"""
公式注册表 —— SQLite 存储 LLM 写过的公式。
公式内容由 LLM 提供（它的知识），这里只负责存/取/列/删。
与 WorkflowStore 同构：写一次，之后按名字直接调用。
"""
import sqlite3, uuid
from pathlib import Path
from datetime import datetime, timezone


class FormulaStore:
    """公式的增删查。求值不在这里（由 FormulaSkill 的安全求值器负责）。"""

    def __init__(self, db_path: str = "./data/mother.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS formulas (
            id TEXT PRIMARY KEY, name TEXT UNIQUE, expression TEXT,
            description TEXT DEFAULT '', created_at REAL)""")
        self._conn.commit()

    def save(self, name: str, expression: str, description: str = "") -> str:
        """保存公式，同名覆盖。"""
        now = datetime.now(timezone.utc).timestamp()
        existing = self._conn.execute(
            "SELECT id FROM formulas WHERE name=?", (name,)
        ).fetchone()
        if existing:
            self._conn.execute(
                "UPDATE formulas SET expression=?, description=?, created_at=? WHERE name=?",
                (expression, description, now, name))
            self._conn.commit()
            return f"✅ 公式已更新: {name} = {expression}"
        fid = f"fm_{uuid.uuid4().hex[:8]}"
        self._conn.execute(
            "INSERT INTO formulas VALUES (?,?,?,?,?)",
            (fid, name, expression, description, now))
        self._conn.commit()
        return f"✅ 公式已保存: {name} = {expression}"

    def get(self, name: str) -> dict | None:
        row = self._conn.execute(
            "SELECT name, expression, description FROM formulas WHERE name=?", (name,)
        ).fetchone()
        if not row:
            return None
        return {"name": row[0], "expression": row[1], "description": row[2]}

    def list_all(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT name, expression, description FROM formulas ORDER BY created_at DESC"
        ).fetchall()
        return [{"name": r[0], "expression": r[1], "description": r[2]} for r in rows]

    def delete(self, name: str) -> bool:
        cur = self._conn.execute("DELETE FROM formulas WHERE name=?", (name,))
        self._conn.commit()
        return cur.rowcount > 0

    def close(self):
        self._conn.close()
