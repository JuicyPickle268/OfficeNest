"""LLM 客户端抽象接口"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    """LLM 返回的完整响应"""
    content: str | None = None           # 纯文本回复
    thinking: str | None = None          # 思考过程（DeepSeek thinking 模式）
    tool_calls: list = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict = field(default_factory=dict)


class ILLMClient(ABC):
    """大模型客户端抽象"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """
        发送消息到 LLM，返回响应。
        messages: [{"role": "system"|"user"|"assistant"|"tool", "content": ...}]
        tools: JSON Schema 格式的工具列表
        """
        ...
