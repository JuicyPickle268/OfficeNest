"""
OfficeNest Qt 面板 v3 —— 单屏仪表盘 + 弹窗。
"""
import sys, os, json, asyncio, threading, traceback, re, warnings
from pathlib import Path
from datetime import datetime

warnings.filterwarnings("ignore", message=".*aclose.*")
warnings.filterwarnings("ignore", message=".*SSEDecoder.*")

sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QSpinBox, QCheckBox,
    QComboBox, QTreeWidget, QTreeWidgetItem, QHeaderView, QApplication,
    QMessageBox, QSplitter, QMenu, QListWidget, QListWidgetItem, QCompleter, QDialog,
    QDialogButtonBox, QInputDialog, QLineEdit,
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QStringListModel, QMimeData
from PySide6.QtGui import QFont, QTextCursor, QColor, QTextCharFormat, QPixmap, QImage

from panel.widgets import StreamBuffer, DropLineEdit


class MotherPanelQt(QMainWindow):
    """
    OfficeNest Qt 面板 —— 单屏仪表盘 + 弹窗。

    布局:
        左侧侧边栏（会话列表 + 📋📚⚙＋按钮）
        右侧主区域（聊天区 + 输入框 + 工具栏）

    生命周期:
        __init__ → _init_async → _build_dashboard → _start_engine

    关键组件:
        StreamBuffer   — 流式文本渲染（见 panel/widgets.py）
        DropLineEdit   — 拖放文件 + 粘贴图片（见 panel/widgets.py）
        _send_command  — 消息发送入口（单Agent / 多Agent 路由）
    """

    _signal_fill_at = Signal()

    def __init__(self, config_path: str = "config/default.yaml"):
        super().__init__()
        # 确保用项目根目录的绝对路径
        p = Path(config_path)
        if not p.is_absolute():
            p = Path(__file__).parent.parent / p
        self._config_path = str(p.resolve())

        from config.schema import load_config
        self.cfg = load_config(self._config_path)
        self.logger = None
        self._app = None
        self._event_count = 0

        self.setWindowTitle("OfficeNest")
        self.resize(1100, 720)

        self._current_session = "default"
        self._session_names: list[str] = []

        # 左右分栏：侧边栏 + 仪表盘
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左栏：会话侧边栏
        self._sidebar = QWidget()
        side_layout = QVBoxLayout(self._sidebar)
        side_layout.setContentsMargins(4, 4, 4, 4)
        side_lbl = QLabel("💬 会话")
        side_lbl.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        side_layout.addWidget(side_lbl)
        self._session_list = QListWidget()
        self._session_list.setStyleSheet(
            "QListWidget { background-color: #1e1e1e; color: #d4d4d4; border: 1px solid #333; }"
            "QListWidget::item:selected { background-color: #264f78; }"
        )
        self._session_list.itemClicked.connect(self._on_session_clicked)
        self._session_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._session_list.customContextMenuRequested.connect(self._session_menu)
        side_layout.addWidget(self._session_list, 1)
        # 底部弹窗按钮
        btn_row = QHBoxLayout()
        for text, handler in [("📋", self._show_log), ("📚", self._show_kb), ("⚙", self._show_settings)]:
            b = QPushButton(text); b.setFixedWidth(36); b.setToolTip(text); b.clicked.connect(handler)
            btn_row.addWidget(b)
        btn_new = QPushButton("＋"); btn_new.clicked.connect(self._new_session)
        btn_row.addWidget(btn_new)
        side_layout.addLayout(btn_row)
        splitter.addWidget(self._sidebar)

        # 右栏：仪表盘
        self._dash = QWidget()
        splitter.addWidget(self._dash)
        splitter.setSizes([180, 920])
        self.setCentralWidget(splitter)

        self._dash_buffer: StreamBuffer | None = None
        self._pinned_file = ""
        self._last_at_text = ""

        self._signal_fill_at.connect(self._auto_fill_at)

        # 50ms 后异步构建仪表盘
        QTimer.singleShot(50, self._init_async)

    # ═══════════════════════════════════════
    # 异步初始化
    # ═══════════════════════════════════════

    def _init_async(self):
        # 配置已在 __init__ 中加载
        try:
            from infrastructure.logger.logger import Logger
            self.logger = Logger(self.cfg.storage.db_path)
        except Exception:
            pass
        self._build_dashboard()

    # ── 会话管理 ──

    def _refresh_sessions(self):
        """刷新侧边栏会话列表。"""
        self._session_list.clear()
        self._session_map: dict[str, str] = {"default": "默认"}  # id → title
        if self._app and self._app.memory:
            try:
                sessions = self._app.memory.list_sessions()
                for s in sessions:
                    self._session_map[s["id"]] = s.get("title", s["id"])
            except Exception:
                pass
        for sid, title in self._session_map.items():
            item = QListWidgetItem(f"📁 {title}")
            item.setData(Qt.ItemDataRole.UserRole, sid)  # 存 ID
            if sid == self._current_session:
                item.setSelected(True)
            self._session_list.addItem(item)

    def _on_session_clicked(self, item: QListWidgetItem):
        sid = item.data(Qt.ItemDataRole.UserRole)
        if not sid or sid == self._current_session:
            return
        self._current_session = sid
        self._log("INFO", f"切换到会话: {self._session_map.get(sid, sid)}")
        self._dash_log.clear()
        self._load_history()
        self._refresh_sessions()
        if self._app:
            for info in self._app.tools._tools.values():
                skill = info.get("skill")
                if hasattr(skill, "set_session"):
                    skill.set_session(sid)

    def _new_session(self):
        if not self._app:
            return
        sid = self._app.memory.create_session(f"会话 {datetime.now().strftime('%m%d %H:%M')}")
        self._current_session = sid
        self._dash_log.clear()
        self._log("INFO", f"新建会话: {sid}")
        self._refresh_sessions()
        if self._app:
            for info in self._app.tools._tools.values():
                skill = info.get("skill")
                if hasattr(skill, "set_session"):
                    skill.set_session(sid)

    def _session_menu(self, pos):
        item = self._session_list.itemAt(pos)
        if not item:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if not sid or sid == "default":
            return
        title = self._session_map.get(sid, sid)
        menu = QMenu()
        act_rename = menu.addAction("✏️ 重命名")
        act_delete = menu.addAction(f"🗑 删除「{title}」")
        action = menu.exec(self._session_list.viewport().mapToGlobal(pos))
        if action == act_rename:
            self._rename_session(sid)
        elif action == act_delete:
            self._delete_session(sid)

    def _rename_session(self, sid: str):
        from PySide6.QtWidgets import QInputDialog
        old_title = self._session_map.get(sid, sid)
        new_title, ok = QInputDialog.getText(self, "重命名会话", "新名称:", text=old_title)
        if ok and new_title.strip() and new_title.strip() != old_title:
            if self._app:
                self._app.memory.rename_session(sid, new_title.strip())
            self._refresh_sessions()

    def _delete_session(self, sid: str):
        title = self._session_map.get(sid, sid)
        reply = QMessageBox.question(self, "确认删除",
            f"确定要删除会话「{title}」及其所有对话记录吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            if self._app:
                self._app.memory.delete_session(sid)
            if self._current_session == sid:
                self._current_session = "default"
                self._dash_log.clear()
                self._load_history()
            self._refresh_sessions()

    def _refresh_model_dropdown(self):
        """从 models.yaml 刷新下拉框（LLM model_add 后可动态更新）。"""
        current = self._model_dropdown.currentText() if self._model_dropdown.count() > 0 else ""
        self._model_dropdown.blockSignals(True)
        self._model_dropdown.clear()
        self._providers_cache = {}
        try:
            import yaml
            mp = Path(self._config_path).parent / "models.yaml"
            if mp.exists():
                data = yaml.safe_load(open(str(mp), "r", encoding="utf-8"))
                yaml_current = data.get("current", "")
                for prov_name, prov in data.get("providers", {}).items():
                    self._providers_cache[prov_name] = prov
                    for m in prov.get("models", []):
                        label = f"{prov_name}/{m['name']}"
                        self._model_dropdown.addItem(label)
                        if m["name"] == yaml_current and not current:
                            self._model_dropdown.setCurrentText(label)
                        elif label == current:
                            self._model_dropdown.setCurrentText(label)
        except Exception:
            self._model_dropdown.addItems(["deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash"])
        self._model_dropdown.blockSignals(False)

    def _on_model_changed(self, text: str):
        """热切换模型——运行时也可切。"""
        if not text or "/" not in text:
            return
        if not self._app:
            return  # 引擎未启动，不切换
        provider, model = text.split("/", 1)
        prov_info = self._providers_cache.get(provider, {})
        base_url = prov_info.get("base_url", "https://api.deepseek.com/v1")

        # 找 Key
        key_map = {"deepseek": "api_key", "openai": "openai_api_key", "glm": "glm_api_key",
                   "zhipu": "glm_api_key", "zhihu": "zhihu_api_key"}
        config_key = key_map.get(provider, f"{provider}_api_key")
        api_key = getattr(self.cfg.llm, config_key, "") or self.cfg.llm.api_key

        if not api_key:
            self._log("ERROR", f"缺少 {provider} 的 API Key，请在设置页填写或用 key_set")
            return

        # 热切换 LLM client
        self._app.llm._model = model
        self._app.llm._base_url = base_url
        self._app.llm._api_key = api_key
        self._update_status("引擎", f"● {provider}/{model}")
        self._log("INFO", f"模型已切换: {provider}/{model}")

    # ═══════════════════════════════════════
    # 仪表盘
    # ═══════════════════════════════════════
        self._tabs.setCurrentIndex(index)

    # ═══════════════════════════════════════
    # Tab 0: 仪表盘
    # ═══════════════════════════════════════

    def _build_dashboard(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 4)

        # 状态栏
        status = QHBoxLayout()
        self._status_labels: dict[str, QLabel] = {}
        for key, default in [("引擎", "● 待启动"), ("pywin32", "● 检测中"),
                               ("openpyxl", "● 检测中"), ("openai", "● 检测中"),
                               ("飞书", "● 未连接"), ("事件", "0")]:
            lbl = QLabel(f"{key} {default}")
            lbl.setFont(QFont("Microsoft YaHei", 9))
            status.addWidget(lbl)
            self._status_labels[key] = lbl
        status.addStretch()
        layout.addLayout(status)

        # 仪表盘主体：左右分栏
        # 日志区
        self._dash_log = QTextEdit()
        self._dash_log.setReadOnly(True)
        self._dash_log.setFont(QFont("Consolas", 9))
        self._dash_log.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #d4d4d4; border: 1px solid #333; }"
        )
        layout.addWidget(self._dash_log, 1)
        self._dash_buffer = StreamBuffer(self._dash_log)

        # 按钮
        btn_row = QHBoxLayout()
        self._model_dropdown = QComboBox()
        self._model_dropdown.setMinimumWidth(160)
        self._model_dropdown.setStyleSheet(
            "QComboBox { background-color: #2d2d2d; color: #d4d4d4; border: 1px solid #444; padding: 2px; }"
        )
        self._refresh_model_dropdown()
        self._model_dropdown.currentTextChanged.connect(self._on_model_changed)
        btn_row.addWidget(self._model_dropdown)
        self.btn_stop = QPushButton("■ 中断")
        self.btn_stop.clicked.connect(self._stop_engine)
        self.btn_web = QPushButton("🌐")
        self.btn_web.setToolTip("启动手机端 Chainlit 服务")
        self.btn_web.clicked.connect(self._start_chainlit)
        btn_row.addWidget(self.btn_stop)
        btn_row.addWidget(self.btn_web)
        btn_row.addStretch()
        self._btn_think = QPushButton("💭 思考")
        self._btn_think.setCheckable(True)
        self._btn_think.setChecked(True)
        self._btn_think.toggled.connect(self._toggle_thinking)
        self._btn_think.setFixedWidth(80)
        btn_row.addWidget(self._btn_think)
        btn_clear = QPushButton("清空日志")
        btn_clear.clicked.connect(lambda: self._dash_log.clear())
        btn_row.addWidget(btn_clear)
        layout.addLayout(btn_row)

        # 文件引用栏
        pin_row = QHBoxLayout()
        pin_row.addWidget(QLabel("📌 锁定文件:"))
        self._pinned_file_input = DropLineEdit()
        self._pinned_file_input.setPlaceholderText("输入文件路径，锁定后所有操作围绕此文件展开...")
        self._pinned_file_input.setFont(QFont("Consolas", 9))
        self._pinned_file_input.setStyleSheet(
            "QLineEdit { background-color: #2d2d2d; color: #4ec9b0; border: 1px solid #444; padding: 2px; }"
        )
        self._pinned_file_input.setEnabled(False)
        self._pinned_file_input.returnPressed.connect(self._pin_file)
        pin_row.addWidget(self._pinned_file_input, 1)
        btn_pin = QPushButton("锁定")
        btn_pin.setFixedWidth(50)
        btn_pin.clicked.connect(self._pin_file)
        self._btn_pin = btn_pin
        pin_row.addWidget(btn_pin)
        btn_unpin = QPushButton("清除")
        btn_unpin.setFixedWidth(50)
        btn_unpin.clicked.connect(self._unpin_file)
        self._btn_unpin = btn_unpin
        pin_row.addWidget(btn_unpin)
        layout.addLayout(pin_row)

        # 命令输入
        cmd_row = QHBoxLayout()
        self.cmd_input = DropLineEdit()
        self.cmd_input.setPlaceholderText("输入指令，Enter 发送...")
        self.cmd_input.setFont(QFont("Consolas", 11))
        self.cmd_input.setStyleSheet(
            "QLineEdit { background-color: #2d2d2d; color: #d4d4d4; border: 1px solid #444; padding: 4px; }"
        )
        self.cmd_input.returnPressed.connect(self._send_command)
        self.cmd_input.image_pasted.connect(self._on_image_pasted)
        # @ 补全
        self._at_completer = QCompleter([], self)
        self._at_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._at_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._at_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.cmd_input.setCompleter(self._at_completer)
        self.cmd_input.textChanged.connect(self._on_cmd_text_changed)
        self.btn_send = QPushButton("发送")
        self.btn_send.clicked.connect(self._send_command)
        cmd_row.addWidget(self.cmd_input, 1)
        cmd_row.addWidget(self.btn_send)
        layout.addLayout(cmd_row)

        self._dash.setLayout(layout)

        self._log("INFO", "OfficeNest 控制台已就绪")
        if self._dash_buffer:
            self._dash_buffer.flush_now()

        # 状态刷新
        self._status_timer = QTimer()
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start(2000)

        self._refresh_status()

        # 自动启动引擎
        QTimer.singleShot(500, self._start_engine)

    def _toggle_thinking(self, checked: bool):
        if self._dash_buffer:
            self._dash_buffer.set_thinking_visible(checked)

    # ── 弹窗 ──

    def _show_log(self):
        dlg = QDialog(self); dlg.setWindowTitle("📋 日志"); dlg.resize(800, 500)
        layout = QVBoxLayout(dlg)
        tree = QTreeWidget(); tree.setColumnCount(3)
        tree.setHeaderLabels(["时间", "类型", "详情"])
        tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        if self.logger:
            try:
                rows = self.logger._conn.execute(
                    "SELECT timestamp, type, data FROM events ORDER BY timestamp DESC LIMIT 200"
                ).fetchall()
                for ts, etype, data in rows:
                    ts_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else ""
                    QTreeWidgetItem(tree, [ts_str, etype.split(".")[-1][:12], str(data)[:120]])
            except Exception: pass
        layout.addWidget(tree)
        btn = QPushButton("关闭"); btn.clicked.connect(dlg.close); layout.addWidget(btn)
        dlg.exec()

    def _show_kb(self):
        dlg = QDialog(self); dlg.setWindowTitle("📚 知识库"); dlg.resize(700, 450)
        layout = QVBoxLayout(dlg)
        tree = QTreeWidget(); tree.setColumnCount(4)
        tree.setHeaderLabels(["来源", "描述", "分块数", "入库时间"])
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        if self._app and self._app.kb:
            try:
                for r in self._app.kb.registry():
                    ts = datetime.fromtimestamp(r["created_at"]).strftime("%Y-%m-%d %H:%M") if r.get("created_at") else ""
                    QTreeWidgetItem(tree, [r.get("source",""), r.get("description",""), str(r.get("chunks",0)), ts])
            except Exception: pass
        layout.addWidget(tree)
        btn = QPushButton("关闭"); btn.clicked.connect(dlg.close); layout.addWidget(btn)
        dlg.exec()

    def _show_settings(self):
        dlg = QDialog(self); dlg.setWindowTitle("⚙ 设置"); dlg.resize(450, 400)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("DeepSeek Key:"))
        ds = QLineEdit(self.cfg.llm.api_key); ds.setEchoMode(QLineEdit.EchoMode.Password); layout.addWidget(ds)
        layout.addWidget(QLabel("GLM Key:"))
        gl = QLineEdit(getattr(self.cfg.llm, 'glm_api_key','')); gl.setEchoMode(QLineEdit.EchoMode.Password); layout.addWidget(gl)
        layout.addWidget(QLabel("商汤 Key:"))
        se = QLineEdit(getattr(self.cfg.llm, 'sense_api_key','')); se.setEchoMode(QLineEdit.EchoMode.Password); layout.addWidget(se)
        layout.addWidget(QLabel("知乎 Key:"))
        zh = QLineEdit(getattr(self.cfg.llm, 'zhihu_api_key','')); zh.setEchoMode(QLineEdit.EchoMode.Password); layout.addWidget(zh)
        btn = QPushButton("💾 保存"); btn.clicked.connect(lambda: self._save_keys(dlg, ds.text(), gl.text(), se.text(), zh.text()))
        layout.addWidget(btn)
        dlg.exec()

    def _save_keys(self, dlg, ds_key, glm_key, sense_key, zhihu_key):
        self._up_yaml("llm", {"api_key": ds_key, "glm_api_key": glm_key, "sense_api_key": sense_key, "zhihu_api_key": zhihu_key})
        dlg.close()
        self._log("INFO", "✅ 设置已保存")

    def _log(self, level: str, msg: str):
        if self._dash_buffer:
            ts = datetime.now().strftime("%H:%M:%S")
            self._dash_buffer.feed("TS", f"[{ts}] ")
            self._dash_buffer.feed_line(level, msg)

    def _refresh_status(self):
        try:
            self._update_status("事件", str(self._event_count))
            for mod_name, pkg in [("pywin32", "win32com"), ("openpyxl", "openpyxl"), ("openai", "openai")]:
                try:
                    __import__(pkg)
                    self._update_status(mod_name, "● 已安装")
                except ImportError:
                    self._update_status(mod_name, "● 未安装")
        except RuntimeError:
            pass

    def _update_status(self, key: str, val: str):
        if key in self._status_labels:
            try:
                self._status_labels[key].setText(f"{key} {val}")
            except RuntimeError:
                pass

    # ── 启停 ──

    def _start_engine(self):
        if self._app:
            return
        selected = self._model_dropdown.currentText()
        if "/" not in selected:
            return
        provider, model = selected.split("/", 1)
        prov_info = self._providers_cache.get(provider, {})
        base_url = prov_info.get("base_url", "https://api.deepseek.com/v1")
        key_map = {"deepseek": "api_key", "openai": "openai_api_key", "glm": "glm_api_key",
                   "zhipu": "glm_api_key", "zhihu": "zhihu_api_key"}
        config_key = key_map.get(provider, f"{provider}_api_key")
        api_key = getattr(self.cfg.llm, config_key, "") or self.cfg.llm.api_key
        if not api_key:
            QMessageBox.warning(self, "缺少 API Key", f"请先在设置页填写 {provider} 的 API Key")
            return
        self.cfg.llm.model = model
        try:
            from main import MotherApp
            self._app = MotherApp(self._config_path)
            self._app.llm._model = model
            self._app.llm._base_url = base_url
            self._app.llm._api_key = api_key
            if getattr(self.cfg.office, 'confirm_dangerous', True):
                self._app.engine.set_confirm_handler(self._on_dangerous_action)
        except Exception as e:
            self._log("ERROR", f"引擎初始化失败: {e}")
            return
        self.cmd_input.setFocus()
        self._update_status("引擎", "● 运行中")
        self._log("INFO", f"引擎已启动 | {provider}/{model}")

        # 加载会话列表和历史
        self._refresh_sessions()
        self._load_history()
        if self._app.feishu:
            self._app.feishu.start()
            self._update_status("飞书", "● 连接中...")

    def _stop_engine(self):
        """中断当前输出，不关闭引擎。"""
        if not self._app:
            return
        self._app.engine.cancel()
        self._log("INFO", "⏹ 已中断当前输出")

    def _start_chainlit(self):
        """在后台线程启动 Chainlit 手机端服务。"""
        if not self._app:
            self._log("INFO", "请先启动引擎")
            return
        import subprocess, threading
        def _run():
            try:
                subprocess.run(
                    ["chainlit", "run", "panel/chainlit_app.py", "--host", "0.0.0.0", "--port", "8000"],
                    cwd=str(Path(__file__).parent.parent),
                    capture_output=False,
                )
            except Exception as e:
                self._log("ERROR", f"Chainlit 启动失败: {e}")
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        import socket
        ip = "127.0.0.1"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            pass
        self._log("INFO", f"🌐 Chainlit 手机端: http://{ip}:8000")

    def _load_history(self):
        """加载最近的对话历史并显示。"""
        if not self._app:
            return
        try:
            msgs = self._app.memory.load_history(self._current_session, 30)
            if not msgs:
                return
            self._dash_buffer.feed("TS", "── 历史对话 ──\n")
            for m in msgs:
                role = m.get("role", "")
                content = m.get("content", "")
                if role == "user":
                    self._dash_buffer.feed_line("USER", f"🧑 {content[:200]}")
                else:
                    # 提取思考内容（[思考]...[/思考]）
                    import re
                    think_match = re.search(r'\[思考\]\n(.*?)\n\[/思考\]', content or "", re.DOTALL)
                    if think_match:
                        self._dash_buffer.feed_line("THINK", f"💭 {think_match.group(1)[:300]}")
                        content = content.replace(think_match.group(0), "").strip()
                    self._dash_buffer.feed_line("BOT", f"🤖 {content[:300]}")
            self._dash_buffer.feed("TS", "── 以上为历史 ──\n\n")
            self._dash_buffer.flush_now()
        except Exception:
            pass

    def _on_cmd_text_changed(self, text: str):
        """检测 @ 符号，弹出会话补全。"""
        last_at = text.rfind("@")
        if last_at >= 0 and (last_at == 0 or text[last_at - 1].isspace()):
            after_at = text[last_at + 1:]
            if " " not in after_at:
                titles = [f"@{title}" for title in self._session_map.values()]
                model = QStringListModel(titles)
                self._at_completer.setModel(model)
                if after_at:
                    self._at_completer.complete()
                return
        self._at_completer.setModel(QStringListModel([]))

    def _on_image_pasted(self, b64: str):
        """粘贴图片后暂存，下一次 _send_command 自动带上。"""
        self._pending_image = b64
        self._log("INFO", "📷 图片已粘贴，输入文字或直接 Enter 发送")

    def _send_command(self):
        text = self.cmd_input.text().strip()
        # 附上粘贴的图片
        image_b64 = getattr(self, '_pending_image', '')
        self._pending_image = ''
        if image_b64:
            text = f"[图片: base64, 前200字符: {image_b64[:200]}] {text}" if text else "分析这张图片"
            # 完整 base64 存在 scratch 里供 LLM 取用
            if self._app and self._app.scratch:
                try:
                    self._app.scratch.set("default", "_last_image", image_b64[:5000])
                except Exception:
                    pass
        if not text:
            return

        import re
        at_mentions = re.findall(r"@(\S+)", text)
        at_prefix = " ".join(f"@{m}" for m in at_mentions) + " " if at_mentions else ""
        self._last_at_text = at_prefix  # 记住，下次自动填充
        self.cmd_input.clear()

        # 多 Agent 模式
        if at_mentions and self._app:
            self._run_multi_agent(text, at_mentions)
            return

        # 单 Agent 模式（原有逻辑）
        self._log("USER", f"🧑 {text[:200]}")
        if not self._app:
            self._log("INFO", "引擎未启动")
            return
        self._run_agent(text, self._current_session)

    def _auto_fill_at(self):
        """回复完成后，自动填充上次的 @ 前缀到输入框。"""
        if self._last_at_text:
            self.cmd_input.setText(self._last_at_text)
            self.cmd_input.setFocus()

    def _run_multi_agent(self, text: str, at_mentions: list[str]):
        """多 Agent 轮询：每个被 @ 的 Agent 基于共享历史 + 私有上下文回复。"""
        import re
        clean_text = re.sub(r"@\S+\s*", "", text).strip()
        title_to_id = {v: k for k, v in self._session_map.items()}
        shared_history = self._grab_shared_history()

        agents_info = []
        for at_name in at_mentions:
            sid = title_to_id.get(at_name)
            if not sid:
                self._log("INFO", f"@会话「{at_name}」不存在")
                continue
            ctx = ""
            try:
                hist = self._app.memory.load_history(sid, 6)
                if hist:
                    ctx += "该Agent最近的对话:\n" + "\n".join(
                        f"  {m['role']}: {m['content'][:100]}" for m in hist[-3:]
                    )
                if self._app.scratch:
                    items = self._app.scratch.list(sid)
                    if items:
                        ctx += f"\n暂存: {', '.join(r['key'] for r in items)}"
            except Exception:
                pass
            agent_msg = clean_text
            if shared_history:
                agent_msg = f"{shared_history}\n---\n{ctx}\n---\n当前指令: {clean_text}"
            elif ctx:
                agent_msg = f"{ctx}\n---\n当前指令: {clean_text}"
            agents_info.append((at_name, sid, agent_msg))

        if not agents_info:
            return

        self._log("USER", f"🧑 {text[:150]}")
        for at_name, _, _ in agents_info:
            self._log("INFO", f"🤖 @{at_name} 正在思考...")

        def _run_all():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            for at_name, sid, agent_msg in agents_info:
                try:
                    result = loop.run_until_complete(
                        self._app.process(agent_msg, session_id=sid)
                    )
                    reply = result.get("response", "")[:800]
                    from adapters.table_renderer import detect_and_render
                    for line in detect_and_render(reply).split("\n"):
                        self._dash_buffer.feed_line("BOT", f"🤖{at_name}: {line}")
                except Exception as e:
                    self._dash_buffer.feed_line("ERROR", f"🤖{at_name}: ❌ {e}")
            self._signal_fill_at.emit()
            try:
                pending = asyncio.all_tasks(loop)
                for t in pending: t.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()

        threading.Thread(target=_run_all, daemon=True).start()

    def _run_agent(self, text: str, session_id: str):
        """单 Agent 执行（原有逻辑）。"""
        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                def on_token(ttype: str, token: str):
                    tag_map = {"thinking": "THINK", "content": "BOT", "tool": "TOOL"}
                    tag = tag_map.get(ttype, "INFO")
                    if ttype == "tool":
                        prefix = " 🔧" if "chart" not in token.lower() else " 📊"
                        tag = "CHART" if "chart" in token.lower() else "TOOL"
                        self._dash_buffer.feed(tag, f"{prefix}{token}")
                    elif ttype == "content":
                        self._dash_buffer.feed(tag, token)
                    else:
                        self._dash_buffer.feed(tag, token)

                result = loop.run_until_complete(
                    self._app.process(text, on_token=on_token, pinned_file=self._pinned_file, session_id=session_id)
                )
                reply = result.get("response", "")
                from adapters.table_renderer import detect_and_render
                for line in detect_and_render(reply).split("\n"):
                    self._dash_buffer.feed_line("BOT", line)
                self._log("INFO", f"轮次:{result.get('rounds',0)} 工具:{result.get('tool_calls',0)}")
            except Exception:
                self._log("ERROR", traceback.format_exc()[-200:])
            finally:
                try:
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception:
                    pass
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass
                loop.close()
                self._signal_fill_at.emit()

        threading.Thread(target=_run, daemon=True).start()

    def _grab_shared_history(self) -> str:
        """抓取当前日志区最近消息作为共享上下文。"""
        try:
            text = self._dash_log.toPlainText()
            lines = text.split("\n")
            recent = [l for l in lines[-20:] if l.strip() and not l.startswith("──")]
            if recent:
                return "共享聊天记录:\n" + "\n".join(recent[-8:])
        except Exception:
            pass
        return ""

    def _pin_file(self):
        path = self._pinned_file_input.text().strip().strip('"').strip("'")
        if not path:
            return
        self._pinned_file = path
        self._pinned_file_input.setStyleSheet(
            "QLineEdit { background-color: #1a3a1a; color: #4ec9b0; border: 1px solid #4ec9b0; padding: 2px; }"
        )
        self._log("INFO", f"📌 已锁定文件: {path}")
        # 同步到 ExcelSkill 的工具层文件锁
        if self._app and self._app.tools:
            for info in self._app.tools._tools.values():
                skill = info.get("skill")
                if hasattr(skill, "set_locked_file"):
                    skill.set_locked_file(path)

    def _unpin_file(self):
        self._pinned_file = ""
        self._pinned_file_input.clear()
        self._pinned_file_input.setStyleSheet(
            "QLineEdit { background-color: #2d2d2d; color: #4ec9b0; border: 1px solid #444; padding: 2px; }"
        )
        self._log("INFO", "📌 已解除文件锁定")
        if self._app and self._app.tools:
            for info in self._app.tools._tools.values():
                skill = info.get("skill")
                if hasattr(skill, "set_locked_file"):
                    skill.set_locked_file("")

    async def _on_dangerous_action(self, tool_name: str, args: dict) -> bool:
        """危险操作确认。非主线程用信号量等待，避免 QMessageBox 死锁。"""
        import threading
        result = threading.Event()
        approved = [True]  # 默认允许

        def _show():
            reply = QMessageBox.question(self, "⚠️ 危险操作",
                f"{tool_name}\n参数: {args}\n\n是否允许？\n（5秒无操作自动通过）")
            approved[0] = (reply == QMessageBox.StandardButton.Yes)
            result.set()

        # 主线程弹窗
        QTimer.singleShot(0, _show)
        # 等待最多 5 秒
        result.wait(timeout=5)
        return approved[0]

    # ═══════════════════════════════════════
    # Tab 1: 日志
    # ═══════════════════════════════════════

    def _build_log(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._log_tree = QTreeWidget()
        self._log_tree.setColumnCount(3)
        self._log_tree.setHeaderLabels(["时间", "类型", "详情"])
        self._log_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._log_tree)
        btn = QPushButton("刷新")
        btn.clicked.connect(self._refresh_log)
        layout.addWidget(btn)
        return tab

    def _refresh_log(self):
        self._log_tree.clear()
        if not self.logger:
            return
        try:
            rows = self.logger._conn.execute(
                "SELECT timestamp, type, data FROM events ORDER BY timestamp DESC LIMIT 200"
            ).fetchall()
        except Exception:
            return
        for ts, etype, data in rows:
            ts_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else ""
            QTreeWidgetItem(self._log_tree, [ts_str, etype.split(".")[-1][:12], str(data)[:80]])

    # ═══════════════════════════════════════
    # Tab 2: 优化建议
    # ═══════════════════════════════════════

    def _build_suggestions(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 工具栏：筛选 + 清空
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("工具:"))
        self._sug_filter = QComboBox()
        self._sug_filter.addItem("全部")
        self._sug_filter.currentIndexChanged.connect(lambda: self._refresh_suggestions())
        toolbar.addWidget(self._sug_filter)
        toolbar.addStretch()
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self._clear_suggestions)
        toolbar.addWidget(btn_clear)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self._refresh_suggestions)
        toolbar.addWidget(btn_refresh)
        layout.addLayout(toolbar)

        self._sug_tree = QTreeWidget()
        self._sug_tree.setColumnCount(4)
        self._sug_tree.setHeaderLabels(["工具", "建议内容", "原因", "严重度"])
        self._sug_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._sug_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._sug_tree.customContextMenuRequested.connect(self._sug_menu)
        layout.addWidget(self._sug_tree)
        return tab

    def _refresh_suggestions(self):
        self._sug_tree.clear()
        # 同步工具注册表到筛选下拉
        self._sync_tool_filter()

        tool_filter = self._sug_filter.currentText()
        if tool_filter == "全部":
            tool_filter = ""

        try:
            if self._app and self._app.opt_store:
                rows = self._app.opt_store.get_all(tool_filter)
            else:
                import sqlite3
                db_path = str(Path(self._config_path).parent / "data" / "mother.db")
                conn = sqlite3.connect(db_path)
                if tool_filter:
                    rows = conn.execute(
                        "SELECT id, tool, suggestion, reason, severity FROM opt_suggestions "
                        "WHERE applied=0 AND tool=? ORDER BY severity DESC, created_at DESC",
                        (tool_filter,)
                    ).fetchall()
                    rows = [{"id": r[0], "tool": r[1], "suggestion": r[2], "reason": r[3], "severity": r[4]} for r in rows]
                else:
                    rows = conn.execute(
                        "SELECT id, tool, suggestion, reason, severity FROM opt_suggestions "
                        "WHERE applied=0 ORDER BY severity DESC, created_at DESC"
                    ).fetchall()
                    rows = [{"id": r[0], "tool": r[1], "suggestion": r[2], "reason": r[3], "severity": r[4]} for r in rows]
                conn.close()
        except Exception:
            return

        for r in rows:
            stars = "★" * r["severity"] + "☆" * (3 - r["severity"])
            item = QTreeWidgetItem([r["tool"], r["suggestion"], r.get("reason", ""), stars])
            item.setData(0, Qt.ItemDataRole.UserRole, r["id"])
            self._sug_tree.addTopLevelItem(item)

    def _sync_tool_filter(self):
        """同步工具注册表到筛选下拉框。"""
        current = self._sug_filter.currentText()
        self._sug_filter.blockSignals(True)
        self._sug_filter.clear()
        self._sug_filter.addItem("全部")
        if self._app and self._app.tools:
            tool_names = sorted(set(
                t["function"]["name"] for t in self._app.tools.list_tools()
            ))
            self._sug_filter.addItems(tool_names)
        idx = self._sug_filter.findText(current)
        if idx >= 0:
            self._sug_filter.setCurrentIndex(idx)
        self._sug_filter.blockSignals(False)

    def _sug_menu(self, pos):
        item = self._sug_tree.itemAt(pos)
        if not item:
            return
        sug_id = item.data(0, Qt.ItemDataRole.UserRole)
        menu = QMenu()
        action = menu.addAction("🗑 删除此建议")
        action.triggered.connect(lambda: self._delete_suggestion(sug_id))
        menu.exec(self._sug_tree.viewport().mapToGlobal(pos))

    def _delete_suggestion(self, sug_id: str):
        if self._app and self._app.opt_store:
            self._app.opt_store.delete(sug_id)
        self._refresh_suggestions()

    def _clear_suggestions(self):
        reply = QMessageBox.question(self, "确认清空",
            "确定要清空所有未应用的建议吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            if self._app and self._app.opt_store:
                self._app.opt_store.clear_pending()
            self._refresh_suggestions()

    # ═══════════════════════════════════════
    # Tab 3: 知识库
    # ═══════════════════════════════════════

    def _build_knowledge_base(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        toolbar = QHBoxLayout()
        self._kb_count_lbl = QLabel("")
        toolbar.addWidget(self._kb_count_lbl)
        toolbar.addStretch()
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self._refresh_knowledge_base)
        toolbar.addWidget(btn_refresh)
        layout.addLayout(toolbar)

        self._kb_tree = QTreeWidget()
        self._kb_tree.setColumnCount(4)
        self._kb_tree.setHeaderLabels(["来源", "描述", "分块数", "入库时间"])
        self._kb_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._kb_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._kb_tree.customContextMenuRequested.connect(self._kb_menu)
        layout.addWidget(self._kb_tree)
        return tab

    def _refresh_knowledge_base(self):
        self._kb_tree.clear()
        try:
            if self._app and self._app.kb:
                items = self._app.kb.registry()
            else:
                import sqlite3
                db_path = str(Path(self._config_path).parent / "data" / "mother.db")
                conn = sqlite3.connect(db_path)
                rows = conn.execute(
                    "SELECT source, description, chunks, created_at FROM kb_docs ORDER BY created_at DESC"
                ).fetchall()
                items = [{"source": r[0], "description": r[1], "chunks": r[2], "created_at": r[3]} for r in rows]
                conn.close()
        except Exception:
            return

        self._kb_count_lbl.setText(f"共 {len(items)} 个文档")
        for r in items:
            ts = datetime.fromtimestamp(r["created_at"]).strftime("%Y-%m-%d %H:%M") if r.get("created_at") else ""
            QTreeWidgetItem(self._kb_tree, [
                r.get("source", ""),
                r.get("description", ""),
                str(r.get("chunks", 0)),
                ts,
            ])

    def _kb_menu(self, pos):
        item = self._kb_tree.itemAt(pos)
        if not item:
            return
        source = item.text(0)
        menu = QMenu()
        action = menu.addAction(f"🗑 删除「{source}」")
        action.triggered.connect(lambda: self._delete_kb_doc(source))
        menu.exec(self._kb_tree.viewport().mapToGlobal(pos))

    def _delete_kb_doc(self, source: str):
        reply = QMessageBox.question(self, "确认删除",
            f"确定要从知识库中删除「{source}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            if self._app and self._app.kb:
                self._app.kb.remove(source)
            self._refresh_knowledge_base()

    # ═══════════════════════════════════════
    # Tab 3: 考试中心
    # ═══════════════════════════════════════

    def _build_exam(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("题目数:"))
        self._exam_spin = QSpinBox()
        self._exam_spin.setRange(1, 10)
        self._exam_spin.setValue(4)
        ctrl.addWidget(self._exam_spin)
        self.btn_exam = QPushButton("▶ 开始考试")
        self.btn_exam.clicked.connect(self._start_exam)
        self.btn_stop_exam = QPushButton("■ 停止")
        self.btn_stop_exam.setEnabled(False)
        self.btn_stop_exam.clicked.connect(self._stop_exam)
        ctrl.addWidget(self.btn_exam)
        ctrl.addWidget(self.btn_stop_exam)
        self._exam_status_lbl = QLabel("")
        ctrl.addWidget(self._exam_status_lbl)
        ctrl.addStretch()
        layout.addLayout(ctrl)
        self._exam_log_w = QTextEdit()
        self._exam_log_w.setReadOnly(True)
        self._exam_log_w.setFont(QFont("Consolas", 9))
        self._exam_log_w.setStyleSheet("QTextEdit { background-color: #1e1e1e; color: #d4d4d4; }")
        layout.addWidget(self._exam_log_w)
        self._exam_buffer = StreamBuffer(self._exam_log_w)
        self._exam_running = False
        return tab

    def _exam_msg(self, tag, text, newline=True):
        if self._exam_buffer:
            self._exam_buffer.feed(tag, text + ("\n" if newline else ""))

    def _start_exam(self):
        if self._exam_running or not self._app:
            return
        self._exam_running = True
        self.btn_exam.setEnabled(False)
        self.btn_stop_exam.setEnabled(True)
        self._exam_log_w.clear()
        count = self._exam_spin.value()
        threading.Thread(target=self._run_exam_thread, args=(count,), daemon=True).start()

    def _stop_exam(self):
        self._exam_running = False
        self.btn_exam.setEnabled(True)
        self.btn_stop_exam.setEnabled(False)

    def _preview_word(self):
        """打开 Word 只读预览弹窗。"""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Word 文件", "./workbooks",
            "Word 文件 (*.docx *.doc);;所有文件 (*.*)"
        )
        if not path:
            return
        from adapters.word_renderer import WordPreviewDialog
        dlg = WordPreviewDialog(path, self)
        dlg.exec()

    def _load_word_preview(self):
        """加载 Word 到右侧预览面板。"""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Word 文件", "./workbooks",
            "Word 文件 (*.docx *.doc);;所有文件 (*.*)"
        )
        if not path:
            return
        from adapters.word_renderer import render_docx_to_qtextedit
        render_docx_to_qtextedit(path, self._word_view)
        self._word_path_lbl.setText(Path(path).name)

    def _auto_preview_word_result(self, reply: str):
        """从 LLM 回复中提取 .docx 路径并自动预览。"""
        import re
        from pathlib import Path
        from adapters.word_renderer import render_docx_to_qtextedit

        # 匹配常见路径模式
        patterns = [
            r'(?:output|workbooks)[/\\][^\s,，。]+\.docx',
            r'[^\s,，。]*\.docx',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, reply, re.IGNORECASE)
            for m in matches:
                path = Path(m)
                if not path.is_absolute():
                    for d in ["./output", "./workbooks", "./templates", "."]:
                        p = Path(d) / path.name
                        if p.exists():
                            render_docx_to_qtextedit(str(p), self._word_view)
                            self._word_path_lbl.setText(p.name)
                            return
        """加载 Word 文件到右侧只读面板。"""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Word 文件", "./workbooks",
            "Word 文件 (*.docx *.doc);;所有文件 (*.*)"
        )
        if not path:
            return
        from adapters.word_renderer import render_docx_to_qtextedit
        render_docx_to_qtextedit(path, self._word_view)
        self._word_path_lbl.setText(Path(path).name)
        self._exam_running = False
        self.btn_exam.setEnabled(True)
        self.btn_stop_exam.setEnabled(False)

    def _run_exam_thread(self, count: int):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run_exam_async(count))
        except Exception as e:
            self._exam_msg("ERROR", f"考试异常: {e}")
        finally:
            self._exam_running = False
            self.btn_exam.setEnabled(True)
            self.btn_stop_exam.setEnabled(False)

    async def _run_exam_async(self, count: int):
        from tests.examiner import build_examiner, _ScoringSkill
        self._exam_msg("TASK", f"{'='*50}\n  开始 {count} 轮双 Agent 对抗测试\n{'='*50}")
        examiner = build_examiner(self._app.cfg, self._app.event_bus)
        scoring = None
        for info in examiner._tools._tools.values():
            if isinstance(info["skill"], _ScoringSkill):
                scoring = info["skill"]
                break
            if isinstance(info["skill"], _ScoringSkill):
                scoring = info["skill"]
                break

        # 考官从 Mother 的工具表中自主出题
        all_tools = self._app.tools.list_tools()
        tool_names = [t["function"]["name"] for t in all_tools]

        # 每组工具的测试任务模板（考官会根据实际工具表择机组合）
        question_pool = [
            f"从以下可用工具中选3个，组合成一个具体的办公任务（要描述清楚具体做什么）：{', '.join(tool_names[:15])}。只输出任务描述，不要执行。",
            f"设计一个需要用到 {', '.join(tool_names[8:15])} 中至少2个工具的任务。只输出任务描述。",
            "设计一个需要联网搜索+Excel操作组合的任务。只输出任务描述。",
            "设计一个需要文件管理+Word生成组合的任务。只输出任务描述。",
            "设计一个包含3步以上的复杂办公流程的任务。只输出任务描述。",
            "设计一个测试异常处理的任务（文件不存在、路径错误等）。只输出任务描述。",
        ]
        all_scores = []
        for q in range(count):
            if not self._exam_running:
                break
            # Step 1: 考官出题
            question = question_pool[q % len(question_pool)]
            self._exam_msg("EXAMINER", f"考官出题中...")
            try:
                eq = await examiner.process(f"你是考官。{question}")
                real_task = eq.get("response", question)[:300]
            except Exception:
                real_task = "在 workbooks 下创建 test.xlsx，写入测试数据"
            self._exam_status_lbl.setText(f"第 {q+1}/{count} 题")
            self._exam_msg("TASK", f"\n━━━ 第 {q+1}/{count} 题 ━━━\n📝 {real_task[:200]}")
            self._exam_msg("MOTHER", "│ Mother: ", newline=False)

            def mt(t, text):
                if t == "thinking":
                    self._exam_msg("MOTHER_THINK", text, newline=False)
                elif t == "content":
                    self._exam_msg("MOTHER", text, newline=False)
                elif t == "tool":
                    tag = "CHART" if "chart" in text.lower() else "SCORE"
                    prefix = " 📊" if "chart" in text.lower() else " 🔧"
                    self._exam_msg(tag, f"{prefix}{text}", newline=False)
            try:
                result = await self._app.process(real_task, on_token=mt)
                self._exam_msg("MOTHER", "")
                self._exam_msg("MOTHER", f"│ 轮次:{result.get('rounds',0)} 工具:{result.get('tool_calls',0)}")
            except Exception as e:
                self._exam_msg("ERROR", f" │ ❌ {e}")

            if scoring:
                scoring.scores.clear()
            verify = f"Mother刚完成这个任务：{real_task}。请用只读工具验证，然后用submit_score打分(0-100)。"
            self._exam_msg("EXAMINER", "│ 考官: ", newline=False)

            def et(t, text):
                if t == "thinking":
                    self._exam_msg("EXAMINER_THINK", text, newline=False)
                elif t == "content":
                    self._exam_msg("EXAMINER", text, newline=False)
                elif t == "tool":
                    self._exam_msg("SCORE", f" 🔍{text}", newline=False)
            try:
                await examiner.process(verify, on_token=et)
                self._exam_msg("EXAMINER", "")
            except Exception as e:
                self._exam_msg("ERROR", f" │ ❌ {e}")

            if scoring and scoring.scores:
                s = scoring.scores[-1]
                all_scores.append(s)
                self._exam_msg("PASS" if s["score"] >= 60 else "FAIL",
                               f"  🏆 {s['score']}/100 — {s['summary']}")
                if s.get("issues"):
                    self._exam_msg("EXAMINER_THINK", f"     问题: {s['issues']}")
            else:
                all_scores.append({"score": 0, "summary": "未评分", "issues": ""})
                self._exam_msg("FAIL", "  ⚠️ 考官未提交评分")

        avg = sum(s["score"] for s in all_scores) / len(all_scores) if all_scores else 0
        passed = sum(1 for s in all_scores if s["score"] >= 60)
        self._exam_msg("SCORE", f"\n{'='*30}\n  平均分: {avg:.1f}  通过率: {passed}/{len(all_scores)}\n{'='*30}")
        self._exam_status_lbl.setText(f"完成: 均分{avg:.0f} | {passed}/{len(all_scores)}")

    # ═══════════════════════════════════════
    # Tab 4: 飞书配置
    # ═══════════════════════════════════════

    def _build_settings(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # ── DeepSeek ──
        layout.addWidget(QLabel("DeepSeek"))
        f = QHBoxLayout()
        f.addWidget(QLabel("Key:"))
        self._ds_api_key = QLineEdit(self.cfg.llm.api_key)
        self._ds_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        f.addWidget(self._ds_api_key)
        layout.addLayout(f)

        r = QHBoxLayout()
        r.addWidget(QLabel("模型:"))
        self._ds_model = QComboBox()
        # 从 models.yaml 读取
        try:
            import yaml
            mp = Path(self._config_path).parent / "models.yaml"
            if mp.exists():
                data = yaml.safe_load(open(str(mp), "r", encoding="utf-8"))
                current = data.get("current", "")
                for prov in data.get("providers", {}).values():
                    for m in prov.get("models", []):
                        self._ds_model.addItem(m["name"])
                if current:
                    self._ds_model.setCurrentText(current)
        except Exception:
            self._ds_model.addItems(["deepseek-v4-pro", "deepseek-v4-flash", "deepseek-chat"])
            self._ds_model.setCurrentText(self.cfg.llm.model) if self.cfg else None
        r.addWidget(self._ds_model)
        r.addWidget(QLabel("轮次:"))
        self._ds_rounds = QSpinBox(); self._ds_rounds.setRange(1,30)
        self._ds_rounds.setValue(self.cfg.llm.max_rounds if self.cfg else 20)
        r.addWidget(self._ds_rounds)
        r.addWidget(QLabel("Temp:"))
        self._ds_temp = QComboBox(); self._ds_temp.addItems(["0.1","0.3","0.5","0.7","1.0","1.5","2.0"])
        if self.cfg: self._ds_temp.setCurrentText(str(self.cfg.llm.temperature))
        r.addWidget(self._ds_temp)
        r.addWidget(QLabel("上下文:"))
        self._ds_ctx = QSpinBox(); self._ds_ctx.setRange(0, 200)
        self._ds_ctx.setSpecialValueText("无限")
        self._ds_ctx.setValue(self.cfg.llm.context_rounds if self.cfg else 0)
        r.addWidget(self._ds_ctx)
        layout.addLayout(r)

        layout.addWidget(QLabel("GLM Key（视觉）:"))
        self._s_glm_key = QLineEdit(getattr(self.cfg.llm, 'glm_api_key', '') if self.cfg else "")
        self._s_glm_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self._s_glm_key)

        layout.addWidget(QLabel("商汤 Key（视觉备用）:"))
        self._s_sense_key = QLineEdit(getattr(self.cfg.llm, 'sense_api_key', '') if self.cfg else "")
        self._s_sense_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self._s_sense_key)

        layout.addWidget(QLabel("知乎 Key:"))
        self._s_zhihu_key = QLineEdit(getattr(self.cfg.llm, 'zhihu_api_key', '') if self.cfg else "")
        self._s_zhihu_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self._s_zhihu_key)

        self._s_lang = QCheckBox("English Prompt（英文提示词）")
        self._s_lang.setChecked(getattr(self.cfg.llm, 'lang', 'zh') == 'en')
        layout.addWidget(self._s_lang)

        self._s_optimize = QCheckBox("启用提示词自动优化")
        self._s_optimize.setChecked(getattr(self.cfg.llm, 'optimize_enabled', True))
        layout.addWidget(self._s_optimize)

        # ── 飞书 ──
        layout.addWidget(QLabel("飞书"))
        self._feishu_app_id = QLineEdit(self.cfg.feishu.app_id if self.cfg else "")
        layout.addWidget(self._feishu_app_id)
        self._feishu_app_secret = QLineEdit(self.cfg.feishu.app_secret if self.cfg else "")
        self._feishu_app_secret.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self._feishu_app_secret)
        self._feishu_ws_cb = QCheckBox("启用 WebSocket")
        self._feishu_ws_cb.setChecked(self.cfg.feishu.enable_websocket if self.cfg else False)
        layout.addWidget(self._feishu_ws_cb)

        # ── 保存 ──
        btn = QPushButton("💾 保存设置")
        btn.clicked.connect(self._save_settings)
        layout.addWidget(btn)
        self._s_status = QLabel("")
        layout.addWidget(self._s_status)
        layout.addStretch()
        return tab

    def _save_settings(self):
        self._up_yaml("llm", {
            "api_key": self._ds_api_key.text(),
            "model": self._ds_model.currentText(),
            "max_rounds": self._ds_rounds.value(),
            "context_rounds": self._ds_ctx.value(),
            "temperature": float(self._ds_temp.currentText()),
            "glm_api_key": self._s_glm_key.text(),
            "sense_api_key": self._s_sense_key.text(),
            "zhihu_api_key": self._s_zhihu_key.text(),
            "lang": "en" if self._s_lang.isChecked() else "zh",
            "optimize_enabled": self._s_optimize.isChecked(),
        })
        # 同步到 models.yaml
        try:
            import yaml
            mp = Path(self._config_path).parent / "models.yaml"
            if mp.exists():
                data = yaml.safe_load(open(str(mp), "r", encoding="utf-8"))
                data["current"] = self._ds_model.currentText()
                yaml.dump(data, open(str(mp), "w", encoding="utf-8"), allow_unicode=True, default_flow_style=False, sort_keys=False)
        except Exception:
            pass
        self._up_yaml("feishu", {
            "app_id": self._feishu_app_id.text(),
            "app_secret": self._feishu_app_secret.text(),
            "enable_websocket": self._feishu_ws_cb.isChecked(),
        })
        self._s_status.setText("✅ 已保存，重启面板生效")

    def _up_yaml(self, section, values):
        import yaml
        path = Path(self._config_path)
        data = {}
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        data.setdefault(section, {}).update(values)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def closeEvent(self, event):
        if hasattr(self, '_status_timer'):
            self._status_timer.stop()
        if self._dash_buffer:
            self._dash_buffer.stop()
        if hasattr(self, '_exam_buffer') and self._exam_buffer:
            self._exam_buffer.stop()
        if self._app:
            self._app.engine.cancel()
            if self._app.feishu:
                self._app.feishu.stop()
            self._app.shutdown()
            self._app = None
        if self.logger:
            self.logger.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MotherPanelQt()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
