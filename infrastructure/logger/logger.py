"""
日志系统实现。
基于 SQLite，支持五层日志结构。
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone

from core.events.event import Event


class Logger:
    """
    五层日志系统。
    - L1: events — 所有事件
    - L2: tasks — 任务聚合
    - L3: steps — 工具调用步骤
    - L4: error_patterns — 错误模式
    - L5: metrics — 每日指标
    """

    def __init__(self, db_path: str = "./data/mother.db"):
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库：建文件夹、建表。"""
        db_dir = Path(self._db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")

        # 执行 schema.sql
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            self._conn.executescript(schema_path.read_text(encoding="utf-8"))
        self._conn.commit()

    # ── L1: 事件写入 ──

    def log_event(self, event: Event) -> str:
        """写入一条事件。返回 event_id。"""
        d = event.to_dict()
        self._conn.execute(
            """INSERT OR REPLACE INTO events
               (event_id, type, timestamp, source, parent_id, task_id, data, level)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (d["event_id"], d["type"], d["timestamp"], d["source"],
             d["parent_id"], d["task_id"], d["data"], d["level"]),
        )
        self._conn.commit()
        return event.event_id

    def query_events(self, event_type: str | None = None, task_id: str | None = None,
                     limit: int = 50) -> list[dict]:
        """查询事件。"""
        sql = "SELECT * FROM events WHERE 1=1"
        params = []
        if event_type:
            sql += " AND type = ?"
            params.append(event_type)
        if task_id:
            sql += " AND task_id = ?"
            params.append(task_id)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    # ── L2: 任务 ──

    def create_task(self, task_id: str, user_input: str, user_id: str = "") -> None:
        """创建任务记录。"""
        self._conn.execute(
            """INSERT INTO tasks (task_id, user_input, user_id, started_at)
               VALUES (?, ?, ?, ?)""",
            (task_id, user_input, user_id, datetime.now(timezone.utc).timestamp()),
        )
        self._conn.commit()

    def update_task(self, task_id: str, **kwargs) -> None:
        """更新任务字段。"""
        allowed = {"status", "finished_at", "tool_calls", "llm_rounds",
                    "tokens_used", "result", "error"}
        sets = []
        params = []
        for k, v in kwargs.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                params.append(v)
        if sets:
            params.append(task_id)
            self._conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE task_id = ?", params)
            self._conn.commit()

    # ── L3: 步骤 ──

    def create_step(self, step_id: str, task_id: str, tool_name: str,
                    arguments: dict | None = None) -> None:
        """创建步骤记录。"""
        self._conn.execute(
            """INSERT INTO steps (step_id, task_id, tool_name, arguments, started_at)
               VALUES (?, ?, ?, ?, ?)""",
            (step_id, task_id, tool_name,
             json.dumps(arguments or {}, ensure_ascii=False),
             datetime.now(timezone.utc).timestamp()),
        )
        self._conn.commit()

    def update_step(self, step_id: str, **kwargs) -> None:
        """更新步骤字段。"""
        allowed = {"status", "finished_at", "result", "error", "self_healed"}
        sets = []
        params = []
        for k, v in kwargs.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                params.append(v if not isinstance(v, dict) else json.dumps(v, ensure_ascii=False))
        if sets:
            params.append(step_id)
            self._conn.execute(f"UPDATE steps SET {', '.join(sets)} WHERE step_id = ?", params)
            self._conn.commit()

    # ── L4: 错误模式 ──

    def record_error_pattern(self, pattern_id: str, pattern: str, category: str = "",
                              suggestion: str = "") -> None:
        """记录或更新错误模式。"""
        now = datetime.now(timezone.utc).timestamp()
        existing = self._conn.execute(
            "SELECT count FROM error_patterns WHERE pattern_id = ?", (pattern_id,)
        ).fetchone()

        if existing:
            self._conn.execute(
                """UPDATE error_patterns
                   SET count = count + 1, last_seen = ?, suggestion = ?
                   WHERE pattern_id = ?""",
                (now, suggestion, pattern_id),
            )
        else:
            self._conn.execute(
                """INSERT INTO error_patterns
                   (pattern_id, pattern, category, first_seen, last_seen, suggestion)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (pattern_id, pattern, category, now, now, suggestion),
            )
        self._conn.commit()

    # ── L5: 指标 ──

    def upsert_daily_metrics(self, date_str: str | None = None, **kwargs) -> None:
        """更新每日指标。"""
        if date_str is None:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        allowed = {"tasks_total", "tasks_passed", "tasks_failed",
                    "avg_llm_rounds", "avg_latency_ms", "tokens_total",
                    "cost_estimate", "self_heal_count", "self_heal_success"}
        filtered = {k: v for k, v in kwargs.items() if k in allowed}

        if filtered:
            cols = list(filtered.keys())
            vals = list(filtered.values())
            # 使用 excluded. 避免重复绑定参数
            update_parts = [f"{c} = excluded.{c}" for c in cols]
            self._conn.execute(
                f"""INSERT INTO metrics (date, {', '.join(cols)})
                    VALUES (?, {', '.join(['?'] * len(cols))})
                    ON CONFLICT(date) DO UPDATE SET {', '.join(update_parts)}""",
                [date_str] + vals,
            )
            self._conn.commit()

    # ── 工具方法 ──

    def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _row_to_dict(row: tuple) -> dict:
        """将 SQLite 行转为 dict（简化处理）。"""
        keys = ["event_id", "type", "timestamp", "source", "parent_id",
                "task_id", "data", "level"]
        d = dict(zip(keys, row))
        if d.get("data"):
            try:
                d["data"] = json.loads(d["data"])
            except json.JSONDecodeError:
                pass
        return d
