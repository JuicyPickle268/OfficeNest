"""
OfficeNest 主入口——应用容器 MotherApp + CLI 入口。

架构角色(胶水层):
    组装所有模块（LLM、Office、存储、技能、事件总线）→ 注入引擎 → 暴露 process()

数据流:
    用户消息 → process() → 加载上下文(记忆/文件/历史/用户偏好)
    → engine.process() → Tool Call 循环 → 回复

启动方式:
    python main_qt.py    → Qt 桌面面板
    python main.py --cli → 终端交互模式
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config.schema import load_config
from adapters.office_bridge import OfficeBridge
from adapters.clipboard_bridge import ClipboardBridge
from adapters.file_bridge import FileBridge
from adapters.file_registry import FileRegistry
from adapters.llm.deepseek_client import DeepSeekClient
from core.mother.engine import MotherEngine
from core.mother.context_builder import ContextBuilder
from core.mother.tool_registry import ToolRegistry
from skills.excel_skill import ExcelSkill
from skills.word_skill import WordSkill
from skills.clipboard_skill import ClipboardSkill
from skills.system_skill import SystemSkill
from skills.chart_skill import ChartSkill
from skills.vision_skill import VisionSkill
from skills.workflow_skill import WorkflowSkill, WorkflowStore
from skills.kb_skill import KnowledgeBaseSkill
from adapters.knowledge_base import KnowledgeBase
from adapters.vision_queue import VisionQueue
from adapters.opt_store import OptStore
from skills.opt_skill import OptimizationSkill
from adapters.scratch_store import ScratchStore
from skills.scratch_skill import ScratchSkill
from skills.vba_skill import VBASkill
from skills.powershell_skill import PowerShellSkill
from skills.model_skill import ModelSkill
from skills.formula_skill import FormulaSkill
from adapters.formula_store import FormulaStore
from adapters.memory_store import SQLiteMemoryStore
from core.events.bus import SimpleEventBus
from core.events.event import Event
from core.events.types import EventType


class MotherApp:
    """Mother 应用容器：组装所有模块，提供统一入口。"""

    def __init__(self, config_path: str = "config/default.yaml"):
        self.cfg = load_config(config_path)
        self._config_path = config_path
        self.event_bus = SimpleEventBus()
        self._last_file: str = ""       # 上一次处理的文件
        self._current_file: str = ""    # 当前正在处理的文件

        # 适配器
        self.office = OfficeBridge(auto_backup=self.cfg.office.auto_backup)
        self.clipboard = ClipboardBridge()
        self.files = FileBridge()
        self.file_registry = FileRegistry(self.cfg.storage.db_path)
        self.memory = SQLiteMemoryStore(self.cfg.storage.db_path)

        # LLM
        self.llm = DeepSeekClient(
            api_key=self.cfg.llm.api_key,
            model=self.cfg.llm.model,
            base_url=self.cfg.llm.base_url,
            temperature=self.cfg.llm.temperature,
        )

        # Tool Registry + Skills
        self.tools = ToolRegistry()
        self.tools.register(ExcelSkill(self.office, self.file_registry,
                                       workbooks_dir=self.cfg.office.workbooks_dir))
        self.tools.register(WordSkill(self.office))
        self.tools.register(ClipboardSkill())
        self.tools.register(SystemSkill(self.file_registry,
            zhihu_key=getattr(self.cfg.llm, 'zhihu_api_key', '')))
        self.tools.register(ChartSkill())
        # 视觉队列
        from adapters.llm.vision_client import VisionClient
        self.vision_client = VisionClient(
            glm_key=getattr(self.cfg.llm, 'glm_api_key', ''),
            sense_key=getattr(self.cfg.llm, 'sense_api_key', ''),
        )
        self.vision_queue = VisionQueue(self.cfg.storage.db_path, self.vision_client)
        self.vision_queue.start()
        self.tools.register(VisionSkill(
            glm_api_key=getattr(self.cfg.llm, 'glm_api_key', ''),
            sense_api_key=getattr(self.cfg.llm, 'sense_api_key', ''),
            llm_client=self.llm, queue=self.vision_queue,
        ))
        self._workflow_store = WorkflowStore(self.cfg.storage.db_path)
        self.tools.register(WorkflowSkill(self._workflow_store))

        # 知识库（纯本地 ChromaDB 嵌入，免费）
        self.kb = KnowledgeBase(self.cfg.storage.db_path, "./data/kb")
        self.tools.register(KnowledgeBaseSkill(self.kb))

        # 提示词优化器
        self.opt_store = OptStore(self.cfg.storage.db_path)
        self.tools.register(OptimizationSkill(self.opt_store))

        # 临时草稿纸
        self.scratch = ScratchStore(self.cfg.storage.db_path)
        self.tools.register(ScratchSkill(self.scratch))

        # VBA + PowerShell + 模型管理
        self.tools.register(VBASkill())
        self.tools.register(PowerShellSkill())
        self._model_skill = ModelSkill("config/models.yaml", self._config_path)
        self._model_skill.set_llm_client(self.llm)
        self.tools.register(self._model_skill)

        # 公式计算（LLM 写表达式，计算机安全求值）
        self.formula_store = FormulaStore(self.cfg.storage.db_path)
        self.tools.register(FormulaSkill(self.formula_store))

        # 自动扫描已有文件
        self._scan_and_register_files()

        # Context Builder
        self.context = ContextBuilder(lang=getattr(self.cfg.llm, 'lang', 'zh'),
                                       max_context=self.cfg.llm.context_rounds)

        # Mother Engine
        self.engine = MotherEngine(
            llm_client=self.llm,
            tool_registry=self.tools,
            context_builder=self.context,
            event_bus=self.event_bus,
            max_rounds=self.cfg.llm.max_rounds,
        )

        # 订阅事件
        self.event_bus.subscribe(EventType.TOOL_CALL_START,
            lambda e: print(f"  🔧 {e.data.get('tool', '?')} ...", end=" ", flush=True))
        self.event_bus.subscribe(EventType.TOOL_CALL_DONE,
            lambda e: print("✅"))
        self.event_bus.subscribe(EventType.TOOL_CALL_ERROR,
            lambda e: print(f"❌ {e.data.get('error', '?')}"))

    def shutdown(self):
        """清理所有资源。"""
        from adapters.search_agent import shutdown_agent
        shutdown_agent()
        self.office._sessions.clear()
        self.memory.close()
        if hasattr(self, 'vision_queue'):
            self.vision_queue.close()

    async def process(self, user_input: str, on_token: callable = None,
                      session_id: str = "default", pinned_file: str = "") -> dict:
        """处理一条用户输入，返回完整结果 dict。"""

        # 注入文件上下文（不可见提示，防路径漂移）
        file_hint = ""
        if self._current_file:
            file_hint = f"[当前处理文件: {self._current_file}]"
        if self._last_file and self._last_file != self._current_file:
            file_hint += f" [上次文件: {self._last_file}]"
        if file_hint:
            user_input = f"{file_hint} {user_input}"

        memory = self.memory.get_context()
        file_list = self._get_file_list()
        # 加载该会话历史
        self.memory.ensure_session(session_id)
        history = self.memory.load_history(session_id, 30)

        result = await self.engine.process(
            user_message=user_input,
            memory_context=memory,
            file_list=file_list,
            chat_history=history,
            on_token=on_token,
            pinned_file=pinned_file,
        )

        # 追踪文件：从 tool_calls 中提取 filepath
        for tc in self.engine._last_tool_calls:
            args = tc.arguments if hasattr(tc, 'arguments') else {}
            fp = args.get("filepath", "") or args.get("file_path", "") or args.get("path", "")
            if fp:
                if self._current_file and fp != self._current_file:
                    self._last_file = self._current_file
                self._current_file = fp
                break

        reply = result.get("response", "（无响应）")
        thinking = result.get("thinking", "")

        # 自动保存（思考合入 assistant 消息，不单独存——API 不支持 thinking role）
        self.memory.save_message("user", user_input, session_id)
        if thinking:
            self.memory.save_message("assistant", f"[思考]\n{thinking[:2000]}\n[/思考]\n\n{reply[:1000]}", session_id)
        else:
            self.memory.save_message("assistant", reply[:2000], session_id)

        return result

    def _get_file_list(self) -> str:
        """从注册表获取文件列表供 LLM 参考。"""
        return self.file_registry.get_summary()

    def _scan_and_register_files(self):
        """启动时自动扫描并注册已有文件。"""
        from core.interfaces.file_registry import FileEntry
        for dir_name, file_type, exts in [
            ("workbooks", "excel", ["*.xlsx", "*.xls"]),
            ("output", "word", ["*.docx", "*.doc"]),
            ("templates", "word", ["*.docx", "*.doc"]),
        ]:
            for ext in exts:
                for f in self.files.list_dir(f"./{dir_name}", ext):
                    if not any(e.name == f.name for e in self.file_registry.find(name=f.name)):
                        self.file_registry.register(FileEntry(
                            name=f.name, path=str(f.resolve()),
                            file_type=file_type,
                            metadata={"description": "启动时自动发现"},
                        ))


# ═══════════════════════════════════════════════════
# 终端交互模式
# ═══════════════════════════════════════════════════

async def interactive_mode(app: MotherApp):
    """终端交互循环。"""
    print("=" * 50)
    print("  Mother v2 — 本地 AI 办公助手")
    print(f"  模型: {app.cfg.llm.model}")
    print(f"  Office: {'已就绪' if _check_office() else '未检测到'}")
    print()
    print("  输入指令，Mother 帮你执行。")
    print("  输入 /quit 退出，/clear 清空对话")
    print("=" * 50)

    while True:
        try:
            user_input = input("\n🧑 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue

        if user_input.lower() in ("/quit", "/exit", "/q"):
            print("再见！")
            break

        if user_input.lower() in ("/clear", "/c"):
            app.memory.clear_history()
            print("✅ 对话历史已清空")
            continue

        if user_input.lower() == "/files":
            print(app._get_file_list())
            continue

        print(f"🤖 ", end="", flush=True)
        try:
            result = await app.process(user_input)
            print(f"\n{result.get('response', '（无响应）')}")
        except Exception as e:
            print(f"\n❌ 错误: {e}")


def _check_office() -> bool:
    try:
        import win32com.client
        return True
    except ImportError:
        return False


def launch_panel():
    """启动 tkinter 管理面板。"""
    from panel.admin_panel import MotherPanel
    panel = MotherPanel("config/default.yaml")
    panel.run()


def main():
    """入口函数。"""
    # --qt → Qt 面板
    if "--qt" in sys.argv:
        from panel.panel_qt import main as qt_main
        qt_main()
        return

    # --cli 或带参数 → 终端模式
    if len(sys.argv) > 1:
        if sys.argv[1] == "--cli":
            app = MotherApp()
            asyncio.run(interactive_mode(app))
            return
        else:
            # 单次命令
            app = MotherApp()
            user_input = " ".join(sys.argv[1:])
            reply = asyncio.run(app.process(user_input))
            print(reply.get("response", reply))
            return

    # 默认：启动面板
    launch_panel()


if __name__ == "__main__":
    main()
