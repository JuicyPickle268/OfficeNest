# AI 开发指引

你是接续 OfficeNest 项目开发的 AI。请在修改任何代码前，先读完此文件。

## 项目身份

- 名字：OfficeNest（AI 办公助手）
- 定位：Windows 本地运行，操作 Excel/Word，飞书远程收发指令
- 技术栈：Python 3.11 + PySide6 + openpyxl + python-docx + win32com + lark-oapi + DeepSeek

## 核心设计原则（不可违背）

### 1. Excel 是工作室，Word 是产出物
- Excel：win32com 热模式 + openpyxl 冷模式自动切换。用户开着文件时实时操作。
- Word：python-docx 为主。不要尝试 win32com 热编辑 Word（已反复失败）。
- 复杂表格一律 Excel 建 + 粘贴到 Word。不在 Word 里挣扎合并单元格。

### 2. 所有外部依赖通过 core/interfaces/ 的 ABC 抽象
- 换 LLM、换 Office 实现、换存储——只改适配器，不改核心逻辑。
- 新增任何模块前，先看 interfaces/ 里有没有对应接口。

### 3. System Prompt 是 LLM 的行为契约
- `core/mother/context_builder.py` 的 `DEFAULT_SYSTEM_PROMPT`
- 修改工具行为时，必须同步更新提示词。

### 4. 文件路径处理走 `_fix_path`
- ExcelSkill 和 WordSkill 各自有 `_fix_path` / `_ensure_docx`
- 它们处理了 `.`、空路径、无后缀、绝对路径等所有脏情况
- 新增文件操作工具必须复用这些方法

## 目录结构速查

```
config/         → 配置（YAML + dataclass schema）
core/
  events/       → 事件总线（发布/订阅）
  interfaces/   → 所有 ABC 接口定义
  mother/       → 核心引擎
    engine.py         → Tool Call 循环
    context_builder.py → System Prompt
    tool_registry.py   → 工具注册+Schema生成
adapters/
  office_bridge.py     → Excel/Word 操作封装
  excel_sync.py        → Excel→SQLite 同步
  file_registry.py     → 文件注册表（SQLite）
  memory_store.py      → 对话持久化（SQLite）
  llm/
    deepseek_client.py → DeepSeek API
    glm_vision.py      → GLM 视觉（zai-sdk）
  feishu/
    ws_client.py       → 飞书 WebSocket
    http_client.py     → 飞书 HTTP API
    gateway.py         → 统一网关
  search_agent.py      → 搜索聚合（DDG+Bing）
skills/
  excel_skill.py       → 9 Excel 工具
  word_skill.py        → 7 Word 工具 + 2 联动工具
  vision_skill.py      → 4 视觉/PDF 工具
  chart_skill.py       → 图表工具
  system_skill.py      → 文件管理+搜索
  clipboard_skill.py   → 剪切板
  improvement_skill.py → 需求追踪（已废弃但代码还在）
panel/
  panel_qt.py          → PySide6 面板（当前主面板）
  admin_panel.py       → tkinter 面板（旧，保留）
infrastructure/
  logger/              → 5层日志（events→tasks→steps→patterns→metrics）
tests/                 → 测试文件（大部分已删除）
main.py                → 主入口
main_qt.py             → Qt 面板入口
main_web.py            → Web 面板入口
api_server.py          → FastAPI 服务（已废弃但保留）
```

## 已知陷阱

1. **不要用 word_fill_table 填充含合并单元格的表格**——用 Excel 建表+粘贴。
2. **zai-sdk 是同步的**，GLM 调用不要用 asyncio。
3. **Qt 流式用 StreamBuffer**，token 不能逐字 insert 会卡死。
4. **飞书 SDK 事件处理器在 WS 线程回调**，不要在那里做重操作。
5. **.doc 格式不支持**——提示用户另存为 .docx。
6. **面板已简化为 5 标签页**：仪表盘/日志/建议/知识库/设置。考试中心和需求追踪已删除。
7. **Word 新建进程默认 Visible=False**，不要在用户面前弹 Word 窗口。
8. **上下文窗口已改为无上限**（`context_builder.py:78`），不再截断 chat_history。面板支持 📌 锁定文件——用户在输入框上方指定路径后，所有操作围绕该文件展开。
9. **VBA 操作需 Excel 信任中心**：文件→选项→信任中心→信任中心设置→宏设置→勾选「信任对 VBA 工程对象模型的访问」，否则 `excel_vba_add` 报错。
10. **powershell_run 为危险工具**，启用后会弹窗确认。

## 被废弃但代码仍在的模块

- `panel/admin_panel.py`（tkinter 旧面板）
- `skills/improvement_skill.py`（suggestion 系统）
- `adapters/improvement_tracker.py`（需求追踪 SQLite）
- `adapters/word_renderer.py`（Word 预览渲染器）
- `api_server.py`（FastAPI Web 服务）
- `tests/` 目录（大部分测试文件已删）

这些可以安全删除，但不用主动删——先确认没有依赖。

## 优化建议系统（opt_suggestions）

### 是什么
用户用自然语言让 LLM 回顾对话，发现低效模式并生成优化建议。之后 LLM 执行工具前自动检查相关建议。

### 完整链路
```
用户: "帮我优化一下"
    │
    ▼
LLM 回顾对话中的工具调用 + 思考过程
    │
    ▼
LLM 调用 opt_add(tool="excel_read", suggestion="...", reason="重复验证", severity=2)
    │
    ▼
存入 SQLite 表 opt_suggestions
    │
    ▼
LLM 下次调 excel_read 前: opt_check("excel_read") → "💡 ..."
    │
    ▼
用户可在面板"建议"标签页查看、导出CSV、从CSV导入
```

### 触发方式
自然语言：用户说"帮我优化""看看有什么建议""回顾改进"等。LLM 按 System Prompt 规则 6 执行。

### 涉及的文件
- `adapters/opt_store.py` — OptStore 类，SQL CRUD（add/get_by_tool/mark_applied）
- `skills/opt_skill.py` — 4 个工具：opt_add（写建议）、opt_check（查建议）、opt_export、opt_import
- `core/mother/context_builder.py` — System Prompt 规则 6 定义触发方式
- `main.py` — MotherApp 初始化 opt_store，注册 OptimizationSkill
- `panel/panel_qt.py` — "建议"标签页（QTreeWidget，懒加载，index 2）
- `adapters/prompt_optimizer.py` — 旧规则引擎（已停用，代码保留）

## 当前状态（v2.1 — 2026-07-22 封存）

### 工具清单：36 个

| 模块 | 工具 | 新增于本轮 |
|---|---|---|
| Excel | excel_create/read/write/add_sheet/append_rows/find_row/delete_rows/get_sheets/format_range | |
| Word | word_create_from_scratch/generate/fill_table/batch_generate/append_paragraph/insert_image/read/read_table | |
| 联动 | excel_paste_to_word / excel_chart_to_word | |
| 视觉 | pdf_read/pdf_analyze/excel_describe_format/word_describe_format | |
| 图表 | excel_generate_chart | |
| 文件 | file_list_dir/search/copy/move/delete/open | |
| 搜索 | global_search/zhihu_search/web_search | |
| 剪切板 | clipboard_read/write | |
| 优化 | opt_add/opt_check/opt_export/opt_import | 🆕 |
| 工作流 | workflow_save/list/run | 🆕 |
| 知识库 | kb_search/kb_registry | 🆕 |
| 草稿纸 | scratch_set/get/delete/list | 🆕 |
| VBA | excel_vba_add / excel_vba_run | 🆕 |
| PowerShell | powershell_run（需确认） | 🆕 |

### 面板：5 标签页 + 侧边栏

仪表盘 / 日志 / 建议 / 知识库 / 设置

仪表盘增加：📌 文件锁定输入栏、强制停止按钮、文件路径自动追踪
建议标签页：QTreeWidget + 工具筛选 + 右键删除 + 清空
知识库标签页：文档列表 + 右键删除
侧边栏：💬 会话列表 + 右键重命名/删除 + 新建
命令输入框：@ 会话补全 → 多 Agent 群聊轮询

### 本轮核心修复

| 修复 | 文件 | 影响 |
|---|---|---|
| find_row 只读 A1 的致命 bug | office_bridge._excel_read_cold/hot | find_row/append/delete 三个工具复活 |
| excel_write 写后回读 + overwrite 检查 | excel_skill.py | 不再覆盖数据、不再凭空说"已写入" |
| 文件锁工具层硬拦截 | excel_skill._check_lock | 锁定文件后 LLM 无法操作其他文件 |
| _fix_path 不再硬编码 ./workbooks/ | excel_skill.py | 走配置 workbooks_dir + 全盘搜索 fallback |
| 虚假成功声明拦截 | engine.py | 生成"已写入"但无 tool_call 时自动拦截 |
| 强制停止按钮 | engine.cancel() + threading.Event | 点击停止立即中断，不等轮次结束 |
| 上下文无上限 | context_builder.py | chat_history 不再截断到 20 轮 |
| excel_describe_format 升级 | vision_skill.py | 输出表头/下拉/公式/合并/冻结/空行 |
| scratch_store 草稿纸 | adapters/scratch_store.py | LLM 跨 tool call 暂存状态 |

### 三层架构（最终）

```
excel_describe_format → 形状感知（表头/验证/公式/布局）
scratch_store          → LLM 临时记事本（跨调用状态）
excel_skill            → 实际读写（带着感知操作）
```

### 已知未解决问题

- PDF 截断/重试逻辑（3 条建议待处理）
- 日期格式（YYYY-MM-DD vs 数字格式）
- excel_read 50 行输出限制
- LLM 思考过长（需提示词进一步调优）
