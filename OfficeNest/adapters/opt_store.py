"""
优化建议存储——SQLite，按工具分类。
每次优化器发现效率问题，自动存入建议表。
AI 可按工具类别查询建议，作为动态提示词补丁。
"""
import sqlite3, uuid
from pathlib import Path
from datetime import datetime, timezone


class OptStore:
    """优化建议 SQL 存储。"""

    def __init__(self, db_path: str = "./data/mother.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS opt_suggestions (
            id TEXT PRIMARY KEY, tool TEXT, suggestion TEXT,
            reason TEXT, severity INTEGER DEFAULT 1,
            created_at REAL, applied INTEGER DEFAULT 0)""")
        self._conn.commit()

    def add(self, tool: str, suggestion: str, reason: str = "", severity: int = 1) -> str:
        sid = f"opt_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).timestamp()
        self._conn.execute("INSERT INTO opt_suggestions VALUES (?,?,?,?,?,?,?)",
                           (sid, tool, suggestion, reason, severity, now, 0))
        self._conn.commit()
        return sid

    def get_by_tool(self, tool: str, limit: int = 5) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, tool, suggestion, reason FROM opt_suggestions WHERE tool=? AND applied=0 "
            "ORDER BY severity DESC, created_at DESC LIMIT ?", (tool, limit)
        ).fetchall()
        return [{"id": r[0], "tool": r[1], "suggestion": r[2], "reason": r[3]} for r in rows]

    def mark_applied(self, sid: str):
        self._conn.execute("UPDATE opt_suggestions SET applied=1 WHERE id=?", (sid,))
        self._conn.commit()

    def get_pending_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM opt_suggestions WHERE applied=0").fetchone()[0]

    def get_all(self, tool_filter: str = "") -> list[dict]:
        """获取所有未应用建议，可按工具筛选。返回含 id。"""
        if tool_filter:
            rows = self._conn.execute(
                "SELECT id, tool, suggestion, reason, severity FROM opt_suggestions "
                "WHERE applied=0 AND tool=? ORDER BY severity DESC, created_at DESC", (tool_filter,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, tool, suggestion, reason, severity FROM opt_suggestions "
                "WHERE applied=0 ORDER BY severity DESC, created_at DESC"
            ).fetchall()
        return [{"id": r[0], "tool": r[1], "suggestion": r[2], "reason": r[3], "severity": r[4]} for r in rows]

    def delete(self, sid: str):
        """软删除（标记为已应用）。"""
        self._conn.execute("UPDATE opt_suggestions SET applied=1 WHERE id=?", (sid,))
        self._conn.commit()

    def clear_pending(self):
        """清空所有未应用建议（标记为已应用）。"""
        self._conn.execute("UPDATE opt_suggestions SET applied=1 WHERE applied=0")
        self._conn.commit()

    def close(self):
        self._conn.close()
