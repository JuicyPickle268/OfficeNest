"""
工具注册表 — 注册 Skill、生成 Schema、执行分发。

架构角色：连接 MotherEngine 和所有 Skill。
每个 Skill 注册时提供 (name, fn, schema)，ToolRegistry 维护全局工具表。
"""
import json
import inspect
from typing import Any
from core.interfaces.tool import ToolCall, ToolResult
from core.interfaces.tool_registry import IToolRegistry


class ToolRegistry(IToolRegistry):
    """工具注册与执行中心。"""

    def __init__(self):
        self._tools: dict[str, dict] = {}  # name → {fn, schema, skill}

    def register(self, skill) -> None:
        """注册一个 Skill 的全部工具。skill.get_tools() 返回 [{name,fn,schema}]。"""
        for tool_info in skill.get_tools():
            name = tool_info["name"]
            self._tools[name] = {
                "fn": tool_info["fn"],
                "schema": tool_info["schema"],
                "skill": skill,
            }

    def list_tools(self, context_hint: str = "") -> list[dict]:
        """返回 OpenAI function-calling 格式的工具列表。自动注入 name 到 function 对象。"""
        result = []
        for name, t in self._tools.items():
            schema = dict(t["schema"])  # 浅拷贝，不污染原数据
            schema.setdefault("function", {})["name"] = name
            result.append(schema)
        return result

    async def execute(self, call: ToolCall) -> ToolResult:
        """
        执行工具调用。自动判断 sync/async，异常包装为 error 返回。

        Returns:
            ToolResult: 成功时 content 有文本，失败时 error 有信息。
        """
        tool = self._tools.get(call.name)
        if not tool:
            return ToolResult(call_id=call.id, content="", error=f"未知工具: {call.name}")

        try:
            fn = tool["fn"]
            if inspect.iscoroutinefunction(fn):
                result = await fn(**call.arguments)
            else:
                result = fn(**call.arguments)
            return ToolResult(call_id=call.id, content=str(result))
        except Exception as e:
            return ToolResult(call_id=call.id, content="", error=str(e))
