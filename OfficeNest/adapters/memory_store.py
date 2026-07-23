"""
记忆系统实现（SQLite）。
每次对话自动保存，下次启动自动加载。
"""
import sqlite3
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

from core.interfaces.memory import IMemoryStore, MemoryEntry


class SQLiteMemoryStore(IMemoryStore):
    """SQLite 长期记忆：对话历史 + 关键摘要。"""

    def __init__(self, db_path: str = "./data/mother.db"):
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self):
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id          TEXT PRIMARY KEY,
                content     TEXT NOT NULL,
                keywords    TEXT DEFAULT '[]',
                source      TEXT DEFAULT '',
                importance  INTEGER DEFAULT 1,
                created_at  REAL,
                access_count INTEGER DEFAULT 0
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT DEFAULT 'default',
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                created_at  REAL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                title       TEXT DEFAULT '新对话',
                created_at  REAL,
                updated_at  REAL
            )
        """)
        self._conn.commit()
        # 迁移旧 chat_history 表（无 session_id 列）
        try:
            self._conn.execute("ALTER TABLE chat_history ADD COLUMN session_id TEXT DEFAULT 'default'")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_history(session_id)")
        self._conn.commit()

    # ── 记忆 ──

    async def store(self, entry: MemoryEntry) -> str:
        mid = entry.id or f"mem_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).timestamp()
        self._conn.execute(
            """INSERT OR REPLACE INTO memories
               (id, content, keywords, source, importance, created_at, access_count)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (mid, entry.content, json.dumps(entry.keywords, ensure_ascii=False),
             entry.source, entry.importance, entry.created_at or now, entry.access_count),
        )
        self._conn.commit()
        return mid

    async def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE content LIKE ? ORDER BY importance DESC, created_at DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    async def get_recent(self, limit: int = 20) -> list[MemoryEntry]:
        rows = self._conn.execute(
            "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    async def summarize_and_archive(
        self, messages: list[dict], max_keep: int = 10
    ) -> list[MemoryEntry]:
        return []  # 后续升级：用 LLM 总结归档

    # ── 对话历史 ──

    def save_message(self, role: str, content: str, session_id: str = "default"):
        """保存单条消息。"""
        now = datetime.now(timezone.utc).timestamp()
        self._conn.execute(
            "INSERT INTO chat_history (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, now),
        )
        self._conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        self._conn.commit()

    def load_history(self, session_id: str = "default", max_messages: int = 40) -> list[dict]:
        """加载指定会话的消息。"""
        rows = self._conn.execute(
            "SELECT role, content FROM chat_history WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, max_messages),
        ).fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    def clear_history(self, session_id: str = "default"):
        """清空指定会话。"""
        self._conn.execute("DELETE FROM chat_history WHERE session_id = ?", (session_id,))
        self._conn.commit()

    # ── 会话管理 ──

    def create_session(self, title: str = "新对话") -> str:
        now = datetime.now(timezone.utc).timestamp()
        sid = f"sess_{uuid.uuid4().hex[:8]}"
        self._conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (sid, title, now, now),
        )
        self._conn.commit()
        return sid

    def list_sessions(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
        return [{"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows]

    def rename_session(self, sid: str, title: str):
        self._conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, sid))
        self._conn.commit()

    def delete_session(self, sid: str):
        self._conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
        self._conn.execute("DELETE FROM chat_history WHERE session_id = ?", (sid,))
        self._conn.commit()

    def get_session(self, sid: str) -> dict | None:
        row = self._conn.execute("SELECT id, title FROM sessions WHERE id = ?", (sid,)).fetchone()
        return {"id": row[0], "title": row[1]} if row else None

    def ensure_session(self, sid: str = "default") -> str:
        if not self.get_session(sid):
            self._conn.execute(
                "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, '新对话', ?, ?)",
                (sid, datetime.now(timezone.utc).timestamp(), datetime.now(timezone.utc).timestamp()),
            )
            self._conn.commit()
        return sid

    def get_context(self) -> str:
        """生成上下文摘要供 LLM 使用。"""
        memories = self._conn.execute(
            "SELECT content FROM memories WHERE importance >= 3 ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        if not memories:
            return ""
        return "## 重要历史\n" + "\n".join(f"- {m[0]}" for m in memories)

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _row_to_entry(row: tuple) -> MemoryEntry:
        try:
            keywords = json.loads(row[2])
        except (json.JSONDecodeError, TypeError):
            keywords = []
        return MemoryEntry(
            id=row[0], content=row[1], keywords=keywords,
            source=row[3], importance=row[4],
            created_at=row[5], access_count=row[6] or 0,
        )
