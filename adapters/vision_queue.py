"""
视觉任务队列 —— 批量 GLM/商汤调用时自动入队，后台线程处理。
"""
import sqlite3, uuid, json, threading, time, asyncio
from pathlib import Path
from datetime import datetime, timezone


class VisionQueue:
    """异步视觉任务队列。"""

    def __init__(self, db_path: str = "./data/mother.db", vision_client=None):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS vision_queue (
            id TEXT PRIMARY KEY, image_b64 TEXT, prompt TEXT,
            status TEXT DEFAULT 'pending', result TEXT, error TEXT,
            created_at REAL
        )""")
        self._conn.commit()
        self._client = vision_client
        self._running = False
        self._thread = None

    def start(self):
        """启动后台处理线程。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def add(self, image_b64: str, prompt: str) -> str:
        """加入队列，返回任务ID。"""
        tid = f"vq_{uuid.uuid4().hex[:8]}"
        self._conn.execute(
            "INSERT INTO vision_queue VALUES (?,?,?,?,?,?,?)",
            (tid, image_b64, prompt, "pending", "", "",
             datetime.now(timezone.utc).timestamp()),
        )
        self._conn.commit()
        return tid

    def status(self) -> dict:
        """获取队列状态。"""
        total = self._conn.execute("SELECT COUNT(*) FROM vision_queue").fetchone()[0]
        pending = self._conn.execute("SELECT COUNT(*) FROM vision_queue WHERE status='pending'").fetchone()[0]
        done = self._conn.execute("SELECT COUNT(*) FROM vision_queue WHERE status='done'").fetchone()[0]
        failed = self._conn.execute("SELECT COUNT(*) FROM vision_queue WHERE status='failed'").fetchone()[0]
        return {"total": total, "pending": pending, "done": done, "failed": failed}

    def get_results(self, limit: int = 20) -> list[dict]:
        """获取已完成的任务结果。"""
        rows = self._conn.execute(
            "SELECT id, prompt, result, error, status FROM vision_queue "
            "WHERE status IN ('done','failed') ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [{"id": r[0], "prompt": r[1][:100], "result": r[2][:500],
                 "error": r[3][:200], "status": r[4]} for r in rows]

    def clear(self):
        """清空已完成的任务。"""
        self._conn.execute("DELETE FROM vision_queue WHERE status IN ('done','failed')")
        self._conn.commit()

    def _worker(self):
        """后台线程：逐个处理队列中的 pending 任务。"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while self._running:
            row = self._conn.execute(
                "SELECT id, image_b64, prompt FROM vision_queue WHERE status='pending' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                time.sleep(2)
                continue
            tid, img, prompt = row
            self._conn.execute("UPDATE vision_queue SET status='processing' WHERE id=?", (tid,))
            self._conn.commit()
            try:
                if self._client:
                    result = loop.run_until_complete(self._client.analyze(img, prompt))
                    self._conn.execute(
                        "UPDATE vision_queue SET status='done', result=? WHERE id=?", (result, tid)
                    )
                else:
                    self._conn.execute(
                        "UPDATE vision_queue SET status='failed', error=? WHERE id=?",
                        ("视觉客户端未初始化", tid),
                    )
            except Exception as e:
                self._conn.execute(
                    "UPDATE vision_queue SET status='failed', error=? WHERE id=?",
                    (str(e)[:500], tid),
                )
            self._conn.commit()
        loop.close()

    def close(self):
        self.stop()
        self._conn.close()
