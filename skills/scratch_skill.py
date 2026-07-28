"""
Scratch Skill —— LLM 的临时草稿纸。
工具间暂存数据：行号映射、列名映射、人员列表、变更追踪等。
"""
from skills.base import BaseSkill


class ScratchSkill(BaseSkill):

    def __init__(self, store, session_id: str = "default"):
        self._store = store
        self._session = session_id

    @property
    def name(self) -> str:
        return "scratch"

    def get_tools(self) -> list[dict]:
        return [
            {"name": "scratch_set", "fn": self.scratch_set,
             "schema": self._s("暂存一条信息（键值对），下次调用时取出", {
                 "key": {"type": "string", "description": "键名，如 row_map / col_map / pending_writes"},
                 "value": {"type": "string", "description": "值，如 JSON 字符串或文本"},
             }, ["key", "value"])},
            {"name": "scratch_get", "fn": self.scratch_get,
             "schema": self._s("取出之前暂存的信息", {
                 "key": {"type": "string", "description": "键名"},
             }, ["key"])},
            {"name": "scratch_delete", "fn": self.scratch_delete,
             "schema": self._s("删除一条暂存", {
                 "key": {"type": "string", "description": "键名"},
             }, ["key"])},
            {"name": "scratch_list", "fn": self.scratch_list,
             "schema": self._s("列出当前会话所有暂存项", {})},
        ]

    def set_session(self, sid: str):
        self._session = sid

    def scratch_set(self, key: str, value: str) -> str:
        return self._store.set(self._session, key, value)

    def scratch_get(self, key: str) -> str:
        return self._store.get(self._session, key)

    def scratch_delete(self, key: str) -> str:
        return self._store.delete(self._session, key)

    def scratch_list(self) -> str:
        items = self._store.list(self._session)
        if not items:
            return "（暂存为空）"
        return "\n".join(f"  📝 {r['key']}: {r['preview']}" for r in items)

    @staticmethod
    def _s(desc, props, req=None):
        return {"type": "function", "function": {
            "description": desc, "parameters": {"type": "object", "properties": props, "required": req or []}}}
