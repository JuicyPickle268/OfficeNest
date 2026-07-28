"""
待优化需求追踪表（SQLite）。
"""
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timezone


class ImprovementTracker:
    """需求追踪：LLM 发现不足 → 记录 → 人类查看/解决。"""

    def __init__(self, db_path: str = "./data/mother.db"):
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self):
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS improvements (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                description TEXT DEFAULT '',
                source      TEXT DEFAULT '',
                status      TEXT DEFAULT 'pending',
                created_at  REAL,
                resolved_at REAL
            )
        """)
        self._conn.commit()

    def add(self, title: str, description: str = "", source: str = "") -> str:
        """添加一条待优化需求。返回 ID。"""
        imp_id = f"imp_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).timestamp()
        self._conn.execute(
            "INSERT INTO improvements (id, title, description, source, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
            (imp_id, title, description, source, now),
        )
        self._conn.commit()
        return imp_id

    def list_pending(self) -> list[dict]:
        """列出待处理的需求。"""
        rows = self._conn.execute(
            "SELECT id, title, description, source, created_at FROM improvements WHERE status='pending' ORDER BY created_at DESC"
        ).fetchall()
        return [{"id": r[0], "title": r[1], "description": r[2], "source": r[3], "created_at": r[4]} for r in rows]

    def list_all(self) -> list[dict]:
        """列出全部需求。"""
        rows = self._conn.execute(
            "SELECT id, title, description, source, status, created_at, resolved_at FROM improvements ORDER BY created_at DESC"
        ).fetchall()
        return [{"id": r[0], "title": r[1], "description": r[2], "source": r[3], "status": r[4], "created_at": r[5], "resolved_at": r[6]} for r in rows]

    def resolve(self, imp_id: str) -> bool:
        """标记为已解决。"""
        now = datetime.now(timezone.utc).timestamp()
        cur = self._conn.execute(
            "UPDATE improvements SET status='resolved', resolved_at=? WHERE id=?",
            (now, imp_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
