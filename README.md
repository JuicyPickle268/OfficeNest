# OfficeNest

AI 办公助手。Windows 本地运行，对话式操作 Excel/Word/PDF 文件。

> 100% AI 辅助编写。非计算机专业开发者 + AI。

## 功能

聊着天就能操作文件：

- 📊 **Excel** — 创建、读写、格式化、图表、VBA 宏
- 📝 **Word** — 模板生成、批量生成、表格填充
- 📄 **PDF** — 文本提取、视觉分析
- 🔍 **搜索** — 知乎站内/全网/DuckDuckGo
- 🧠 **知识库** — ChromaDB 向量检索，本地免费
- ⚡ **PowerShell** — 系统命令（需确认）
- 🗂️ **文件管理** — 浏览、搜索、复制、移动

## 快速开始

```bash
pip install -e .
python main_qt.py
```

第一次打开会自动创建配置文件。在设置页填入 DeepSeek API Key（[platform.deepseek.com](https://platform.deepseek.com) 免费注册）。

## 技术栈

Python 3.11+ | PySide6 | DeepSeek | openpyxl | python-docx | win32com | ChromaDB

## 架构

```
用户输入 → MotherEngine (Tool Call 循环)
                │
    ┌───────────┼───────────┐
    ▼           ▼           ▼
  60工具     Office桥接   System Prompt
 (skills/)  (win32com/   (context_builder.py)
             openpyxl)
```

所有外部依赖通过 `core/interfaces/` 的 ABC 抽象，换模型/存储只改适配器不改核心。

## 项目结构

- `core/` — 引擎、接口、事件总线
- `adapters/` — LLM、Office、存储
- `skills/` — 60+ 个 LLM 可调用工具
- `panel/` — PySide6 Qt 面板
- `config/` — YAML 配置
- `prompts/` — LLM 提示词模板

详见 [AGENTS.md](AGENTS.md)。

## 许可

MIT
