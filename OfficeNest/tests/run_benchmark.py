"""
基准测试运行器。
python tests/run_benchmark.py
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.schema import load_config
from adapters.llm.deepseek_client import DeepSeekClient
from core.mother.engine import MotherEngine
from core.mother.context_builder import ContextBuilder
from core.mother.tool_registry import ToolRegistry
from skills.excel_skill import ExcelSkill
from skills.word_skill import WordSkill
from skills.clipboard_skill import ClipboardSkill
from skills.system_skill import SystemSkill
from skills.improvement_skill import ImprovementSkill
from adapters.improvement_tracker import ImprovementTracker
from adapters.file_registry import FileRegistry
from tests.mock_office import MockOfficeBridge
from tests.evaluator import Evaluator


async def main():
    cfg = load_config("config/default.yaml")

    if not cfg.llm.api_key:
        print("❌ 请先在配置中设置 DeepSeek API Key")
        return

    print("=" * 60)
    print("  Mother v2 — Phase 5a 基准测试")
    print(f"  模型: {cfg.llm.model}")
    print("=" * 60)

    # Mock Office
    mock_office = MockOfficeBridge()

    # LLM
    llm = DeepSeekClient(
        api_key=cfg.llm.api_key,
        model=cfg.llm.model,
        base_url=cfg.llm.base_url,
        temperature=0.1,  # 低温度，更确定性
    )

    # Tool Registry + Mock Skills
    registry = ToolRegistry()
    registry.register(ExcelSkill(mock_office))
    registry.register(WordSkill(mock_office))
    registry.register(ClipboardSkill())
    registry.register(SystemSkill())
    tracker = ImprovementTracker(":memory:")
    registry.register(ImprovementSkill(tracker))

    # Engine
    engine = MotherEngine(
        llm_client=llm,
        tool_registry=registry,
        context_builder=ContextBuilder(),
        max_rounds=10,
    )

    # 跑测试
    evaluator = Evaluator(engine, mock_office)
    print()
    result = await evaluator.run_all()

    # 输出报告
    print()
    print("=" * 60)
    print(f"  通过: {result['passed']}/{result['total']} ({result['pass_rate']})")
    print("=" * 60)
    print()

    # 详细结果
    for r in result["details"]:
        status = "✅" if r["passed"] else "❌"
        tools = " → ".join(r["tool_calls"]) if r["tool_calls"] else "(无)"
        print(f"  {status} {r['task']} {r['name']}")
        print(f"     工具链: {tools}")
        print(f"     轮次: {r['rounds']} | 分数: {r['score']}")
        if r["reasons"]:
            print(f"     {', '.join(r['reasons'])}")
        print()

    # 保存到日志
    try:
        from infrastructure.logger.logger import Logger
        log = Logger(cfg.storage.db_path)
        log.upsert_daily_metrics(
            tasks_total=result["total"],
            tasks_passed=result["passed"],
            tasks_failed=result["failed"],
        )
        log.close()
        print("  📊 指标已写入日志")
    except Exception:
        pass

    return result


if __name__ == "__main__":
    asyncio.run(main())
