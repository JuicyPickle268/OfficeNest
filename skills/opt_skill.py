"""
优化建议 Skill。
"""
from pathlib import Path
from skills.base import BaseSkill


class OptimizationSkill(BaseSkill):

    def __init__(self, store):
        self._store = store

    @property
    def name(self) -> str:
        return "optimize"

    def get_tools(self) -> list[dict]:
        return [
            {"name": "opt_add", "fn": self.opt_add,
             "schema": {"type": "function", "function": {
                 "description": "记录一条给自己用的操作建议（优化自己的做事方式，不是给项目提需求）",
                 "parameters": {"type": "object", "properties": {
                     "tool": {"type": "string", "description": "被优化的工具名，如 excel_read"},
                     "suggestion": {"type": "string", "description": "建议内容，如'读写完成后不重复验证'"},
                     "reason": {"type": "string", "description": "触发原因，如'重复验证/决策摇摆/过度思考/轮次过多'"},
                     "severity": {"type": "integer", "description": "严重度 1-3，1=轻微 3=严重"},
                 }, "required": ["tool", "suggestion", "reason", "severity"]}}}},
            {"name": "opt_check", "fn": self.opt_check,
             "schema": {"type": "function", "function": {
                 "description": "执行任务前检查该工具的优化建议",
                 "parameters": {"type": "object", "properties": {
                     "tool": {"type": "string", "description": "工具名，如 excel_read"}},
                  "required": ["tool"]}}},
            },
            {"name": "opt_export", "fn": self.opt_export,
             "schema": {"type": "function", "function": {
                 "description": "导出优化建议为 CSV 文件",
                 "parameters": {"type": "object", "properties": {
                     "filepath": {"type": "string", "description": "输出路径，如 ./output/suggestions.csv"}},
                  "required": ["filepath"]}}},
            },
            {"name": "opt_import", "fn": self.opt_import,
             "schema": {"type": "function", "function": {
                 "description": "从 CSV 导入优化建议",
                 "parameters": {"type": "object", "properties": {
                     "filepath": {"type": "string", "description": "CSV 文件路径"}},
                  "required": ["filepath"]}}},
            },
        ]

    def opt_add(self, tool: str, suggestion: str, reason: str, severity: int = 1) -> str:
        sid = self._store.add(tool=tool, suggestion=suggestion, reason=reason, severity=severity)
        return f"✅ 已记录优化建议 [{sid[:12]}] {tool}: {suggestion}"

    def opt_check(self, tool: str) -> str:
        items = self._store.get_by_tool(tool, limit=3)
        if not items:
            return f"（{tool} 暂无优化建议）"
        return "\n".join(f"💡 {r['suggestion']}" for r in items)

    def opt_export(self, filepath: str) -> str:
        import csv
        path = Path(filepath)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        try:
            rows = self._store._conn.execute(
                "SELECT tool, suggestion, reason, severity, created_at, applied FROM opt_suggestions ORDER BY created_at"
            ).fetchall()
            with open(str(path), "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["tool", "suggestion", "reason", "severity", "created_at", "applied"])
                for r in rows:
                    w.writerow(list(r))
            return f"✅ 已导出 {len(rows)} 条建议 → {path.name}"
        except Exception as e:
            return f"❌ 导出失败: {e}"

    def opt_import(self, filepath: str) -> str:
        import csv
        path = Path(filepath)
        if not path.exists():
            return f"❌ 文件不存在: {filepath}"
        try:
            count = 0
            with open(str(path), "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("tool") and row.get("suggestion"):
                        self._store.add(
                            tool=row["tool"].strip(),
                            suggestion=row["suggestion"].strip(),
                            reason=row.get("reason", "").strip(),
                            severity=int(row.get("severity", 1)),
                        )
                        count += 1
            return f"✅ 已导入 {count} 条建议"
        except Exception as e:
            return f"❌ 导入失败: {e}"
