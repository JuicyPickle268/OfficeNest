# core/interfaces/ — 抽象接口层

所有模块之间的通信契约在此定义。

## 接口清单

| 接口 | 文件 | 核心职责 |
|------|------|----------|
| ToolCall / ToolResult | `tool.py` | 工具调用与结果的统一数据结构 |
| IToolRegistry | `tool_registry.py` | 工具注册、Schema生成、执行分发 |
| ILLMClient | `llm_client.py` | 大模型调用（DeepSeek） |
| IFeishuGateway | `feishu_gateway.py` | 飞书消息收发、文件上传 |
| IOfficeBridge | `office_bridge.py` | Excel + Word 操作（win32com） |
| IClipboardBridge | `clipboard_bridge.py` | Windows 剪切板读写 |
| IFileBridge | `file_bridge.py` | 本地文件系统操作 |
| IMemoryStore | `memory.py` | 长期记忆存储与检索 |
| IAuditStore | `audit.py` | 审计日志 |
| IFileRegistry | `file_registry.py` | 本地文件元数据管理 |

## 设计原则

- **依赖倒置**：上层模块依赖这些接口，不依赖具体实现
- **单一职责**：每个接口只管一件事
- **最小化**：接口方法只定义"必须有什么"，不定义"怎么实现"
- **无实现代码**：本目录不含任何 `class XXX(ABC)` 之外的逻辑

## 如何添加新接口

1. 在本目录新建文件
2. 定义 dataclass（如有）
3. 定义 ABC 类，标记 `@abstractmethod`
4. 在本 README 中登记
