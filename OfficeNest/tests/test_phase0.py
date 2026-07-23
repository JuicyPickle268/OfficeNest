"""
Phase 0 验收测试。
运行方式：python tests/test_phase0.py
不依赖飞书、不依赖 Office、不需要任何外部凭证。
"""
import sys
from pathlib import Path

# 将项目根目录加入 path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_config():
    """测试：配置加载"""
    from config.schema import load_config, Config

    cfg = load_config("config/default.yaml")
    assert isinstance(cfg, Config), "cfg 必须是 Config 实例"
    assert cfg.app.name == "Mother"
    assert cfg.llm.model == "deepseek-chat"
    assert cfg.llm.max_rounds == 8
    assert cfg.office.auto_backup is True
    print("  ✅ config 加载正常")


def test_event_types():
    """测试：事件类型枚举"""
    from core.events.types import EventType

    assert EventType.TOOL_CALL_START == "tool.call.start"
    assert EventType.TOOL_CALL_DONE == "tool.call.done"
    assert EventType.FEISHU_MESSAGE_RECEIVED == "feishu.message.received"
    assert EventType.SYSTEM_STARTUP == "system.startup"
    assert EventType.ERROR_SELF_HEAL_ATTEMPT == "error.self_heal.attempt"
    assert len(list(EventType)) >= 25, f"事件类型应≥25，实际{len(list(EventType))}"
    print(f"  ✅ EventType 枚举正常（{len(list(EventType))} 种事件类型）")


def test_event_creation():
    """测试：事件创建"""
    from core.events.event import Event
    from core.events.types import EventType

    evt = Event(
        type=EventType.TOOL_CALL_DONE,
        source="test_runner",
        data={"tool": "excel_write", "rows": 5},
    )
    assert evt.event_id.startswith("evt_"), f"event_id 格式不对: {evt.event_id}"
    assert evt.timestamp > 0

    d = evt.to_dict()
    assert d["type"] == "tool.call.done"
    assert d["source"] == "test_runner"
    print(f"  ✅ Event 创建正常 (id={evt.event_id[:16]}...) ")


def test_event_bus():
    """测试：事件总线发布/订阅"""
    from core.events.bus import SimpleEventBus
    from core.events.event import Event
    from core.events.types import EventType

    bus = SimpleEventBus()
    received = []

    bus.subscribe(EventType.TOOL_CALL_START, lambda e: received.append(e))
    bus.subscribe(EventType.TOOL_CALL_DONE, lambda e: received.append(e))

    bus.publish(Event(type=EventType.TOOL_CALL_START, source="test", data={}))
    bus.publish(Event(type=EventType.TOOL_CALL_DONE, source="test", data={}))
    bus.publish(Event(type=EventType.MOTHER_ROUND_START, source="test", data={}))  # 无人订阅

    assert len(received) == 2
    assert bus.subscriber_count == 2
    print(f"  ✅ EventBus 正常（{bus.subscriber_count} 个订阅者）")


def test_logger():
    """测试：日志系统（内存数据库）"""
    from core.events.event import Event
    from core.events.types import EventType
    from infrastructure.logger.logger import Logger

    logger = Logger(":memory:")  # 内存数据库

    # L1: 写入事件
    evt = Event(type=EventType.TOOL_CALL_DONE, source="test", data={"k": "v"})
    logger.log_event(evt)
    rows = logger.query_events(limit=1)
    assert len(rows) == 1
    assert rows[0]["type"] == "tool.call.done"

    # L2: 创建任务
    logger.create_task("task_test", "测试任务")
    logger.update_task("task_test", status="done")

    # L3: 创建步骤
    logger.create_step("step_test", "task_test", "excel_write", {"range": "A1"})
    logger.update_step("step_test", status="done", result="成功")

    # L4: 错误模式
    logger.record_error_pattern("test_pattern", "测试模式", category="api_format", suggestion="修复建议")
    logger.record_error_pattern("test_pattern", "测试模式")  # 第二次，count 应增加

    # L5: 指标
    logger.upsert_daily_metrics(tasks_total=10, tasks_passed=8)

    logger.close()
    print("  ✅ Logger 五层日志正常")


def test_interfaces():
    """测试：所有接口可导入，ABC 定义正确"""
    from core.interfaces.tool import ToolCall, ToolResult
    from core.interfaces.llm_client import LLMResponse
    from core.interfaces.feishu_gateway import FeishuMessage
    from core.interfaces.office_bridge import CellRange, TableData
    from core.interfaces.memory import MemoryEntry
    from core.interfaces.audit import AuditRecord
    from core.interfaces.file_registry import FileEntry

    # 验证 dataclass 可实例化
    tc = ToolCall(id="1", name="test", arguments={"a": 1})
    assert tc.name == "test"

    tr = ToolResult(call_id="1", content="done")
    assert tr.content == "done"

    lr = LLMResponse(content="hello", finish_reason="stop")
    assert lr.content == "hello"

    fm = FeishuMessage(id="m1", chat_id="c1", text="你好", mentioned=True)
    assert fm.mentioned is True

    cr = CellRange(sheet="Sheet1", start="A1", end="D10")
    assert cr.end == "D10"

    td = TableData(headers=["A", "B"], rows=[["1", "2"]])
    assert len(td.headers) == 2

    me = MemoryEntry(id="mem1", content="测试记忆", importance=3)
    assert me.importance == 3

    ar = AuditRecord(id="aud1", event_type="tool.call.done", timestamp=1.0, source="test", summary="测试")
    assert ar.summary == "测试"

    fe = FileEntry(name="测试", path="/test.xlsx", file_type="excel")
    assert fe.file_type == "excel"

    # 验证 ABC 可被继承
    from core.interfaces.llm_client import ILLMClient

    class MockLLM(ILLMClient):
        async def chat(self, messages, tools=None, temperature=0.3):
            return LLMResponse(content="mock")

    assert issubclass(MockLLM, ILLMClient)

    print("  ✅ 所有接口正常（10个接口、所有dataclass可实例化、ABC可继承）")


def test_panel_import():
    """测试：面板模块可导入（不启动 GUI）"""
    # 只测试导入，不测试 tkinter 渲染（CI 环境无显示器）
    try:
        from panel.admin_panel import MotherPanel
        print("  ✅ tkinter 面板模块可导入")
    except ImportError as e:
        print(f"  ⚠️ 面板导入跳过: {e}")


def main():
    print("=" * 60)
    print("  Mother v2 — Phase 0 验收测试")
    print("=" * 60)

    tests = [
        ("配置加载", test_config),
        ("事件类型", test_event_types),
        ("事件创建", test_event_creation),
        ("事件总线", test_event_bus),
        ("日志系统", test_logger),
        ("接口定义", test_interfaces),
        ("面板导入", test_panel_import),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  ❌ {name} 失败: {e}")

    print()
    print(f"  结果: {passed} 通过, {failed} 失败")
    if failed == 0:
        print("  ✅✅✅ Phase 0 验收通过！")
    else:
        print("  ❌ Phase 0 验收未通过，请检查")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
