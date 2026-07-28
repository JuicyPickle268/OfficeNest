# OfficeNest — AI 开发指引

> 读完此文件再改代码。

## 项目身份

- **名字**: OfficeNest（AI 办公助手）
- **定位**: Windows 本地运行，操作 Excel/Word，对话式办公
- **技术栈**: Python 3.11+ | PySide6 | DeepSeek | openpyxl | python-docx | win32com | ChromaDB
- **诞生**: 100% AI 辅助编写，非计算机专业开发者 + AI

## 架构概览

```
用户输入（Qt面板 / Chainlit / 飞书）
        │
        ▼
   MotherApp (main.py) —— 胶水层，组装所有模块
        │
        ▼
   MotherEngine (core/mother/engine.py) —— Tool Call 循环
        ├── ILLMClient → DeepSeek / GLM / 商汤
        ├── ContextBuilder → System Prompt + 用户偏好
        └── ToolRegistry → 60+ 工具
              │
              ▼
         Skills (skills/) —— LLM 可调用的工具
              │
              ▼
         Adapters (adapters/) —— 外部依赖
              ├── llm/     (DeepSeek, GLM, SenseTime)
              ├── office/  (win32com + openpyxl + python-docx)
              ├── storage/ (SQLite: memory, opt, user, scratch, file_registry)
              ├── search/  (web, zhihu)
              └── feishu/  (gateway)
```

## 核心设计原则

1. **外部依赖通过 core/interfaces/ 的 ABC 抽象**——换模型、换存储、换 Office 实现只需改适配器
2. **Excel 是工作室，Word 是产出物**——复杂表格 Excel 建好粘贴到 Word
3. **System Prompt 是 LLM 的行为契约**——改工具必须同步更新 context_builder.py
4. **文件路径走 _fix_path**——ExcelSkill/WordSkill 各有一套，处理所有脏路径

## 目录结构

```
config/             配置（YAML + dataclass schema）
  default.yaml      主配置（API Key、模型、路径）
  models.yaml       模型注册表（LLM 可写入）
  schema.py         配置模型（dataclass + load_config）
core/
  mother/           核心引擎
    engine.py       Tool Call 循环
    context_builder.py  System Prompt 构建
    tool_registry.py    工具注册 + Schema 生成
  interfaces/       所有 ABC 接口（10个）
  events/           事件总线（发布/订阅）
adapters/
  llm/              LLM 客户端
    deepseek_client.py  OpenAI 兼容客户端
    glm_vision.py       GLM 视觉（zai-sdk）
    vision_client.py    统一视觉客户端（GLM+商汤）
  office_bridge.py   Excel/Word 操作封装（win32com + openpyxl + python-docx）
  excel_sync.py      Excel → SQLite 同步
  knowledge_base.py  ChromaDB 向量知识库
  search_agent.py    搜索聚合（DDG + Bing）
  file_registry.py   文件注册表（SQLite）
  memory_store.py    对话持久化 + 会话管理（SQLite）
  opt_store.py       优化建议存储（SQLite）
  user_store.py      用户偏好管理（SQLite）
  scratch_store.py   AI 临时草稿纸（SQLite KV）
  table_renderer.py  终端表格渲染
  feishu/            飞书网关
skills/              LLM 可调用工具（60+ 个，12 个模块）
  excel_skill.py     Excel 操作（9 工具）
  word_skill.py      Word 操作（7 工具 + 2 联动）
  vision_skill.py    视觉/PDF（5 工具 + excel_understand）
  system_skill.py    文件管理 + 搜索（10 工具）
  chart_skill.py     图表（1 工具）
  clipboard_skill.py 剪切板（2 工具）
  kb_skill.py        知识库（3 工具）
  opt_skill.py       优化建议（4 工具）
  workflow_skill.py  工作流（3 工具）
  scratch_skill.py   草稿纸（4 工具）
  vba_skill.py       Excel VBA（2 工具）
  powershell_skill.py PowerShell（1 工具）
  model_skill.py     模型管理（3 工具）
  user_skill.py      用户偏好（2 工具）
panel/
  panel_qt.py        Qt 面板（主面板，1500+ 行）
  chainlit_app.py    Chainlit 手机端
infrastructure/
  logger/            5 层日志（events → tasks → steps → patterns → metrics）
prompts/             LLM 提示词模板
tests/               测试文件
main.py              主入口（MotherApp + CLI）
main_qt.py           Qt 面板入口
```

## 关键数据流

### 用户发消息 → 得到回复

```
panel_qt._send_command("帮我查合同表")
    → MotherApp.process(user_input, session_id, user_id)
        → 加载历史 / 文件列表 / 用户偏好
        → engine.process(user_message, chat_history, user_prefs, on_token)
            → context_builder.build(所有上下文) → messages
            → llm_client.chat(messages, tools)
            → LLM 返回 tool_calls → tool_registry.execute(tc)
            → 工具结果注入 messages → 循环
            → 最终纯文本 → 返回
        → 保存到 chat_history
        → 追踪文件路径（防漂移）
    → StreamBuffer 渲染到面板
```

### 启动引擎 → 加载用户

```
_start_engine()
    → 读模型下拉 → 选 provider/key/base_url
    → MotherApp(config_path) → 组装所有模块
    → _refresh_sessions()   → 侧边栏会话列表
    → _refresh_user_dropdown() → 用户下拉
    → _load_history()       → 最近对话
```

## 已知陷阱

1. **word_fill_table 不能填含合并单元格的表格**——用 Excel 建表 + 粘贴
2. **zai-sdk 是同步的**——GLM 调用不要用 asyncio
3. **Qt 流式用 StreamBuffer**——token 不能逐字 insert，会卡死
4. **飞书回调在 WS 线程**——不要在里面做重操作
5. **.doc 不支持**——提示用户另存为 .docx
6. **Word 新建默认 Visible=False**
7. **上下文窗口从配置读取**（context_rounds，0=无限）
8. **VBA 需 Excel 信任中心**开启"信任对 VBA 工程对象模型的访问"
9. **powershell_run 为危险工具**——每次执行弹窗确认
10. **知识库首次使用需下载 ChromaDB 本地嵌入模型**（79MB），已配置 hf-mirror.com 镜像
11. **拖放文件到输入框**——DropLineEdit 子类自动识别

## 废弃但代码仍在的模块

- `panel/admin_panel.py`（tkinter，已删除）
- `skills/improvement_skill.py`（已删除）
- `adapters/improvement_tracker.py`（已删除）
- `adapters/word_renderer.py`（已删除）
- `adapters/prompt_optimizer.py`（已删除）
- `api_server.py`（已删除）
- `web/` 目录（已删除）
- `reflex/` 相关（已删除）

## 当前状态（v2.2 — 2026-07-28）

- **60+ 个工具**，涵盖 Excel/Word/PDF/VBA/PowerShell/搜索/知识库/工作流
- **多模型热切换**：运行时切换 provider/key/base_url
- **用户系统**：多用户 + 个性化 prompt（AI 可读写）
- **多 Agent 群聊**：@ 会话协作
- **Chainlit 手机端**：`chainlit run panel/chainlit_app.py`
- **双面板**：Qt 桌面 + Chainlit 手机
- **建议 + 知识库**：ChromaDB + SQLite

