"""
工作流 Skill——保存成功操作流程，下次直接复用。
"""
import sqlite3, json, uuid
from pathlib import Path
from datetime import datetime, timezone
from skills.base import BaseSkill


class WorkflowStore:
    def __init__(self, db_path: str = "./data/mother.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS workflows (
            id TEXT PRIMARY KEY, name TEXT, description TEXT DEFAULT '',
            steps TEXT DEFAULT '[]', prompt_hint TEXT DEFAULT '',
            created_at REAL, run_count INTEGER DEFAULT 0)""")
        self._conn.commit()

    def save(self, name: str, description: str, steps: list, hint: str = "") -> str:
        wid = f"wf_{uuid.uuid4().hex[:8]}"
        self._conn.execute(
            "INSERT INTO workflows VALUES (?,?,?,?,?,?,?)",
            (wid, name, description, json.dumps(steps, ensure_ascii=False), hint,
             datetime.now(timezone.utc).timestamp(), 0))
        self._conn.commit(); return wid

    def list_all(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, description, run_count FROM workflows ORDER BY created_at DESC").fetchall()
        return [{"id": r[0], "name": r[1], "description": r[2], "run_count": r[3]} for r in rows]

    def get(self, wid: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, name, description, steps, prompt_hint FROM workflows WHERE id=? OR name=?", (wid, wid)
        ).fetchone()
        if not row:
            return None
        return {"id": row[0], "name": row[1], "description": row[2],
                "steps": json.loads(row[3]), "prompt_hint": row[4]}

    def increment(self, wid: str):
        self._conn.execute("UPDATE workflows SET run_count=run_count+1 WHERE id=?", (wid,)); self._conn.commit()


class WorkflowSkill(BaseSkill):
    def __init__(self, store: WorkflowStore):
        self._store = store

    @property
    def name(self) -> str:
        return "workflow"

    def get_tools(self) -> list[dict]:
        return [
            {"name": "workflow_save", "fn": self.workflow_save,
             "schema": self._s("保存当前操作流程为可复用工作流——下次遇到同类任务直接调用，不绕路", {
                 "name": {"type": "string", "description": "工作流名称"},
                 "steps": {"type": "array", "description": "工具调用序列，如['excel_read','excel_write']"},
                 "prompt_hint": {"type": "string", "description": "给AI自己的提示：下次执行时注意什么、参数怎么填"},
             }, ["name", "steps", "prompt_hint"])},
            {"name": "workflow_list", "fn": self.workflow_list,
             "schema": self._s("列出所有已保存的工作流", {})},
            {"name": "workflow_run", "fn": self.workflow_run,
             "schema": self._s("加载一个已保存的工作流（获取步骤+提示词）", {
                 "name": {"type": "string", "description": "工作流名称或ID"},
             }, ["name"])},
        ]

    def workflow_save(self, name: str, steps: list, prompt_hint: str, description: str = "") -> str:
        self._store.save(name, description,
                         [{"tool": s, "order": i} for i, s in enumerate(steps)], prompt_hint)
        return f"✅ 工作流已保存: {name}（下次可以直接运行）"

    def workflow_list(self) -> str:
        items = self._store.list_all()
        return "\n".join(f"  [{r['id'][:12]}] {r['name']} | 运行{r['run_count']}次 | {r['description']}"
                         for r in items) if items else "（暂无工作流）"

    def workflow_run(self, name: str) -> str:
        wf = self._store.get(name)
        if not wf:
            return f"❌ 未找到: {name}"
        self._store.increment(wf["id"])
        steps_desc = " → ".join(s["tool"] for s in wf["steps"])
        return f"📋 工作流「{wf['name']}」\n步骤: {steps_desc}\n提示: {wf['prompt_hint']}"
