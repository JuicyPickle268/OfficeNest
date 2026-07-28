# OfficeNest

AI office assistant. Runs locally on Windows. Chat to operate Excel, Word, and PDF files.

> 100% AI-assisted development by a non-CS developer + AI.

## Capabilities

- 📊 **Excel** — create, read, write, format, charts, VBA macros
- 📝 **Word** — template generation, batch generation, table filling
- 📄 **PDF** — text extraction, visual analysis
- 🔍 **Search** — Zhihu, web, DuckDuckGo
- 🧠 **Knowledge Base** — ChromaDB vector search, local & free
- ⚡ **PowerShell** — system commands (with confirmation)
- 🗂️ **File Management** — browse, search, copy, move

## Quick Start

```bash
pip install -e .
python main_qt.py
```

On first launch, a config file is created automatically. Fill in your DeepSeek API Key in Settings ([platform.deepseek.com](https://platform.deepseek.com), free registration).

## Tech Stack

Python 3.11+ | PySide6 | DeepSeek | openpyxl | python-docx | win32com | ChromaDB

## Architecture

```
User Input → MotherEngine (Tool Call Loop)
                  │
      ┌───────────┼───────────┐
      ▼           ▼           ▼
  60 Tools    Office Bridge  System Prompt
  (skills/)   (win32com/    (context_builder.py)
               openpyxl)
```

All external dependencies are abstracted via ABCs in `core/interfaces/`. Swap models or storage by changing adapters only.

## Project Structure

- `core/` — Engine, interfaces, event bus
- `adapters/` — LLM, Office, storage
- `skills/` — 60+ LLM-callable tools
- `panel/` — PySide6 Qt panel
- `config/` — YAML configuration
- `prompts/` — LLM prompt templates

See [AGENTS.md](AGENTS.md) for full developer guide.

## License

MIT
