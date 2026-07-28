# core/events/ — 事件系统

## 文件

| 文件 | 说明 |
|------|------|
| `types.py` | EventType 枚举——系统支持的所有事件类型 |
| `event.py` | Event 数据类——统一的事件格式 |
| `bus.py` | IEventBus 接口 + SimpleEventBus 实现 |

## 核心理念

所有模块通过事件总线通信，不直接依赖对方。

```
Office Bridge ──→ EventBus.publish(Event("office.excel.written"))
                      │
                      ├──→ Logger 订阅 → 写入日志
                      ├──→ Panel 订阅 → 刷新 UI
                      └──→ Audit 订阅 → 写审计记录
```

## 事件命名规范

`{域}.{对象}.{动作}`

- `feishu.message.received`
- `mother.round.start`
- `tool.call.done`
- `office.excel.written`
- `error.self_heal.attempt`

## 使用示例

```python
from core.events.bus import SimpleEventBus
from core.events.event import Event
from core.events.types import EventType

bus = SimpleEventBus()

# 订阅
def on_tool_done(event: Event):
    print(f"工具完成: {event.data}")

bus.subscribe(EventType.TOOL_CALL_DONE, on_tool_done)

# 发布
bus.publish(Event(
    type=EventType.TOOL_CALL_DONE,
    source="office_bridge",
    data={"tool": "excel_write", "rows": 5}
))
```
