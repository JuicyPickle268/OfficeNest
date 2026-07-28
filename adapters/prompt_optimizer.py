"""
提示词优化器——每轮结束后观察行为，生成优化建议。
"""
import json, re


class PromptOptimizer:
    """
    分析对话历史，发现效率问题，给出提示词修改建议。
    不依赖 LLM——纯规则引擎，零延迟。
    """

    def __init__(self, store=None):
        self._store = store
        self._stats: dict = {}
        self._suggestions: list = []
        self._history: list = []

    def analyze(self, user_msg: str, tool_calls: list[str],
                rounds: int, thinking: str = "", reply: str = "") -> dict | None:
        """分析一轮对话，返回优化建议或 None。"""
        issues = []

        # 模式 1：重复验证——同一工具在单轮中调用超过 3 次
        tc_counts = {}
        for tc in tool_calls:
            tc_counts[tc] = tc_counts.get(tc, 0) + 1
        for tool, count in tc_counts.items():
            if count >= 3 and tool in ('excel_read', 'file_list_dir', 'excel_get_sheets'):
                issues.append(("重复验证", tool, count,
                    f"工具'{tool}'在一轮中调用了{count}次。建议加规则：'读写完成后不重复验证'"))

        # 模式 2：决策摇摆——A→B→A 模式
        for i in range(len(tool_calls) - 2):
            if tool_calls[i] == tool_calls[i+2] and tool_calls[i] != tool_calls[i+1]:
                issues.append(("决策摇摆", tool_calls[i:i+3],
                    f"先{tool_calls[i]}→{tool_calls[i+1]}→{tool_calls[i]}，犹豫了。"
                    "建议加规则：'选定工具后坚持使用，除非明确失败'"))

        # 模式 3：过度思考——thinking 文本 > 500 字但工具调用很少
        if thinking and len(thinking) > 500 and len(tool_calls) <= 2:
            issues.append(("过度思考", len(thinking),
                f"思考{len(thinking)}字，但只调了{len(tool_calls)}个工具。"
                "建议加规则：'行动优于过度分析，2次工具调用内完成简单任务'"))

        # 模式 4：轮次过多
        if rounds >= 7:
            issues.append(("轮次过多", rounds,
                f"用了{rounds}轮完成一个任务。建议拆分为多个子任务或简化流程。"))

        if not issues:
            return None

        # 生成建议
        reasons = "; ".join(f"{r[0]}" for r in issues)
        detail = "\n".join(f"• {r[2]}" for r in issues)

        suggestion = {
            "type": "prompt_optimize",
            "reason": reasons,
            "detail": detail,
            "severity": max(1, min(3, len(issues))),  # 1-3
            "timestamp": __import__('time').time(),
        }

        self._suggestions.append(suggestion)
        return suggestion

    def get_pending(self) -> list[dict]:
        """获取待处理的建议。"""
        return self._suggestions

    def clear(self):
        self._suggestions.clear()
