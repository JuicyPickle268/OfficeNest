# adapters/ — 适配器层

实现 `core/interfaces/` 中定义的抽象接口。

## 文件

| 文件 | 实现接口 | 说明 |
|------|----------|------|
| `office_bridge.py` | IOfficeBridge | Excel/Word 操作（openpyxl + win32com） |
| `clipboard_bridge.py` | IClipboardBridge | Windows 剪切板读写 |
| `file_bridge.py` | IFileBridge | 本地文件系统操作 |
| `excel_sync.py` | — | Excel → SQLite 同步 |
| `llm/deepseek_client.py` | ILLMClient | DeepSeek API |
