# OfficeNest v2 完整项目说明书

## 项目身份
- **名称**: OfficeNest
- **定位**: Windows 本地 AI 办公助手，操作 Excel/Word，飞书远程收发指令
- **技术栈**: Python 3.11 + PySide6 + openpyxl + python-docx + win32com + DeepSeek + GLM-4.6V

## 目录树与文件说明

```
OfficeNest/
├── main.py                        入口（面板/CLI/飞书）
├── main_qt.py                     Qt 面板入口
├── main_web.py                    Web 面板入口（已废弃）
├── api_server.py                  FastAPI（已废弃）
├── AGENTS.md                      AI 开发指引（新 AI 接手时先读）
├── PROJECT_SPEC.md                本文件
├── README.md                      简介
│
├── config/
│   ├── default.yaml               配置模板（LLM/飞书/Office/存储）
│   ├── schema.py                  dataclass 配置模型 + YAML 加载
│   └── README.md                  配置层说明
│
├── core/
│   ├── events/
│   │   ├── types.py               EventType 枚举（33种事件）
│   │   ├── event.py               Event 数据类
│   │   └── bus.py                 SimpleEventBus 发布订阅
│   ├── interfaces/
│   │   ├── tool.py                ToolCall / ToolResult
│   │   ├── tool_registry.py       IToolRegistry 接口
│   │   ├── llm_client.py          ILLMClient + LLMResponse
│   │   ├── feishu_gateway.py      IFeishuGateway + FeishuMessage
│   │   ├── office_bridge.py       IOfficeBridge + CellRange/TableData
│   │   ├── clipboard_bridge.py    IClipboardBridge
│   │   ├── file_bridge.py         IFileBridge
│   │   ├── memory.py              IMemoryStore + MemoryEntry
│   │   ├── audit.py               IAuditStore + AuditRecord
│   │   └── file_registry.py       IFileRegistry + FileEntry
│   └── mother/
│       ├── engine.py              MotherEngine（Tool Call 循环核心）
│       ├── context_builder.py     System Prompt 生成（中英文）
│       └── tool_registry.py       ToolRegistry 实现（注册+Schema+执行）
│
├── adapters/
│   ├── office_bridge.py            Excel/Word 操作封装（win32com+openpyxl+python-docx）
│   ├── excel_sync.py              Excel → SQLite 同步
│   ├── file_registry.py           文件注册表（SQLite）
│   ├── file_bridge.py             文件系统操作
│   ├── clipboard_bridge.py        剪切板读写
│   ├── memory_store.py            对话持久化 + 多会话管理
│   ├── knowledge_base.py          ChromaDB 向量知识库（含 DeepSeek Embedding）
│   ├── kb_agent.py                KB Agent（独立提示词，只负责入库）
│   ├── prompt_optimizer.py        提示词优化器（规则引擎）
│   ├── opt_store.py               优化建议 SQL 存储
│   ├── search_agent.py            搜索聚合（DDG+Bing）
│   ├── table_renderer.py          终端表格渲染
│   ├── word_renderer.py           Word 预览渲染器（已废弃）
│   ├── improvement_tracker.py     需求追踪（已废弃）
│   ├── proxy.py                   代理模块（已删除）
│   ├── feishu/
│   │   ├── ws_client.py          飞书 WebSocket 客户端
│   │   ├── http_client.py         飞书 HTTP API（发消息/上传文件）
│   │   └── gateway.py             FeishuGateway 统一入口
│   └── llm/
│       ├── deepseek_client.py     DeepSeek API（流式+非流式）
│       └── glm_vision.py          GLM-4.6V 视觉（zai-sdk，同步）
│
├── skills/
│   ├── base.py                    BaseSkill 基类
│   ├── excel_skill.py             9 个 Excel 工具
│   ├── word_skill.py              8 个 Word 工具 + 2 联动工具
│   ├── vision_skill.py            4 视觉/PDF 工具（读取/分析/切割/合并）
│   ├── chart_skill.py             图表工具（柱状图/折线图/饼图）
│   ├── system_skill.py            文件管理+搜索（6工具+3搜索）
│   ├── clipboard_skill.py         剪切板读写
│   ├── workflow_skill.py          工作流保存/列表/运行
│   ├── kb_skill.py                知识库搜索/注册表（通用 Agent 用）
│   ├── opt_skill.py               优化建议查询/导出/导入
│   └── improvement_skill.py       suggestion 工具（已废弃）
│
├── panel/
│   ├── panel_qt.py                PySide6 主面板（3标签：仪表盘/日志/设置）
│   └── admin_panel.py             tkinter 面板（已废弃）
│
├── infrastructure/
│   └── logger/
│       ├── schema.sql             5层日志建表语句
│       └── logger.py              Logger 实现（SQLite）
│
└── tests/
    └── test_phase0.py             Phase 0 验收测试
```

## 核心架构

用户 → 飞书/面板 → FeishuGateway → MotherEngine(ToolCall循环) → ToolRegistry → Skills → OfficeBridge → Excel/Word/文件

## 35 个工具清单

### Excel (9)
excel_create, excel_read, excel_write, excel_append_rows, excel_find_row, excel_delete_rows, excel_add_sheet, excel_get_sheets, excel_format_range

### Word (8)
word_create_from_scratch, word_generate, word_fill_table, word_batch_generate, word_append_paragraph, word_insert_image, word_read, word_read_table

### 联动 (2)
excel_paste_to_word, excel_chart_to_word

### 视觉/PDF (4 + 2)
pdf_read, pdf_analyze, pdf_split, pdf_merge, excel_describe_format, word_describe_format

### 图表 (1)
excel_generate_chart

### 文件管理 (6)
file_list_dir, file_search, file_copy, file_move, file_delete, file_open

### 搜索 (3)
global_search, zhihu_search, web_search

### 知识库 (2)
kb_search, kb_registry

### 工作流 (3)
workflow_save, workflow_list, workflow_run

### 优化建议 (3)
opt_check, opt_export, opt_import

### 剪切板 (2)
clipboard_read, clipboard_write

## 关键设计决策

1. **Excel 是工作室，Word 是产出物** —— win32com 热模式实时操作 Excel，python-docx 生成 Word
2. **热/冷双模式** —— Excel 打开时走 win32com，关闭时走 openpyxl，自动切换
3. **接口抽象** —— core/interfaces/ 定义所有 ABC，换实现只改适配器
4. **System Prompt 是 LLM 契约** —— 简单 5 条规则，效率优先
5. **知识库独立 Agent** —— KB Agent 只读+入库，通用 Agent 只搜，互不污染
6. **工作流系统** —— 完成复杂任务后保存，下次直接复用
7. **Zai-sdk 同步** —— GLM 调用不走 asyncio，避免事件循环冲突

## 配置

config/default.yaml 包含所有配置项。设置面板支持：DeepSeek/GLM/知乎 Key、模型选择、中英文切换、嵌入模型选择、优化器开关。

## 打包

```bash
pyinstaller --onefile --name OfficeNest \
  --add-data "config;config" --add-data "core;core" \
  --add-data "skills;skills" --add-data "adapters;adapters" \
  --add-data "infrastructure;infrastructure" \
  --hidden-import lark_oapi --hidden-import openpyxl \
  --hidden-import PySide6 --hidden-import docx \
  --hidden-import ddgs --hidden-import zai --hidden-import chromadb \
  main_qt.py
```

输出 dist/OfficeNest.exe (~130MB)。

## 已知陷阱

1. word_fill_table 不支持合并单元格（用 Excel 建表+粘贴替代）
2. zai-sdk 是同步的，GLM 调用不要用 asyncio
3. 飞书事件回调在 WS 线程，不要做重操作
4. .doc 格式不支持，提示用户另存为 .docx
5. Word 新建进程默认 Visible=False

---

*文档更新于 2026-07-22*
