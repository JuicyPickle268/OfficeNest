"""工具调用与结果数据结构"""
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """LLM 发起的工具调用"""
    id: str                          # 调用 ID（由 LLM 生成）
    name: str                        # 工具名称
    arguments: dict = field(default_factory=dict)  # 参数


@dataclass
class ToolResult:
    """工具执行结果，返回给 LLM"""
    call_id: str                     # 对应 ToolCall.id
    content: str = ""                # 成功时返回给 LLM 的文本
    error: str | None = None         # 失败时的错误描述
    audit_id: str = ""               # 审计回执号
    data: dict | None = None         # 结构化数据（可选，供上层消费）
