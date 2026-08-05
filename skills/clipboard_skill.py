"""
Clipboard Skill：2 个剪切板工具。
"""
from skills.base import BaseSkill
from adapters.clipboard_bridge import ClipboardBridge


class ClipboardSkill(BaseSkill):

    def __init__(self):
        self._clipboard = ClipboardBridge()

    @property
    def name(self) -> str:
        return "clipboard"

    def get_tools(self) -> list[dict]:
        return [
            {"name": "clipboard_read", "fn": self.clipboard_read,
             "schema": self._schema("读取 Windows 剪切板当前文本内容", {})},
            {"name": "clipboard_write", "fn": self.clipboard_write,
             "schema": self._schema("写入文本到 Windows 剪切板", {
                 "text": {"type": "string", "description": "要写入的文本"},
             }, ["text"])},
        ]

    def clipboard_read(self) -> str:
        text = self._clipboard.read_text()
        if not text:
            return "（剪切板为空或内容非文本）"
        return text[:5000]  # 最多返回 5000 字符

    def clipboard_write(self, text: str) -> str:
        self._clipboard.write_text(text)
        return f"✅ 已写入剪切板（{len(text)} 字符）"
