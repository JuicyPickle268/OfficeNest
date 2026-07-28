# core/ — 核心层

此目录下的代码：
- ✅ 只定义接口（ABC）和纯数据结构（dataclass）
- ✅ 零外部依赖（不 import 飞书 SDK、openpyxl、win32com 等）
- ❌ 不包含任何具体实现代码

## 子目录

| 目录 | 说明 |
|------|------|
| `events/` | 事件系统（EventType、Event、EventBus） |
| `interfaces/` | 所有模块的抽象接口 |
