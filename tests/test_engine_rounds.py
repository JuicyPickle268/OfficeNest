"""
引擎轮次控制单元测试。

运行: python -m unittest tests.test_engine_rounds -v
覆盖:
    - max_rounds=0 无限轮次：超长任务可完成
    - 有限轮次仍正常超时
    - cancel() 可中断无限循环
    - _infinite_rounds 生成器
"""
import unittest
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.mother.engine import MotherEngine, _infinite_rounds
from core.interfaces.llm_client import ILLMClient, LLMResponse
from core.interfaces.tool import ToolCall
from core.mother.tool_registry import ToolRegistry
from skills.base import BaseSkill


class FakeLLM(ILLMClient):
    """返回 tool_call 直到 calls 达到 stop_at。"""

    def __init__(self, stop_at=25):
        self.calls = 0
        self.stop_at = stop_at

    async def chat(self, messages, tools=None, temperature=None):
        await asyncio.sleep(0)  # 让出事件循环（测试用）
        self.calls += 1
        if self.calls < self.stop_at:
            return LLMResponse(content="", tool_calls=[
                ToolCall(id=f"t{self.calls}", name="noop", arguments={})])
        return LLMResponse(content="完成", tool_calls=[])

    async def chat_stream(self, messages, tools=None, temperature=None, on_token=None):
        return await self.chat(messages, tools, temperature)


class NoopSkill(BaseSkill):
    @property
    def name(self):
        return "noop"

    def get_tools(self):
        return [{"name": "noop", "fn": lambda: "ok",
                 "schema": {"type": "function", "function": {
                     "name": "noop", "description": "noop",
                     "parameters": {"type": "object", "properties": {}}}}},
                {"name": "fail", "fn": lambda: 1 / 0,
                 "schema": {"type": "function", "function": {
                     "name": "fail", "description": "fail",
                     "parameters": {"type": "object", "properties": {}}}}}]


class TestInfiniteRounds(unittest.TestCase):
    def test_infinite_completes_long_task(self):
        """无限轮次：25 轮任务应完成而非超时。"""
        tools = ToolRegistry()
        tools.register(NoopSkill())
        llm = FakeLLM(stop_at=25)
        engine = MotherEngine(llm_client=llm, tool_registry=tools, max_rounds=0)
        result = asyncio.run(engine.process("跑 25 轮"))
        self.assertIsNone(result.get("timeout"))
        self.assertEqual(result.get("rounds"), 25)

    def test_finite_still_timeouts(self):
        """有限轮次仍正常超时（回归）。"""
        tools = ToolRegistry()
        tools.register(NoopSkill())
        llm = FakeLLM(stop_at=50)
        engine = MotherEngine(llm_client=llm, tool_registry=tools, max_rounds=10)
        result = asyncio.run(engine.process("跑 50 轮"))
        self.assertTrue(result.get("timeout"))
        self.assertEqual(result.get("rounds"), 10)

    def test_cancel_interrupts_infinite(self):
        """cancel() 可中断无限循环。"""
        tools = ToolRegistry()
        tools.register(NoopSkill())
        llm = FakeLLM(stop_at=100000)
        engine = MotherEngine(llm_client=llm, tool_registry=tools, max_rounds=0)

        async def _run():
            async def cancel_later():
                await asyncio.sleep(0.05)
                engine.cancel()
            asyncio.create_task(cancel_later())
            return await engine.process("跑 100000 轮")

        result = asyncio.run(_run())
        self.assertTrue(result.get("cancelled"))
        self.assertLess(result.get("rounds"), 100000)

    def test_generator(self):
        g = _infinite_rounds()
        self.assertEqual([next(g) for _ in range(5)], [1, 2, 3, 4, 5])


if __name__ == "__main__":
    unittest.main()
