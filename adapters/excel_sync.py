"""
Excel ↔ SQLite 同步引擎。
每次 Excel 操作后同步数据结构到 SQLite，让 LLM 可查询。
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone


class ExcelSync:
    """
    Excel 数据镜像到 SQLite。

    使用方式：
        sync = ExcelSync("./data/mother.db")
        sync.sync_workbook("招聘数据.xlsx", wb_data)
        # wb_data: {"Sheet1": [["姓名","岗位"], ["张三","产品经理"]], ...}

    LLM 可以：
        SELECT * FROM xl_招聘数据_Sheet1 WHERE 岗位 LIKE '%产品%'
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._init_db()

    def _init_db(self):
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")

        # 元数据表：记录哪些 Excel 被同步过
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS _xl_sync_meta (
                file_name TEXT,
                sheet_name TEXT,
                rows INTEGER,
                cols INTEGER,
                synced_at REAL,
                PRIMARY KEY (file_name, sheet_name)
            )
        """)
        self._conn.commit()

    def sync_workbook(self, file_name: str, sheets: dict[str, list[list]]) -> list[str]:
        """
        将整个 Workbook 的所有 Sheet 同步到 SQLite。
        sheets: {"Sheet1": [[row1], [row2], ...], "Sheet2": [[...]]}
        返回：创建的 SQL 表名列表。
        """
        created = []
        now = datetime.now(timezone.utc).timestamp()

        for sheet_name, rows in sheets.items():
            if not rows:
                continue

            table_name = self._sheet_to_table(file_name, sheet_name)

            # 删旧表重建
            self._conn.execute(f"DROP TABLE IF EXISTS [{table_name}]")

            # 用第一行做列名
            headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(rows[0])]
            safe_headers = [self._safe_col(h, i) for i, h in enumerate(headers)]

            col_defs = ", ".join(f"[{h}] TEXT" for h in safe_headers)
            self._conn.execute(f"CREATE TABLE [{table_name}] ({col_defs})")

            # 插入数据
            placeholders = ", ".join("?" * len(safe_headers))
            cols = ", ".join(f"[{h}]" for h in safe_headers)

            for row in rows[1:]:
                # 补齐缺失列
                padded = list(row) + [""] * (len(safe_headers) - len(row))
                self._conn.execute(
                    f"INSERT INTO [{table_name}] ({cols}) VALUES ({placeholders})",
                    padded[:len(safe_headers)]
                )

            # 更新元数据
            self._conn.execute(
                """INSERT OR REPLACE INTO _xl_sync_meta
                   (file_name, sheet_name, rows, cols, synced_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (file_name, sheet_name, len(rows), len(safe_headers), now),
            )
            created.append(table_name)

        self._conn.commit()
        return created

    def query(self, sql: str, limit: int = 100) -> list[dict]:
        """执行只读查询，返回 dict 列表。"""
        safe_sql = sql.strip()
        if not safe_sql.upper().startswith("SELECT"):
            raise ValueError("仅支持 SELECT 查询")

        safe_sql = safe_sql.rstrip(";") + f" LIMIT {limit}"

        cur = self._conn.execute(safe_sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def list_tables(self) -> list[dict]:
        """列出所有已同步的表。"""
        rows = self._conn.execute(
            "SELECT file_name, sheet_name, rows, cols, synced_at FROM _xl_sync_meta ORDER BY synced_at DESC"
        ).fetchall()
        return [{"file": r[0], "sheet": r[1], "rows": r[2], "cols": r[3], "synced_at": r[4]} for r in rows]

    def get_summary(self) -> str:
        """生成供 LLM 使用的摘要。"""
        tables = self.list_tables()
        if not tables:
            return "（未同步任何 Excel 数据）"

        lines = ["已同步的 Excel 数据表："]
        for t in tables:
            # 获取前3行样例
            table_name = self._sheet_to_table(t["file"], t["sheet"])
            try:
                sample = self._conn.execute(
                    f"SELECT * FROM [{table_name}] LIMIT 3"
                ).fetchall()
                col_names = [d[0] for d in self._conn.execute(
                    f"SELECT * FROM [{table_name}] LIMIT 0"
                ).description]
                lines.append(f"  [{table_name}] {t['rows']}行×{t['cols']}列")
                lines.append(f"    列: {', '.join(col_names[:8])}")
            except Exception:
                lines.append(f"  [{table_name}] {t['rows']}行×{t['cols']}列")
        return "\n".join(lines)

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── 内部 ──

    @staticmethod
    def _sheet_to_table(file_name: str, sheet_name: str) -> str:
        """文件名+Sheet名 → SQL 安全表名"""
        base = Path(file_name).stem
        safe = "".join(c if c.isalnum() or c == '_' else '_' for c in f"xl_{base}_{sheet_name}")
        return safe[:64]

    @staticmethod
    def _safe_col(name: str, idx: int) -> str:
        """列名去特殊字符"""
        safe = "".join(c if c.isalnum() or c == '_' else '_' for c in name)
        if not safe or safe[0].isdigit():
            safe = f"col_{idx}"
        return safe[:32]
