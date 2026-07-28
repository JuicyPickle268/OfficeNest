"""
事件数据结构。系统中所有事件统一使用此格式。
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid


@dataclass
class Event:
    """
    系统事件。

    字段说明：
    - event_id: 全局唯一 ID，自动生成
    - type: 事件类型（见 EventType 枚举）
    - timestamp: Unix 时间戳（秒，浮点）
    - source: 发出事件的模块名（如 "mother.engine"）
    - parent_id: 父事件 ID（用于追溯因果链）
    - task_id: 所属任务 ID（可选，用于任务聚合）
    - data: 事件携带的数据（dict）
    - level: 日志级别
    """
    type: str
    source: str
    data: dict = field(default_factory=dict)

    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    parent_id: str | None = None
    task_id: str | None = None
    level: str = "INFO"

    def to_dict(self) -> dict:
        """转为 dict，供日志系统序列化。"""
        import json
        return {
            "event_id": self.event_id,
            "type": self.type,
            "timestamp": self.timestamp,
            "source": self.source,
            "parent_id": self.parent_id,
            "task_id": self.task_id,
            "data": json.dumps(self.data, ensure_ascii=False),
            "level": self.level,
        }
