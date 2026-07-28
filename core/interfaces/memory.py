"""长期记忆存储抽象接口"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class MemoryEntry:
    """一条记忆"""
    id: str
    content: str                       # 记忆文本
    keywords: list[str] = field(default_factory=list)
    source: str = ""                   # 来源（对话摘要 / 用户注册 / 工具产出）
    importance: int = 1                # 1-5，越高越重要
    created_at: float = 0.0
    access_count: int = 0


class IMemoryStore(ABC):
    """长期记忆：存储对话摘要、关键信息，按需检索注入上下文"""

    @abstractmethod
    async def store(self, entry: MemoryEntry) -> str:
        """存储一条记忆。返回 ID。"""
        ...

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        """
        检索相关记忆。
        实现可用全文搜索（SQLite FTS5）或简单的关键词匹配。
        """
        ...

    @abstractmethod
    async def get_recent(self, limit: int = 20) -> list[MemoryEntry]:
        """获取最近的记忆。"""
        ...

    @abstractmethod
    async def summarize_and_archive(
        self, messages: list[dict], max_keep: int = 10
    ) -> list[MemoryEntry]:
        """
        总结消息历史，归档到记忆库。
        返回新创建的记忆条目。
        messages: 最近 N 轮对话
        max_keep: 保留最近 N 条在上下文中
        """
        ...
