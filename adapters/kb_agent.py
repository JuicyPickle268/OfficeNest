"""
KB Agent——独立提示词，只负责读文件+判断入库。不与通用 Agent 混用，降低幻觉。
通用 Agent 只能 kb_search；KB Agent 才能 kb_add。
"""
import json
from pathlib import Path
from core.mother.engine import MotherEngine
from core.mother.context_builder import ContextBuilder
from core.mother.tool_registry import ToolRegistry
from adapters.office_bridge import OfficeBridge
from adapters.file_bridge import FileBridge
from adapters.llm.deepseek_client import DeepSeekClient
from skills.excel_skill import ExcelSkill
from skills.word_skill import WordSkill
from skills.vision_skill import VisionSkill
from skills.system_skill import SystemSkill
from skills.kb_skill import KnowledgeBaseSkill


def build_kb_agent(cfg, kb) -> MotherEngine:
    """构建 KB Agent。只读工具 + kb_add。"""

    office = OfficeBridge()
    files = FileBridge()

    llm = DeepSeekClient(api_key=cfg.llm.api_key, model=cfg.llm.model,
                         base_url=cfg.llm.base_url, temperature=0.1)  # 低温度=低幻觉

    prompt = """你是知识库管理员。你只有一项工作：把值得长期保存的文档加入知识库。

规则：
1. 读取用户指定的文件或文件夹，提取文本内容
2. 判断内容是否值得入库：
   ✅ 制度/规范/手册/合同模板/参考文档 → 调 kb_add 入库
   ❌ 纯数据/一次性报表/临时文件 → 跳过
3. 入库时给出有意义的 description（如"员工考勤制度"而非"文件1"）
4. 只做入库，不做其他操作。不能修改任何文件
5. 回答简洁——"已入库3个文件，跳过2个"这种格式"""

    context = ContextBuilder(system_prompt=prompt)

    tools = ToolRegistry()
    tools.register(SystemSkill(file_registry=None))  # file_list_dir
    tools.register(ExcelSkill(office))               # excel_read（只读）
    tools.register(WordSkill(office))                # word_read
    tools.register(VisionSkill(
        glm_api_key=getattr(cfg.llm, 'glm_api_key', '')))  # pdf_read
    tools.register(_KBAddSkill(kb))                  # kb_add（唯一写工具）

    return MotherEngine(llm_client=llm, tool_registry=tools,
                        context_builder=context, max_rounds=15)


class _KBAddSkill:
    """KB Agent 专用——只有 kb_add，不给 kb_search。"""
    def __init__(self, kb):
        self._kb = kb

    @property
    def name(self):
        return "kb_add"

    def get_tools(self):
        return [{"name": "kb_add", "fn": self.kb_add,
                 "schema": {"type": "function", "function": {
                     "description": "将文本加入知识库（制度/规范/合同等长期文档）",
                     "parameters": {"type": "object", "properties": {
                         "text": {"type": "string", "description": "要入库的文本"},
                         "source": {"type": "string", "description": "来源文件名"},
                         "description": {"type": "string", "description": "内容描述，如'员工考勤制度'"},
                     }, "required": ["text", "source", "description"]}}}}]

    def kb_add(self, text: str, source: str, description: str) -> str:
        return self._kb.add(text, source, description)
