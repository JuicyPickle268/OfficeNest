"""
知识库 Skill——通用 Agent 调 kb_search 查知识库。
入库由 KB Agent（独立提示词）负责，不混用。
"""
from skills.base import BaseSkill


class KnowledgeBaseSkill(BaseSkill):

    def __init__(self, kb):
        self._kb = kb

    @property
    def name(self) -> str:
        return "knowledge"

    def get_tools(self) -> list[dict]:
        return [
            {"name": "kb_search", "fn": self.kb_search,
             "schema": self._s("搜索本地知识库——查公司制度、合同模板、参考文档", {
                 "query": {"type": "string", "description": "搜索关键词"},
             }, ["query"])},
            {"name": "kb_registry", "fn": self.kb_registry,
             "schema": self._s("查看知识库已索引的文件列表", {})},
        ]

    def kb_search(self, query: str) -> str:
        results = self._kb.search(query)
        if not results:
            return f"（知识库中未找到关于'{query}'的内容）"
        lines = []
        for i, r in enumerate(results):
            lines.append(f"{i+1}. [{r['source']}] {r['content'][:200]}")
        return "\n".join(lines)

    def kb_registry(self) -> str:
        items = self._kb.registry()
        if not items:
            return "（知识库为空）"
        return "\n".join(f"  📄 {r['source']} | {r['chunks']}块 | {r['description']}" for r in items)

    @staticmethod
    def _s(desc, props, req=None):
        return {"type": "function", "function": {
            "description": desc, "parameters": {"type": "object", "properties": props, "required": req or []}}}
