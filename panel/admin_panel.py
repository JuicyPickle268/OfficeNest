"""
Mother v2 控制面板（tkinter）
状态监控、事件日志、启停控制、飞书/DeepSeek 配置、内嵌终端。
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime
from pathlib import Path
import sys
import os
import asyncio
import threading
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.schema import load_config
from core.events.bus import SimpleEventBus
from core.events.event import Event
from core.events.types import EventType
from infrastructure.logger.logger import Logger


class MotherPanel:
    """Mother 管理面板"""

    # 流式缓冲刷新间隔（秒）
    STREAM_FLUSH_MS = 80

    class _StreamBuffer:
        """批量缓存流式 token，定时刷新到 tkinter widget，避免逐个 insert 卡顿。"""
        def __init__(self, widget, flush_ms=80):
            self._widget = widget
            self._flush_ms = flush_ms
            self._buf: list[tuple[str, str]] = []  # (tag, text)
            self._scheduled = False

        def feed(self, tag: str, text: str):
            self._buf.append((tag, text))
            if not self._scheduled:
                self._scheduled = True
                self._widget.after(self._flush_ms, self._flush)

        def feed_line(self, tag: str, text: str):
            self._buf.append((tag, text + "\n"))
            if not self._scheduled:
                self._scheduled = True
                self._widget.after(self._flush_ms, self._flush)

        def _flush(self):
            self._scheduled = False
            if not self._buf:
                return
            combined = self._buf
            self._buf = []
            for tag, text in combined:
                self._widget.insert(tk.END, text, tag)
            self._widget.see(tk.END)

        def flush_now(self):
            self._scheduled = False
            self._flush()

    def __init__(self, config_path: str = "config/default.yaml"):
        self._config_path = config_path
        self.cfg = load_config(config_path)
        self.event_bus = SimpleEventBus()
        self.logger: Logger | None = None
        self._running = False
        self._event_count = 0
        self._app = None
        self._task_lock = threading.Lock()

        # 持久化 asyncio event loop（避免每次 asyncio.run 创建/销毁）
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()

        # 窗口
        self.root = tk.Tk()
        self.root.title(self.cfg.panel.window_title)
        w, h = self.cfg.panel.window_size
        self.root.geometry(f"{w}x{h+80}")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._init_logger()
        self._start_refresh_loop()

    # ── UI 构建 ──

    def _build_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self._build_dashboard_tab(notebook)
        self._build_log_tab(notebook)
        self._build_improvements_tab(notebook)
        self._build_exam_tab(notebook)
        self._build_feishu_tab(notebook)
        self._build_deepseek_tab(notebook)

        # ── 全局底栏：命令输入 ──
        cmd_frame = ttk.Frame(self.root, padding=5)
        cmd_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        left = ttk.Frame(cmd_frame)
        left.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Label(left, text="指令:", font=("Microsoft YaHei", 9)).pack(anchor=tk.N, padx=(0, 5))

        self.cmd_entry = scrolledtext.ScrolledText(
            cmd_frame, height=4, width=1, wrap=tk.WORD,
            font=("Consolas", 10),
            bg="#1e1e1e", fg="#d4d4d4", insertbackground="white",
        )
        self.cmd_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        self.cmd_entry.bind("<Return>", self._send_command)
        self.cmd_entry.config(state=tk.DISABLED)

        self.btn_send = ttk.Button(cmd_frame, text="发送", command=self._send_command)
        self.btn_send.pack(side=tk.LEFT, padx=5)
        self.btn_send.config(state=tk.DISABLED)

    # ── Tab 1: 仪表盘 ──

    def _build_dashboard_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="仪表盘")

        # 状态栏
        status_frame = ttk.Frame(tab)
        status_frame.pack(fill=tk.X, pady=5)
        self._status_labels = {}

        for label, default, color in [
            ("引擎", "● 待启动", "gray"),
            ("pywin32", "● 检测中", "gray"),
            ("openpyxl", "● 检测中", "gray"),
            ("openai", "● 检测中", "gray"),
            ("事件", "0", "black"),
        ]:
            f = ttk.Frame(status_frame)
            f.pack(side=tk.LEFT, padx=15)
            ttk.Label(f, text=label, font=("Microsoft YaHei", 8)).pack(side=tk.LEFT)
            lbl = ttk.Label(f, text=default, font=("Microsoft YaHei", 9, "bold"), foreground=color)
            lbl.pack(side=tk.LEFT, padx=5)
            self._status_labels[label] = lbl

        # 日志区
        ttk.Label(tab, text="对话 & 事件日志", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(10, 0))
        self.log_text = scrolledtext.ScrolledText(
            tab, height=18, font=("Consolas", 9),
            bg="#1e1e1e", fg="#d4d4d4", wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=5)
        self.log_text.tag_config("INFO", foreground="#4ec9b0")
        self.log_text.tag_config("WARN", foreground="#dcdcaa")
        self.log_text.tag_config("ERROR", foreground="#f44747")
        self.log_text.tag_config("USER", foreground="#ce9178")
        self.log_text.tag_config("BOT", foreground="#39ff14")      # 荧光绿，回复内容
        self.log_text.tag_config("THINK", foreground="#569cd6")    # 蓝色，思考过程
        self.log_text.tag_config("TOOL", foreground="#dcdcaa")     # 黄色，工具调用
        self.log_text.tag_config("TIMESTAMP", foreground="#808080")

        # 流式缓冲器（避免逐token insert卡顿）
        self._log_stream = self._StreamBuffer(self.log_text, self.STREAM_FLUSH_MS)

        # 控制按钮
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, pady=5)
        self.btn_start = ttk.Button(btn_frame, text="▶ 启动引擎", command=self._start_engine)
        self.btn_start.pack(side=tk.LEFT, padx=5)
        self.btn_stop = ttk.Button(btn_frame, text="■ 停止", command=self._stop_engine, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="清空日志", command=self._clear_log).pack(side=tk.RIGHT, padx=5)

    # ── Tab 2: 日志 ──

    def _build_log_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="日志")

        top = ttk.Frame(tab)
        top.pack(fill=tk.X, pady=5)

        ttk.Button(top, text="刷新", command=self._refresh_log_tab).pack(side=tk.LEFT, padx=5)
        self.log_filter_var = tk.StringVar(value="all")
        ttk.Radiobutton(top, text="全部", variable=self.log_filter_var, value="all",
                        command=self._refresh_log_tab).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(top, text="仅错误", variable=self.log_filter_var, value="error",
                        command=self._refresh_log_tab).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(top, text="仅工具调用", variable=self.log_filter_var, value="tool",
                        command=self._refresh_log_tab).pack(side=tk.LEFT, padx=5)

        self.log_tree = ttk.Treeview(tab, columns=("time", "type", "detail"), show="headings",
                                      selectmode="browse")
        self.log_tree.heading("time", text="时间")
        self.log_tree.heading("type", text="类型")
        self.log_tree.heading("detail", text="详情")
        self.log_tree.column("time", width=80, anchor="center")
        self.log_tree.column("type", width=80, anchor="center")
        self.log_tree.column("detail", width=600, anchor="w")

        scrollbar = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=self.log_tree.yview)
        self.log_tree.configure(yscrollcommand=scrollbar.set)
        self.log_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_tree.tag_configure("error", foreground="#f44747")
        self.log_tree.tag_configure("tool", foreground="#dcdcaa")
        self.log_tree.tag_configure("task", foreground="#4ec9b0")

    def _refresh_log_tab(self):
        """刷新日志标签页。"""
        self.log_tree.delete(*self.log_tree.get_children())
        if not self.logger:
            return

        filter_val = self.log_filter_var.get()
        try:
            rows = self.logger._conn.execute(
                "SELECT timestamp, type, data, event_id FROM events ORDER BY timestamp DESC LIMIT 200"
            ).fetchall()
        except Exception:
            return

        for row in rows:
            ts = datetime.fromtimestamp(row[0]).strftime("%H:%M:%S")
            etype = row[1]
            data_str = row[2] or ""

            # 提取简要
            try:
                import json
                data = json.loads(data_str)
            except Exception:
                data = {}

            detail = ""
            tag = ""
            if "tool" in etype:
                if filter_val == "error":
                    continue
                tool = data.get("tool", "")
                err = data.get("error", "")
                detail = f"{tool}" if not err else f"{tool} ❌ {err}"
                tag = "tool" if not err else "error"
            elif "error" in etype:
                detail = data.get("error", etype)
                tag = "error"
            elif "task" in etype:
                if filter_val not in ("all",):
                    continue
                detail = data.get("user_message", "")[:80]
                tag = "task"
            else:
                if filter_val == "error" or filter_val == "tool":
                    continue
                detail = etype

            self.log_tree.insert("", 0, values=(ts, etype.split(".")[-1][:10], detail), tags=(tag,))

    async def _on_dangerous_action(self, tool_name: str, args: dict) -> bool:
        """危险操作确认弹窗（在 tkinter 主线程显示）。"""
        import threading
        result = threading.Event()
        approved = [False]

        def _show():
            ok = messagebox.askyesno(
                "⚠️ 危险操作确认",
                f"Mother 即将执行危险操作:\n\n工具: {tool_name}\n参数: {args}\n\n是否允许？"
            )
            approved[0] = ok
            result.set()

        self.root.after(0, _show)
        # 等待用户选择（不阻塞 event loop）
        while not result.is_set():
            await asyncio.sleep(0.1)
        return approved[0]

    # ── Tab: 待优化需求 ──

    def _build_improvements_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="待优化需求")

        top = ttk.Frame(tab)
        top.pack(fill=tk.X, pady=5)
        ttk.Button(top, text="刷新", command=self._refresh_improvements_tab).pack(side=tk.LEFT, padx=5)
        ttk.Label(top, text="右键 → 标记为已解决", foreground="gray", font=("Microsoft YaHei", 8)).pack(side=tk.RIGHT, padx=5)

        self.imp_tree = ttk.Treeview(tab, columns=("id", "title", "desc", "status"), show="headings",
                                      selectmode="browse")
        self.imp_tree.heading("id", text="ID")
        self.imp_tree.heading("title", text="标题")
        self.imp_tree.heading("desc", text="描述")
        self.imp_tree.heading("status", text="状态")
        self.imp_tree.column("id", width=90, anchor="center")
        self.imp_tree.column("title", width=150, anchor="w")
        self.imp_tree.column("desc", width=400, anchor="w")
        self.imp_tree.column("status", width=60, anchor="center")

        scrollbar = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=self.imp_tree.yview)
        self.imp_tree.configure(yscrollcommand=scrollbar.set)
        self.imp_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.imp_tree.tag_configure("pending", foreground="#dcdcaa")
        self.imp_tree.tag_configure("resolved", foreground="#808080")

        # 右键菜单
        self.imp_menu = tk.Menu(self.root, tearoff=0)
        self.imp_menu.add_command(label="✅ 标记为已解决", command=self._resolve_improvement)
        self.imp_tree.bind("<Button-3>", self._on_imp_right_click)

    def _refresh_improvements_tab(self):
        """刷新需求列表。"""
        self.imp_tree.delete(*self.imp_tree.get_children())
        if not self._app:
            return
        try:
            items = self._app.improvements.list_all()
        except Exception:
            return
        for item in items:
            status = item.get("status", "pending")
            tag = "resolved" if status == "resolved" else "pending"
            self.imp_tree.insert("", 0,
                values=(item["id"][:12], item["title"], item.get("description", "")[:60], status),
                tags=(tag,))

    def _on_imp_right_click(self, event):
        """右键弹出菜单。"""
        sel = self.imp_tree.selection()
        if sel:
            self.imp_menu.post(event.x_root, event.y_root)

    def _resolve_improvement(self):
        """标记选中需求为已解决。"""
        sel = self.imp_tree.selection()
        if not sel:
            return
        values = self.imp_tree.item(sel[0], "values")
        if not values:
            return
        imp_id = values[0]
        # 尝试完整 ID 匹配
        try:
            items = self._app.improvements.list_all()
            for item in items:
                if item["id"].startswith(imp_id):
                    self._app.improvements.resolve(item["id"])
                    break
        except Exception:
            pass
        self._refresh_improvements_tab()

    # ── Tab: 考试中心 ──

    def _build_exam_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="考试中心")

        ttk.Label(tab, text="双 Agent 对抗测试", font=("Microsoft YaHei", 12, "bold")).pack(anchor=tk.W)

        info = """考官（只读工具）出题 → Mother（全工具）真 Office 执行 → 考官阅卷评分。
两个 Agent 使用不同的提示词和工具集。"""
        ttk.Label(tab, text=info, font=("Microsoft YaHei", 8), foreground="gray").pack(anchor=tk.W, pady=5)

        # 控制栏
        ctrl = ttk.Frame(tab)
        ctrl.pack(fill=tk.X, pady=5)

        ttk.Label(ctrl, text="题目数:").pack(side=tk.LEFT)
        self.exam_count = ttk.Spinbox(ctrl, from_=1, to=10, width=4)
        self.exam_count.pack(side=tk.LEFT, padx=5)
        self.exam_count.set("4")

        self.btn_exam = ttk.Button(ctrl, text="▶ 开始考试", command=self._start_exam)
        self.btn_exam.pack(side=tk.LEFT, padx=5)

        self.btn_exam_stop = ttk.Button(ctrl, text="■ 停止", command=self._stop_exam, state=tk.DISABLED)
        self.btn_exam_stop.pack(side=tk.LEFT, padx=5)

        self.exam_status = ttk.Label(ctrl, text="")
        self.exam_status.pack(side=tk.RIGHT, padx=10)

        # 结果区
        self.exam_text = scrolledtext.ScrolledText(
            tab, height=14, font=("Consolas", 9),
            bg="#1e1e1e", fg="#d4d4d4", wrap=tk.WORD
        )
        self.exam_text.pack(fill=tk.BOTH, expand=True, pady=5)
        self.exam_text.tag_config("TASK", foreground="#ce9178")
        self.exam_text.tag_config("MOTHER", foreground="#39ff14")
        self.exam_text.tag_config("MOTHER_THINK", foreground="#4a8a5e")
        self.exam_text.tag_config("EXAMINER", foreground="#569cd6")
        self.exam_text.tag_config("EXAMINER_THINK", foreground="#3a5f8a")
        self.exam_text.tag_config("SCORE", foreground="#dcdcaa")
        self.exam_text.tag_config("ERROR", foreground="#f44747")
        self.exam_text.tag_config("PASS", foreground="#4ec9b0")
        self.exam_text.tag_config("FAIL", foreground="#f44747")

        # 考试流式缓冲
        self._exam_stream = self._StreamBuffer(self.exam_text, self.STREAM_FLUSH_MS)

        self._exam_running = False

    def _exam_log(self, tag: str, text: str, newline: bool = True):
        self._exam_stream.feed(tag, text + ("\n" if newline else ""))

    def _start_exam(self):
        if self._exam_running:
            return
        if not self._app:
            self._exam_log("ERROR", "请先在仪表盘启动引擎")
            return

        self._exam_running = True
        self.btn_exam.config(state=tk.DISABLED)
        self.btn_exam_stop.config(state=tk.NORMAL)
        self.exam_text.delete("1.0", tk.END)

        count = int(self.exam_count.get())
        threading.Thread(target=self._run_exam_thread, args=(count,), daemon=True).start()

    def _stop_exam(self):
        self._exam_running = False
        self.btn_exam.config(state=tk.NORMAL)
        self.btn_exam_stop.config(state=tk.DISABLED)
        self._exam_log("ERROR", "考试已手动停止")

    def _run_exam_thread(self, count: int):
        """后台线程运行考试。"""
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._run_exam_async(count))
        except Exception as e:
            self._exam_log("ERROR", f"考试异常: {e}")
        finally:
            self._exam_running = False
            self.root.after(0, lambda: self.btn_exam.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.btn_exam_stop.config(state=tk.DISABLED))

    async def _run_exam_async(self, count: int):
        """考试异步逻辑——流式输出双方思考。"""
        from tests.examiner import build_examiner, _ScoringSkill

        self._exam_log("TASK", "=" * 50)
        self._exam_log("TASK", f"  开始 {count} 轮双 Agent 对抗测试")
        self._exam_log("TASK", "=" * 50)

        # 构建考官
        self._exam_log("EXAMINER", "[考官] 初始化中...")
        examiner = build_examiner(self._app.cfg, self._app.event_bus)
        scoring: _ScoringSkill | None = None
        for info in examiner._tools._tools.values():
            if isinstance(info["skill"], _ScoringSkill):
                scoring = info["skill"]
                break

        all_scores = []
        templates = [
            ("基础Excel创建", "请 Mother 在 workbooks 下创建 exam_test.xlsx，表头：姓名、岗位、面试官、评分。写入5行含异常值的数据（如空面试官、非数字评分）。"),
            ("数据查询", "请 Mother 读取 exam_test.xlsx，找出评分最高和最低的候选人，告诉我姓名和分数。"),
            ("数据清洗", "请 Mother 删除 exam_test.xlsx 中评分异常的行的行，把空面试官填'待查'。"),
            ("多Sheet统计", "请 Mother 在 exam_test.xlsx 建新Sheet'统计'，写每个岗位的人数和平均分。"),
        ]

        for q in range(count):
            if not self._exam_running:
                break

            name, task = templates[q % len(templates)]
            self.exam_status.config(text=f"第 {q+1}/{count} 题: {name}")
            self._exam_log("TASK", f"\n━━━ 第 {q+1}/{count} 题: {name} ━━━")
            self._exam_log("TASK", f"📝 {task[:150]}")
            self._exam_log("TASK", "")

            # ── Mother 流式执行 ──
            self._exam_log("MOTHER", "│ Mother: ", newline=False)
            def mother_token(ttype, text):
                if ttype == "thinking":
                    self._exam_log("MOTHER_THINK", text, newline=False)
                elif ttype == "content":
                    self._exam_log("MOTHER", text, newline=False)
                elif ttype == "tool":
                    self._exam_log("SCORE", f" 🔧{text}", newline=False)
            try:
                result = await self._app.process(task, on_token=mother_token)
                self._exam_log("MOTHER", "")
                self._exam_log("MOTHER", f"│ 轮次:{result.get('rounds',0)} 工具调用:{result.get('tool_calls',0)}")
            except Exception as e:
                self._exam_log("ERROR", f" │ ❌ {e}")

            # ── 考官流式阅卷 ──
            if scoring:
                scoring.scores.clear()
            verify = f"Mother刚完成一个任务：{task}。请用只读工具验证一下她做得对不对，然后调submit_score打分(0-100)。"
            self._exam_log("EXAMINER", "│ 考官: ", newline=False)
            def exam_token(ttype, text):
                if ttype == "thinking":
                    self._exam_log("EXAMINER_THINK", text, newline=False)
                elif ttype == "content":
                    self._exam_log("EXAMINER", text, newline=False)
                elif ttype == "tool":
                    self._exam_log("SCORE", f" 🔍{text}", newline=False)
            try:
                er = await examiner.process(verify, on_token=exam_token)
                self._exam_log("EXAMINER", "")
            except Exception as e:
                self._exam_log("ERROR", f" │ ❌ {e}")

            if scoring and scoring.scores:
                s = scoring.scores[-1]
                all_scores.append(s)
                tag = "PASS" if s["score"] >= 60 else "FAIL"
                self._exam_log(tag, f"  🏆 {s['score']}/100 — {s['summary']}")
                if s.get("issues"):
                    self._exam_log("EXAMINER_THINK", f"     问题: {s['issues']}")
            else:
                all_scores.append({"score": 0, "summary": "未评分", "issues": ""})
                self._exam_log("FAIL", "  ⚠️ 考官未提交评分")

        # 汇总
        avg = sum(s["score"] for s in all_scores) / len(all_scores) if all_scores else 0
        passed = sum(1 for s in all_scores if s["score"] >= 60)
        self._exam_log("SCORE", f"\n{'='*30}")
        self._exam_log("SCORE", f"  平均分: {avg:.1f}  通过率: {passed}/{len(all_scores)}")
        self._exam_log("SCORE", f"{'='*30}")
        self.exam_status.config(text=f"完成: 均分{avg:.0f} | 通过{passed}/{len(all_scores)}")

    # ── Tab 2: 飞书配置 ──

    def _build_feishu_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=15)
        notebook.add(tab, text="飞书配置")

        ttk.Label(tab, text="飞书应用凭证", font=("Microsoft YaHei", 12, "bold")).pack(anchor=tk.W)
        info = """
在飞书开发者后台 (open.feishu.cn) 获取 App ID 和 App Secret。
在「应用功能」中开启机器人能力并发布。
"""
        ttk.Label(tab, text=info, font=("Microsoft YaHei", 8), foreground="gray").pack(anchor=tk.W, pady=5)

        ttk.Label(tab, text="App ID:").pack(anchor=tk.W, pady=(10, 0))
        self.feishu_app_id = ttk.Entry(tab, width=60)
        self.feishu_app_id.pack(fill=tk.X, pady=2)
        self.feishu_app_id.insert(0, self.cfg.feishu.app_id)

        ttk.Label(tab, text="App Secret:").pack(anchor=tk.W, pady=(10, 0))
        self.feishu_app_secret = ttk.Entry(tab, width=60, show="*")
        self.feishu_app_secret.pack(fill=tk.X, pady=2)
        self.feishu_app_secret.insert(0, self.cfg.feishu.app_secret)

        ttk.Label(tab, text="WebSocket 长连接:", font=("Microsoft YaHei", 9)).pack(anchor=tk.W, pady=(15, 0))
        self.feishu_ws_enabled = tk.BooleanVar(value=self.cfg.feishu.enable_websocket)
        ttk.Checkbutton(tab, text="启用飞书连接（生产环境）", variable=self.feishu_ws_enabled).pack(anchor=tk.W)

        ttk.Button(tab, text="保存飞书配置", command=self._save_feishu_config).pack(pady=15)
        self.feishu_status = ttk.Label(tab, text="", foreground="green")
        self.feishu_status.pack()

    # ── Tab 3: DeepSeek 配置 ──

    def _build_deepseek_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=15)
        notebook.add(tab, text="DeepSeek 配置")

        ttk.Label(tab, text="DeepSeek API 设置", font=("Microsoft YaHei", 12, "bold")).pack(anchor=tk.W)
        info = """
在 platform.deepseek.com 申请 API Key。
deepseek-v4-pro（最强）| deepseek-v4-flash（更快）
"""
        ttk.Label(tab, text=info, font=("Microsoft YaHei", 8), foreground="gray").pack(anchor=tk.W, pady=5)

        ttk.Label(tab, text="API Key:").pack(anchor=tk.W, pady=(10, 0))
        self.ds_api_key = ttk.Entry(tab, width=60, show="*")
        self.ds_api_key.pack(fill=tk.X, pady=2)
        self.ds_api_key.insert(0, self.cfg.llm.api_key)

        ttk.Label(tab, text="模型:").pack(anchor=tk.W, pady=(10, 0))
        self.ds_model = ttk.Combobox(tab, values=["deepseek-v4-pro", "deepseek-v4-flash", "deepseek-chat"], state="readonly")
        self.ds_model.pack(fill=tk.X, pady=2)
        self.ds_model.set(self.cfg.llm.model)

        ttk.Label(tab, text="Base URL:").pack(anchor=tk.W, pady=(10, 0))
        self.ds_base_url = ttk.Entry(tab, width=60)
        self.ds_base_url.pack(fill=tk.X, pady=2)
        self.ds_base_url.insert(0, self.cfg.llm.base_url)

        row = ttk.Frame(tab)
        row.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(row, text="最大轮次:").pack(side=tk.LEFT)
        self.ds_max_rounds = ttk.Spinbox(row, from_=1, to=20, width=5)
        self.ds_max_rounds.pack(side=tk.LEFT, padx=5)
        self.ds_max_rounds.set(str(self.cfg.llm.max_rounds))

        ttk.Label(row, text="  Temperature:").pack(side=tk.LEFT, padx=(20, 0))
        self.ds_temperature = ttk.Spinbox(row, from_=0, to=2.0, increment=0.1, width=5)
        self.ds_temperature.pack(side=tk.LEFT, padx=5)
        self.ds_temperature.set(str(self.cfg.llm.temperature))

        ttk.Button(tab, text="保存 DeepSeek 配置", command=self._save_deepseek_config).pack(pady=15)
        self.ds_status = ttk.Label(tab, text="", foreground="green")
        self.ds_status.pack()

    # ── Async Loop ──

    def _run_loop(self):
        """持久化事件循环线程。"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run_async(self, coro, timeout: float = 120):
        """在持久化循环中运行协程，返回结果。"""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    # ── 命令发送 ──

    def _send_command(self, event=None):
        """Enter 键或点击发送时调用。"""
        user_input = self.cmd_entry.get("1.0", tk.END).strip()
        if not user_input:
            return "break"

        self.cmd_entry.delete("1.0", tk.END)
        self._append_log("USER", f"🧑 {user_input}")

        if not self._app:
            self._append_log("WARN", "引擎未启动，请先点击「启动引擎」")
            return "break"

        # 后台线程执行，不卡 UI
        threading.Thread(target=self._run_command, args=(user_input,), daemon=True).start()
        return "break"  # 阻止默认的换行

    def _run_command(self, user_input: str):
        """在后台线程执行命令，流式输出。"""
        with self._task_lock:
            try:
                thinking_buf = []
                content_buf = []
                tool_names = []

                def on_token(ttype: str, text: str):
                    if ttype == "thinking":
                        thinking_buf.append(text)
                        self._log_stream.feed("THINK", text)
                    elif ttype == "tool":
                        tool_names.append(text)
                        self._log_stream.feed("TOOL", f" 🔧 {text}")

                self.root.after(0, lambda: self._start_bot_line())
                if thinking_buf:
                    self.root.after(0, lambda: self._append_stream("END", "\n"))

                # 用持久化 loop 代替 asyncio.run()
                result = self._run_async(self._app.process(user_input, on_token=on_token))

                full_reply = "".join(content_buf)
                if not full_reply:
                    full_reply = result.get("response", "")

                if full_reply:
                    from adapters.table_renderer import detect_and_render
                    rendered = detect_and_render(full_reply)
                    for line in rendered.split("\n"):
                        self._log_stream.feed_line("BOT", line)

            except Exception as e:
                self.root.after(0, lambda e=e: self._append_log("ERROR", f"执行失败: {e}"))

    def _append_line(self, level: str, text: str):
        """追加一整行（带时间戳的首行、不带时间戳的续行）。"""
        # 简化：BOT 输出统一用 BOT 颜色，不加时间戳（已在 _start_bot_line 加了）
        self.log_text.insert(tk.END, text + "\n", level)
        self.log_text.see(tk.END)

    def _start_bot_line(self):
        """插入 BOT 行首标识（已废弃，由 _log_stream 处理）。"""
        pass

    def _append_stream(self, level: str, text: str):
        """流式追加文本（不换行）。"""
        tag = level
        if level == "THINK":
            tag = "THINK"
        elif level == "TOOL":
            tag = "TOOL"
        elif level == "BOT":
            tag = "BOT"
        elif level == "END":
            self.log_text.insert(tk.END, "\n")
            self.log_text.see(tk.END)
            return
        self.log_text.insert(tk.END, text, tag)
        self.log_text.see(tk.END)

    def _on_feishu_event(self, event: Event):
        """飞书消息显示在面板日志。"""
        text = event.data.get("text", "")
        self._append_log("INFO", f"📩 飞书: {text[:120]}")

    # ── 配置保存 ──

    def _save_feishu_config(self):
        try:
            self._update_yaml({
                "feishu": {
                    "app_id": self.feishu_app_id.get(),
                    "app_secret": self.feishu_app_secret.get(),
                    "enable_websocket": self.feishu_ws_enabled.get(),
                }
            })
            self.feishu_status.config(text="已保存", foreground="green")
        except Exception as e:
            self.feishu_status.config(text=f"保存失败: {e}", foreground="red")

    def _save_deepseek_config(self):
        try:
            self._update_yaml({
                "llm": {
                    "api_key": self.ds_api_key.get(),
                    "model": self.ds_model.get(),
                    "base_url": self.ds_base_url.get(),
                    "max_rounds": int(self.ds_max_rounds.get()),
                    "temperature": float(self.ds_temperature.get()),
                }
            })
            self.ds_status.config(text="已保存，重启面板生效", foreground="green")
        except Exception as e:
            self.ds_status.config(text=f"保存失败: {e}", foreground="red")

    def _update_yaml(self, updates: dict):
        path = Path(self._config_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}

        for section, values in updates.items():
            if section not in data:
                data[section] = {}
            data[section].update(values)

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # ── 日志 ──

    def _init_logger(self):
        try:
            self.logger = Logger(self.cfg.storage.db_path)
            self._append_log("INFO", "日志系统就绪")
        except Exception as e:
            self._append_log("ERROR", f"日志系统失败: {e}")

    def _append_log(self, level: str, message: str):
        """线程安全地追加日志。"""
        ts = datetime.now().strftime("%H:%M:%S")
        if level == "BOT":
            from adapters.table_renderer import detect_and_render
            rendered = detect_and_render(message)
            first = True
            for line in rendered.split("\n"):
                if first:
                    self._log_stream.feed("TIMESTAMP", f"[{ts}] ")
                    first = False
                self._log_stream.feed_line(level, line)
        else:
            self._log_stream.feed("TIMESTAMP", f"[{ts}] ")
            self._log_stream.feed_line(level, message)

    def _clear_log(self):
        self.log_text.delete("1.0", tk.END)

    # ── 引擎控制 ──

    def _start_engine(self):
        """启动 Mother Engine。"""
        if self._running:
            return

        # 重新加载配置（可能面板里改了）
        self.cfg = load_config(self._config_path)

        # 检查 API Key
        if not self.cfg.llm.api_key:
            messagebox.showwarning("缺少 API Key", "请先在「DeepSeek 配置」页填写 API Key")
            return

        try:
            from main import MotherApp
            self._app = MotherApp(self._config_path)
            # 设置危险操作确认
            if getattr(self._app.cfg.office, 'confirm_dangerous', True):
                self._app.engine.set_confirm_handler(self._on_dangerous_action)
        except Exception as e:
            self._append_log("ERROR", f"引擎初始化失败: {e}")
            return

        self._running = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.cmd_entry.config(state=tk.NORMAL)
        self.btn_send.config(state=tk.NORMAL)
        self.cmd_entry.focus_set()

        self._update_status("引擎", "● 运行中", "green")
        self._append_log("INFO", f"引擎已启动 | 模型: {self.cfg.llm.model} | Office: {'就绪' if self._check_office() else '未检测到'}")

        # 连接 app 的事件总线（让飞书消息能在面板显示）
        self._app.event_bus.subscribe(EventType.FEISHU_MESSAGE_RECEIVED, self._on_feishu_event)

        # 启动飞书
        if self._app.feishu:
            self._app.start_feishu()
            self._update_status("飞书", "● 连接中...", "yellow")

    def _stop_engine(self):
        self._running = False
        # 停止飞书
        if self._app and self._app.feishu:
            self._app.feishu.stop()
            self._update_status("飞书", "● 已断开", "gray")
        self._app = None
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.cmd_entry.config(state=tk.DISABLED)
        self.btn_send.config(state=tk.DISABLED)
        self._update_status("引擎", "● 已停止", "orange")
        self._append_log("INFO", "引擎已停止")

    @staticmethod
    def _check_office() -> bool:
        try:
            import win32com.client
            return True
        except ImportError:
            return False

    # ── 状态刷新 ──

    def _start_refresh_loop(self):
        self._refresh_status()
        self._refresh_log_tab()
        self.root.after(self.cfg.panel.refresh_interval_ms, self._start_refresh_loop)

    def _refresh_status(self):
        self._update_status("事件", str(self._event_count), "black")
        # 依赖检测
        for pkg, label in [("win32com", "pywin32"), ("openpyxl", "openpyxl"), ("openai", "openai")]:
            try:
                __import__(pkg)
                self._update_status(label, "● 已安装", "green")
            except ImportError:
                self._update_status(label, "● 未安装", "red")

    def _update_status(self, label: str, value: str, color: str):
        if label in self._status_labels:
            self._status_labels[label].config(text=value, foreground=color)

    def _on_close(self):
        if self._running:
            self._stop_engine()
        if self.logger:
            self.logger.close()
        # 停止事件循环
        self._loop.call_soon_threadsafe(self._loop.stop)
        self.root.destroy()

    def run(self):
        self._append_log("INFO", "Mother v2 控制台已就绪")
        self.root.mainloop()


def main():
    panel = MotherPanel()
    panel.run()


if __name__ == "__main__":
    main()
