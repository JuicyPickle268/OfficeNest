"""
工具注册表实现。
自动发现 Skill、生成 JSON Schema、执行分发。
"""
import json
import inspect
from typing import Any

from core.interfaces.tool import ToolCall, ToolResult
from core.interfaces.tool_registry import IToolRegistry


class ToolRegistry(IToolRegistry):
    """
    工具注册表。
    - 每个 Skill 注册自己的工具函数
    - 自动从函数签名生成 JSON Schema
    - 执行时记录审计信息
    """

    def __init__(self):
        self._tools: dict[str, dict] = {}       # name → {fn, schema, skill_instance}
        self._skills: list = []

    def register(self, skill) -> None:
        """注册一个 Skill 实例的所有工具。"""
        self._skills.append(skill)

        for tool_info in skill.get_tools():
            name = tool_info["name"]
            fn = tool_info["fn"]
            schema = tool_info["schema"]
            self._tools[name] = {
                "fn": fn,
                "schema": schema,
                "skill": skill,
            }

    def list_tools(self, context_hint: str = "") -> list[dict]:
        """返回 JSON Schema 格式的工具列表。"""
        tools = []
        for name, info in self._tools.items():
            schema = info["schema"].copy()

            # 确保 schema.function 存在并设 name
            fn_block = schema.setdefault("function", {})
            fn_block["name"] = name
            fn_block.setdefault("description", name)
            fn_block.setdefault("parameters", {"type": "object", "properties": {}})

            # 转为 OpenAI tool 格式
            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": fn_block.get("description", name),
                    "parameters": fn_block.get("parameters", {"type": "object", "properties": {}}),
                }
            })
        return tools

    async def execute(self, call: ToolCall) -> ToolResult:
        """执行一个工具调用。"""
        info = self._tools.get(call.name)
        if not info:
            return ToolResult(
                call_id=call.id,
                error=f"未知工具: {call.name}。可用工具: {', '.join(self._tools.keys())}"
            )

        try:
            fn = info["fn"]
            # 检查是否是 async 函数
            if inspect.iscoroutinefunction(fn):
                result = await fn(**call.arguments)
            else:
                result = fn(**call.arguments)

            # 结果转字符串
            if isinstance(result, str):
                content = result
            elif isinstance(result, (dict, list)):
                content = json.dumps(result, ensure_ascii=False, indent=2)
            else:
                content = str(result)

            return ToolResult(
                call_id=call.id,
                content=content,
                data=result if isinstance(result, dict) else None,
            )
        except Exception as e:
            return ToolResult(
                call_id=call.id,
                error=str(e),
            )
