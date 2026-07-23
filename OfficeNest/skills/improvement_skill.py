"""
Improvement Skill：当 LLM 发现自己能力不足时，提需求记录。
"""
from skills.base import BaseSkill
from adapters.improvement_tracker import ImprovementTracker


class ImprovementSkill(BaseSkill):

    def __init__(self, tracker: ImprovementTracker):
        self._tracker = tracker

    @property
    def name(self) -> str:
        return "improvement"

    def get_tools(self) -> list[dict]:
        return [
            {"name": "suggest_improvement", "fn": self.suggest_improvement,
             "schema": self._schema("当你发现某个功能缺失或需要改进时，用此工具记录需求。例如：无法删除注册表项、缺少某个工具、某个操作反复失败需要新能力。", {
                 "title": {"type": "string", "description": "需求标题，简洁描述缺什么"},
                 "description": {"type": "string", "description": "详细描述场景和期望"},
             }, ["title", "description"])},
        ]

    def suggest_improvement(self, title: str, description: str = "") -> str:
        imp_id = self._tracker.add(title=title, description=description, source="llm")
        return f"✅ 需求已记录（{imp_id}）：{title}。人类会在「待优化需求」标签页查看和处理。"

    @staticmethod
    def _schema(desc: str, properties: dict, required: list[str] | None = None) -> dict:
        return {
            "type": "function",
            "function": {
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required or [],
                }
            }
        }
