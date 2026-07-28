"""
事件总线：发布/订阅模式。
所有模块通过事件总线解耦通信。
"""
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Callable

from .event import Event
from .types import EventType


class IEventBus(ABC):
    """事件总线抽象接口"""

    @abstractmethod
    def publish(self, event: Event) -> None:
        """发布事件，通知所有订阅者。"""
        ...

    @abstractmethod
    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """订阅某类事件。handler 在 publish 时同步调用。"""
        ...

    @abstractmethod
    def unsubscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """取消订阅。"""
        ...


class SimpleEventBus(IEventBus):
    """
    同步事件总线实现。
    使用 dict 存储订阅关系，publish 时遍历调用。
    """

    def __init__(self):
        self._handlers: dict[EventType, list[Callable]] = defaultdict(list)

    def publish(self, event: Event) -> None:
        event_type = EventType(event.type)
        for handler in self._handlers.get(event_type, []):
            try:
                handler(event)
            except Exception as e:
                # 某个订阅者出错不影响其他订阅者
                print(f"[EventBus] Handler error for {event.type}: {e}")

    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    @property
    def subscriber_count(self) -> int:
        """返回总订阅数（调试用）。"""
        return sum(len(h) for h in self._handlers.values())
