"""LLM 客户端抽象接口——所有模型提供商必须实现此接口。"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    """LLM 响应数据。"""
    content: str | None = None      # 回复文本
    thinking: str | None = None     # 思考过程（DeepSeek reasoning）
    tool_calls: list = field(default_factory=list)  # 工具调用列表 [ToolCall]
    finish_reason: str = "stop"     # 结束原因
    usage: dict = field(default_factory=dict)       # token 用量


class ILLMClient(ABC):
    """LLM 客户端抽象接口——通过依赖注入接入引擎。"""

    @abstractmethod
    async def chat(self, messages: list[dict], tools: list[dict] | None = None,
                   temperature: float | None = None) -> LLMResponse:
        """非流式调用。"""
        ...

    # 注：chat_stream 由具体实现提供，不在接口中声明（引擎通过 duck-typing 调用）
