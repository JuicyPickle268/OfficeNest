# Panel — OfficeNest Qt 面板

## 文件

| 文件 | 行数 | 职责 |
|---|---|---|
| `panel_qt.py` | ~800 | 主窗口 + 仪表盘 + 会话管理 + 引擎启停 |
| `widgets.py` | ~100 | StreamBuffer（流式渲染）+ DropLineEdit（拖放粘贴） |

## 架构

```
MotherPanelQt (QMainWindow)
    │
    ├── 侧边栏 (QSplitter 左)
    │   ├── 会话列表 (QListWidget)
    │   ├── 📋 日志弹窗 → _show_log()
    │   ├── 📚 知识库弹窗 → _show_kb()
    │   ├── ⚙ 设置弹窗 → _show_settings()
    │   └── ＋ 新建会话
    │
    └── 仪表盘 (QSplitter 右)
        ├── 状态栏
        ├── 聊天区 (QTextEdit + StreamBuffer)
        ├── 工具栏 [模型▼] [■中断] [💭思考] [清空]
        ├── 📌 文件锁定栏
        └── 输入框 (DropLineEdit) + 发送按钮
```

## 核心方法

| 方法 | 说明 |
|---|---|
| `_start_engine()` | 读模型下拉 → 创建 MotherApp → 启动引擎 |
| `_send_command()` | 解析 @ 引用 → 路由到 _run_agent 或 _run_multi_agent |
| `_run_agent(text, session_id)` | 单 Agent 执行，流式显示 |
| `_run_multi_agent(text, @mentions)` | 多 Agent 群聊，逐个回复 |

## 弹窗

| 方法 | 触发 | 内容 |
|---|---|---|
| `_show_log()` | 📋 按钮 | 最近 200 条事件日志 |
| `_show_kb()` | 📚 按钮 | 知识库文档列表 |
| `_show_settings()` | ⚙ 按钮 | API Key 配置 |

## 依赖

- `panel/widgets.py` — StreamBuffer, DropLineEdit
- `main.py` — MotherApp（引擎容器）
- `core/mother/engine.py` — MotherEngine
- `config/schema.py` — load_config
