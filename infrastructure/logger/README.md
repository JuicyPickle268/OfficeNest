# infrastructure/logger/ — 日志系统

## 文件

| 文件 | 说明 |
|------|------|
| `schema.sql` | 5张表的建表语句 |
| `logger.py` | Logger 实现类 |

## 五层结构

```
L5: metrics      每日汇总指标（给人类看的仪表盘）
L4: error_patterns  聚合的错误模式（自动发现问题）
L3: steps        每个工具调用（重试链、自我修正）
L2: tasks        按用户请求聚合
L1: events       所有事件（最底层，最全）
```

## 使用方式

```python
from infrastructure.logger.logger import Logger
from core.events.event import Event
from core.events.types import EventType

logger = Logger("./data/mother.db")

# L1: 记录事件
event = Event(type=EventType.TOOL_CALL_DONE, source="test", data={"tool": "excel_write"})
logger.log_event(event)

# L2: 创建任务
logger.create_task("task_001", "帮我更新招聘数据")

# L3: 记录步骤
logger.create_step("step_001", "task_001", "excel_write", {"range": "A1:D10"})
logger.update_step("step_001", status="done", result="写入成功")

# L4: 记录错误模式
logger.record_error_pattern(
    "field_name_vs_id",
    "使用字段名而非字段ID",
    category="api_format",
    suggestion="先调 list_fields 获取字段ID映射"
)

# L5: 更新指标
logger.upsert_daily_metrics(tasks_total=1, tasks_passed=1)

logger.close()
```
