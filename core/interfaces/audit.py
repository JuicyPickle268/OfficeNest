"""审计日志存储抽象接口"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AuditRecord:
    """一条审计记录"""
    id: str
    event_type: str
    timestamp: float
    source: str
    summary: str                       # 人类可读摘要
    detail: dict = field(default_factory=dict)
    task_id: str | None = None


class IAuditStore(ABC):
    """审计日志：记录每一次关键操作，可追溯"""

    @abstractmethod
    async def log(self, record: AuditRecord) -> str:
        """写入一条审计记录。返回 ID。"""
        ...

    @abstractmethod
    async def query(
        self,
        task_id: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
    ) -> list[AuditRecord]:
        """按条件查询审计记录。"""
        ...

    @abstractmethod
    async def get_task_trail(self, task_id: str) -> list[AuditRecord]:
        """获取某个任务的所有审计记录（完整追溯链）。"""
        ...
