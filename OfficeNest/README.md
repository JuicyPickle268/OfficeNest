# OfficeNest

AI 办公助手 — 本地运行，对话式操作 Excel/Word，57 个工具，100% AI 编写。

## 能力

- 📊 **Excel**：创建、读写、格式化、图表、VBA 宏
- 📝 **Word**：模板生成、批量生成、表格填充
- 🔗 **联动**：Excel → Word 粘贴、图表嵌入
- 📄 **PDF**：文本提取、GLM 视觉分析
- 🔍 **搜索**：全网/知乎/DuckDuckGo
- ⚡ **PowerShell**：系统命令执行
- 🧠 **多 Agent 群聊**：@ 不同的会话协作
- 💾 **知识库**：ChromaDB 向量检索 + RAG

## 启动

```bash
pip install -r requirements.txt
python main_qt.py
```

首次使用在设置页填 DeepSeek API Key。

## 技术栈

Python 3.11+ | PySide6 | DeepSeek | openpyxl | python-docx | win32com | ChromaDB

## 架构

```
用户输入 → MotherEngine (Tool Call 循环)
                │
    ┌───────────┼───────────┐
    ▼           ▼           ▼
  Skills     Adapters    Context
  (57工具)   (win32com/  (System
              openpyxl/   Prompt)
              ChromaDB)
```

所有外部依赖通过 `core/interfaces/` 的 ABC 抽象，换 LLM/Office/存储只改适配器不改核心。

## 项目状态

v2.1 — 功能完整，100% AI 编写，详见 [AGENTS.md](AGENTS.md)
