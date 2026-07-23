"""
Mother Engine：Tool Call 循环核心。
"""
import uuid
import time
import threading
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

    流程：
    1. 收到用户消息
    2. 构建上下文（System Prompt + 记忆 + 文件列表）
    3. 调 LLM
    4. 如果 LLM 返回 tool_calls → 执行工具 → 把结果注入消息 → 回到第3步
    5. 如果 LLM 返回纯文本 → 回复用户
    """

    def __init__(
        self,
        llm_client: ILLMClient,
        tool_registry: IToolRegistry,
        context_builder: ContextBuilder | None = None,
        event_bus: IEventBus | None = None,
        max_rounds: int = 8,
    ):
        self._llm = llm_client
        self._tools = tool_registry
        self._context = context_builder or ContextBuilder()
        self._bus = event_bus or SimpleEventBus()
        self._max_rounds = max_rounds
        self._last_tool_calls: list = []  # 供优化器
        self._dangerous_tools = {"file_delete"}
        self._dangerous_tools = {"excel_delete_rows", "file_delete", "word_export_pdf", "powershell_run"}
        self._confirm_handler: callable | None = None  # async (tool_name, args) -> bool
        self._cancel_flag = threading.Event()  # 中断标志

    def set_confirm_handler(self, handler):
        """设置危险操作确认回调。handler(tool_name, args) -> bool。"""
        self._confirm_handler = handler

    def cancel(self):
        """外部调用：中断当前正在执行的 tool-call 循环。"""
        self._cancel_flag.set()

    def reset(self):
        """重置中断标志（下次 process 前自动调用）。"""
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
        处理一条用户消息，返回最终结果。
        """
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        start_time = datetime.now(timezone.utc).timestamp()
        self._cancel_flag.clear()  # 新请求重置中断标志

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

        # 连环错误检测
        _consecutive_errors = 0
        _last_error_tool = ""
        _last_error_msg = ""
        MAX_CONSECUTIVE_ERRORS = 3

        for round_num in range(1, self._max_rounds + 1):
            # 中断检查
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

            # 无 tool_calls → LLM 给出最终回复
            if not response.tool_calls:
                content = response.content or ""
                # 虚假成功声明检测：声称写入但本轮没调 excel_write
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

            # 添加 assistant 消息（含 thinking 以保持上下文）
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

            # 执行每个 tool_call
            self._last_tool_calls = []  # 每轮重置
            for tc in response.tool_calls:
                self._last_tool_calls.append(tc)
                # ── 危险操作确认 ──
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
                    # ── 连环错误检测 ──
                    if tc.name == _last_error_tool and result.error == _last_error_msg:
                        _consecutive_errors += 1
                    else:
                        _consecutive_errors = 1
                        _last_error_tool = tc.name
                        _last_error_msg = result.error

                    if _consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        # 注入终止消息，但让 LLM 有机会记录 suggestion
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": (
                                f"该工具已连续失败 {MAX_CONSECUTIVE_ERRORS} 次（{result.error}）。"
                                f"请用 suggest_improvement 记录此问题供开发者修复，然后告知用户操作已终止。"
                            ),
                        })
                        # 标记 round 继续而非返回，让 LLM 处理剩余轮次
                        _consecutive_errors = 0  # 防止反复触发
                        continue  # 跳过本次工具执行的后续代码
                else:
                    _consecutive_errors = 0  # 成功则重置计数
                    self._bus.publish(Event(
                        type=EventType.TOOL_CALL_DONE,
                        source="mother.engine",
                        task_id=task_id,
                        data={"tool": tc.name, "result_len": len(result.content)},
                    ))

                # 注入 tool result 到消息
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result.error or result.content,
                })

        # 达到最大轮次
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


# 需要 json 模块
import json
