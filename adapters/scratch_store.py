"""
Scratch Store —— AI 临时草稿纸（SQLite KV）。
跨 tool call 暂存：行号映射、列名映射、变更列表、文件路径等。
"""
import sqlite3
import json
from pathlib import Path


class ScratchStore:
    """会话级 KV 暂存。"""

    def __init__(self, db_path: str = "./data/mother.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS scratch (
            session_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (session_id, key)
        )""")
        self._conn.commit()

    def set(self, session_id: str, key: str, value: str) -> str:
        self._conn.execute(
            "INSERT OR REPLACE INTO scratch VALUES (?, ?, ?)",
            (session_id, key, value),
        )
        self._conn.commit()
        return f"✅ scratch_set: {key}"

    def get(self, session_id: str, key: str) -> str:
        row = self._conn.execute(
            "SELECT value FROM scratch WHERE session_id=? AND key=?",
            (session_id, key),
        ).fetchone()
        return row[0] if row else f"（{key} 未设置）"

    def delete(self, session_id: str, key: str) -> str:
        self._conn.execute(
            "DELETE FROM scratch WHERE session_id=? AND key=?",
            (session_id, key),
        )
        self._conn.commit()
        return f"✅ scratch_delete: {key}"

    def list(self, session_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT key, substr(value, 1, 100) FROM scratch WHERE session_id=?",
            (session_id,),
        ).fetchall()
        return [{"key": r[0], "preview": r[1]} for r in rows]

    def close(self):
        self._conn.close()
