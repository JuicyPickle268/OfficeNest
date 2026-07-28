"""
BaseSkill 基类：所有 Skill 的模板。
"""
from abc import ABC, abstractmethod


class BaseSkill(ABC):
    """每个 Skill 继承此类，定义自己的工具。"""

    @abstractmethod
    def get_tools(self) -> list[dict]:
        """
        返回工具列表，格式：
        [
            {
                "name": "excel_create",
                "fn": self.excel_create,
                "schema": {
                    "type": "function",
                    "function": {
                        "description": "创建新的 Excel 文件",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "filepath": {"type": "string", "description": "文件路径"}
                            },
                            "required": ["filepath"]
                        }
                    }
                }
            },
            ...
        ]
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Skill 名称，用于日志标识。"""
        ...
