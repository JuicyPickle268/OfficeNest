"""工具注册表抽象接口"""
from abc import ABC, abstractmethod

from .tool import ToolCall, ToolResult


class IToolRegistry(ABC):
    """工具注册、Schema 生成、执行分发"""

    @abstractmethod
    def register(self, tool) -> None:
        """注册一个工具实例。"""
        ...

    @abstractmethod
    def list_tools(self, context_hint: str = "") -> list[dict]:
        """
        返回当前可用工具的 JSON Schema 列表。
        context_hint: 可选，根据上下文缩小工具范围。
        """
        ...

    @abstractmethod
    async def execute(self, call: ToolCall) -> ToolResult:
        """
        执行一个工具调用。
        返回 ToolResult，错误不抛异常。
        """
        ...
