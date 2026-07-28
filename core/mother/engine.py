"""
引擎 — MotherEngine：Tool Call 循环核心。

这是整个 OfficeNest 的"大脑"。每次收到用户消息，引擎循环执行：
    LLM决策 → 执行工具 → 结果反馈 → LLM再次决策 → 直到LLM给出纯文本回复

架构依赖（全部通过 ABC 接口注入，不依赖具体实现）:
    ILLMClient      — 大模型调用
    IToolRegistry   — 工具注册与执行
    ContextBuilder  — System Prompt 构建
    IEventBus       — 事件发布/订阅
"""
import uuid
import time
import threading
import json
from datetime import datetime, timezone

from core.interfaces.llm_client import ILLMClient
from core.interfaces.tool import ToolCall, ToolResult
from core.interfaces.tool_registry import IToolRegistry
from core.mother.context_builder import ContextBuilder
from core.events.bus import IEventBus, SimpleEventBus
from core.events.event import Event
from core.events.types import EventType


class MotherEngine:
    """
    Tool Call 循环引擎。

    每处理一条用户消息，引擎在循环中反复执行以下步骤：
        1. 调 LLM（携带 System Prompt + 历史对话 + 可用工具列表）
        2. 如果 LLM 返回 tool_calls → 执行工具 → 把结果注入对话历史 → 回到第1步
        3. 如果 LLM 返回纯文本 → 结束，返回最终回复

    内置保护机制：
        - max_rounds: 最多执行 N 轮，防止死循环（默认 8 轮）
        - 危险工具确认: excel_delete_rows / file_delete / powershell_run 需用户确认
        - 连环错误检测: 同一工具连续失败 3 次 → 建议 LLM 放弃
        - 虚假成功拦截: 声称"已写入"但未调 excel_write 时自动警告
        - 中断标志: cancel() 设置 threading.Event，每轮检查，立停

    使用方式:
        engine = MotherEngine(llm_client, tool_registry, max_rounds=20)
        engine.set_confirm_handler(callback)  # 危险操作确认回调
        result = await engine.process("在合同表加一条数据")
    """

    def __init__(
        self,
        llm_client: ILLMClient,
        tool_registry: IToolRegistry,
        context_builder: ContextBuilder | None = None,
        event_bus: IEventBus | None = None,
        max_rounds: int = 8,
    ):
        """
        Args:
            llm_client: LLM 客户端（实现 ILLMClient 接口）
            tool_registry: 工具注册表（实现 IToolRegistry 接口）
            context_builder: System Prompt 生成器（可选，默认 ContextBuilder()）
            event_bus: 事件总线（可选，默认 SimpleEventBus）
            max_rounds: Tool Call 最大循环轮次（防止死循环）
        """
        self._llm = llm_client
        self._tools = tool_registry
        self._context = context_builder or ContextBuilder()
        self._bus = event_bus or SimpleEventBus()
        self._max_rounds = max_rounds
        self._last_tool_calls: list = []  # 最近一轮的工具调用记录，供文件追踪
        self._dangerous_tools = {"excel_delete_rows", "file_delete", "word_export_pdf", "powershell_run"}
        self._confirm_handler: callable | None = None  # 危险操作确认回调
        self._cancel_flag = threading.Event()  # 强制中断标志

    def set_confirm_handler(self, handler):
        """
        设置危险操作确认回调。

        当 LLM 要调用危险工具时，引擎先调此回调询问用户。
        回调必须返回 True（允许）或 False（拒绝）。

        Args:
            handler: async (tool_name, args) -> bool
        """
        self._confirm_handler = handler

    def cancel(self):
        """
        外部调用：强制中断当前正在执行的 tool-call 循环。

        设置 threading.Event，引擎在每轮开头检查该标志。
        中断后返回 {"cancelled": True}。
        线程安全——可从任意线程调用。
        """
        self._cancel_flag.set()

    def reset(self):
        """重置中断标志（每次 process() 开头自动调用）。"""
        self._cancel_flag.clear()

    async def process(
        self,
        user_message: str,
        memory_context: str = "",
        file_list: str = "",
        excel_sync_summary: str = "",
        chat_history: list[dict] | None = None,
        on_token: callable = None,   # on_token(type: str, text: str)
        pinned_file: str = "",
    ) -> dict:
        """
        处理一条用户消息，执行完整的 Tool Call 循环。

        Args:
            user_message: 用户输入文本
            memory_context: 长期记忆摘要（可选，注入 System Prompt）
            file_list: 本地文件列表（可选）
            excel_sync_summary: Excel 同步摘要（可选）
            chat_history: 历史对话消息列表（可选，最多 30 轮）
            on_token: 流式回调函数（可选），接收 (type, text) 对
                       type 可选值: "thinking" / "content" / "tool"
            pinned_file: 用户锁定的文件路径
            user_prefs: 用户个性化偏好文本

        Returns:
            dict:
                task_id     — 任务唯一标识
                response    — LLM 最终文本回复
                thinking    — LLM 思考过程（DeepSeek reasoning）
                rounds      — 实际执行轮数
                tool_calls  — 工具调用总数
                tokens      — 消耗的 token 总数
                elapsed     — 耗时（秒）
                cancelled   — 是否被用户中断（可选）
                timeout     — 是否因超时结束（可选）
        """
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        start_time = datetime.now(timezone.utc).timestamp()
        self._cancel_flag.clear()

        self._bus.publish(Event(
            type=EventType.MOTHER_TASK_START,
            source="mother.engine",
            task_id=task_id,
            data={"user_message": user_message[:200]},
        ))

        messages = self._context.build(
            user_message=user_message,
            memory_context=memory_context,
            file_list=file_list,
            excel_sync_summary=excel_sync_summary,
            chat_history=chat_history,
            pinned_file=pinned_file,
        )

        total_tokens = 0
        tool_calls_count = 0
        _consecutive_errors = 0
        _last_error_tool = ""
        _last_error_msg = ""
        MAX_CONSECUTIVE_ERRORS = 3

        for round_num in range(1, self._max_rounds + 1):
            # ── 中断检查 ──
            if self._cancel_flag.is_set():
                elapsed = datetime.now(timezone.utc).timestamp() - start_time
                return {
                    "task_id": task_id,
                    "response": "⏹ 用户已中断操作。",
                    "rounds": round_num,
                    "tool_calls": tool_calls_count,
                    "tokens": total_tokens,
                    "elapsed": elapsed,
                    "cancelled": True,
                }

            self._bus.publish(Event(
                type=EventType.MOTHER_ROUND_START,
                source="mother.engine",
                task_id=task_id,
                data={"round": round_num},
            ))

            tools_schema = self._tools.list_tools()

            # ── 调 LLM ──
            if on_token:
                response = await self._llm.chat_stream(messages, tools_schema, on_token=on_token)
            else:
                response = await self._llm.chat(messages, tools_schema)

            total_tokens += response.usage.get("total_tokens", 0)

            self._bus.publish(Event(
                type=EventType.MOTHER_ROUND_END,
                source="mother.engine",
                task_id=task_id,
                data={
                    "round": round_num,
                    "tokens": response.usage.get("total_tokens", 0),
                    "has_tool_calls": bool(response.tool_calls),
                    "finish_reason": response.finish_reason,
                },
            ))

            # ── 无 tool_calls → LLM 给出最终回复 ──
            if not response.tool_calls:
                content = response.content or ""
                # 虚假成功声明检测
                if content and tool_calls_count == 0:
                    false_claims = ["已写入", "已确认写入", "已填入", "写入成功", "已经写入", "已保存"]
                    for claim in false_claims:
                        if claim in content:
                            content = (
                                f"⚠️ 系统检测到本轮未调用任何写入工具，但回复中包含'{claim}'。\n"
                                f"请勿在未调用 excel_write 的情况下声称写入成功。\n\n"
                                f"原回复：{content}"
                            )
                            break
                elapsed = datetime.now(timezone.utc).timestamp() - start_time
                model_name = getattr(self._llm, '_model', '?')
                info_line = f"[{model_name} | {tool_calls_count}工具 | {total_tokens} tokens | {round_num}轮]"
                content = f"{info_line}\n{content}"
                self._bus.publish(Event(
                    type=EventType.MOTHER_TASK_DONE,
                    source="mother.engine",
                    task_id=task_id,
                    data={"rounds": round_num, "tools": tool_calls_count, "tokens": total_tokens, "elapsed": elapsed},
                ))
                return {
                    "task_id": task_id,
                    "response": content,
                    "thinking": response.thinking or "",
                    "rounds": round_num,
                    "tool_calls": tool_calls_count,
                    "tokens": total_tokens,
                    "elapsed": elapsed,
                }

            # ── 添加 assistant 消息到历史 ──
            content = response.content or ""
            if response.thinking:
                content = f"[思考]\n{response.thinking}\n[/思考]\n\n{content}"
            assistant_msg = {"role": "assistant", "content": content}
            tool_calls_msg = []
            for tc in response.tool_calls:
                tool_calls_msg.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)},
                })
            if tool_calls_msg:
                assistant_msg["tool_calls"] = tool_calls_msg
            messages.append(assistant_msg)

            # ── 执行每个 tool_call ──
            self._last_tool_calls = []
            for tc in response.tool_calls:
                self._last_tool_calls.append(tc)

                # 危险操作确认
                if tc.name in self._dangerous_tools and self._confirm_handler:
                    approved = await self._confirm_handler(tc.name, tc.arguments)
                    if not approved:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": "用户取消了此操作。请换一种方式或跳过。",
                        })
                        continue

                self._bus.publish(Event(
                    type=EventType.TOOL_CALL_START,
                    source="mother.engine",
                    task_id=task_id,
                    data={"tool": tc.name, "args": tc.arguments},
                ))

                result = await self._tools.execute(tc)
                tool_calls_count += 1

                if result.error:
                    self._bus.publish(Event(
                        type=EventType.TOOL_CALL_ERROR,
                        source="mother.engine",
                        task_id=task_id,
                        data={"tool": tc.name, "error": result.error},
                    ))
                    # 连环错误检测
                    if tc.name == _last_error_tool and result.error == _last_error_msg:
                        _consecutive_errors += 1
                    else:
                        _consecutive_errors = 1
                        _last_error_tool = tc.name
                        _last_error_msg = result.error

                    if _consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": (
                                f"该工具已连续失败 {MAX_CONSECUTIVE_ERRORS} 次（{result.error}）。"
                                f"请用 suggest_improvement 记录此问题供开发者修复，然后告知用户操作已终止。"
                            ),
                        })
                        _consecutive_errors = 0
                        continue
                else:
                    _consecutive_errors = 0
                    self._bus.publish(Event(
                        type=EventType.TOOL_CALL_DONE,
                        source="mother.engine",
                        task_id=task_id,
                        data={"tool": tc.name, "result_len": len(result.content)},
                    ))

                # 注入 tool result 到对话历史
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result.error or result.content,
                })

        # ── 达到最大轮次 ──
        elapsed = datetime.now(timezone.utc).timestamp() - start_time
        return {
            "task_id": task_id,
            "response": f"任务达到最大轮次 ({self._max_rounds})，已执行 {tool_calls_count} 次工具调用。",
            "rounds": self._max_rounds,
            "tool_calls": tool_calls_count,
            "tokens": total_tokens,
            "elapsed": elapsed,
            "timeout": True,
        }
