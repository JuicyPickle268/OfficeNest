"""
文件注册表实现（SQLite）。
每次创建/操作文件后注册，附带说明，LLM 可通过上下文感知已有文件。
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone

from core.interfaces.file_registry import IFileRegistry, FileEntry


class FileRegistry(IFileRegistry):
    """SQLite 持久化文件注册表。"""

    def __init__(self, db_path: str = "./data/mother.db"):
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self):
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS file_registry (
                name        TEXT PRIMARY KEY,
                path        TEXT NOT NULL,
                file_type   TEXT DEFAULT '',
                tags        TEXT DEFAULT '[]',
                description TEXT DEFAULT '',
                created_at  REAL,
                modified_at REAL,
                last_synced_at REAL DEFAULT 0
            )
        """)
        self._conn.commit()

    def register(self, entry: FileEntry) -> str:
        """注册或更新一个文件。"""
        now = datetime.now(timezone.utc).timestamp()
        self._conn.execute(
            """INSERT OR REPLACE INTO file_registry
               (name, path, file_type, tags, description, created_at, modified_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.name,
                entry.path,
                entry.file_type,
                json.dumps(entry.tags, ensure_ascii=False),
                entry.metadata.get("description", ""),
                entry.created_at or now,
                now,
            ),
        )
        self._conn.commit()
        return entry.name

    def find(self, name: str | None = None, file_type: str | None = None,
             tag: str | None = None) -> list[FileEntry]:
        sql = "SELECT * FROM file_registry WHERE 1=1"
        params = []
        if name:
            sql += " AND name LIKE ?"
            params.append(f"%{name}%")
        if file_type:
            sql += " AND file_type = ?"
            params.append(file_type)
        if tag:
            sql += " AND tags LIKE ?"
            params.append(f'%"{tag}"%')
        sql += " ORDER BY modified_at DESC"

        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def list_all(self) -> list[FileEntry]:
        rows = self._conn.execute(
            "SELECT * FROM file_registry ORDER BY modified_at DESC"
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def update(self, name: str, **kwargs) -> None:
        allowed = {"path", "file_type", "description", "last_synced_at"}
        sets = []
        params = []
        for k, v in kwargs.items():
            if k in allowed:
                if k == "tags":
                    v = json.dumps(v, ensure_ascii=False)
                sets.append(f"{k} = ?")
                params.append(v)
        if sets:
            params.append(name)
            self._conn.execute(
                f"UPDATE file_registry SET {', '.join(sets)}, modified_at = ? WHERE name = ?",
                params[:-1] + [datetime.now(timezone.utc).timestamp(), name],
            )
            self._conn.commit()

    def unregister(self, name: str) -> bool:
        cur = self._conn.execute("DELETE FROM file_registry WHERE name = ?", (name,))
        self._conn.commit()
        return cur.rowcount > 0

    def get_summary(self) -> str:
        """生成供 LLM 使用的文件列表摘要。"""
        entries = self.list_all()
        if not entries:
            return "（暂无已注册文件）"

        lines = ["已注册的本地文件："]
        for e in entries:
            desc = f" — {e.metadata.get('description', '')}" if e.metadata.get("description") else ""
            tags_str = f" [{', '.join(e.tags)}]" if e.tags else ""
            lines.append(f"  [{e.file_type}] {e.name}{tags_str}{desc}")
        return "\n".join(lines)

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _row_to_entry(row: tuple) -> FileEntry:
        try:
            tags = json.loads(row[3])
        except (json.JSONDecodeError, TypeError):
            tags = []
        return FileEntry(
            name=row[0],
            path=row[1],
            file_type=row[2],
            tags=tags,
            created_at=row[5] or 0,
            modified_at=row[6] or 0,
            metadata={"description": row[4] or ""},
        )
