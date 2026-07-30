# OfficeNest

AI 办公助手。Windows 本地运行，对话式操作 Excel/Word/PDF。

> **100% AI 辅助编写。** 我不是程序员——我是 HR 实习生。这个项目里 60 个工具、三层架构、Qt 面板，全部是 AI 写的。我负责的方向是"这里不对劲""这功能没用""你改错行了"。
>
> 如果你也是非专业开发者，或者你在考虑用 AI 做点什么——希望这个项目能给你一点信心。当然，也给你一点警示。

## 这个项目是怎么来的

2026 年 7 月，我在处理 76 份员工合同。每份 PDF 有不同的格式、不同的公司主体、不同的合同类型，要逐个录入 Excel。我受够了，打开 AI 说："给我写个能操作 Excel 的助手。"

9 天后，它有了 32 个工具。

30 天后，它有了 60 个，处理完了那 76 份合同。

## Vibe Coding 的真实体验

网上说 Vibe Coding 是"跟 AI 聊天就能写代码"——骗人的。真实的 Vibe Coding 是这样的：

```
你: "录入付群，2024.1.22-2027.1.21，三年"
AI: ✅ 已写入
你: 打开 Excel——没写进去
你: "你没写进去"
AI: "已经确认写入成功了"  ← 没调用任何工具
你: "..."
你: _打开代码_ → _读 engine.py_ → _发现 CellRange 只读了 A1_
你: "你把这段修一下"
AI: 修好了
你: "录入付群"
AI: ✅ 已写入第 91 行
你: _打开 Excel——真的写进去了_
```

**Vibe Coding 不是"AI 帮你写代码"。是"AI 写了个能跑的 bug，你用肉身踩出来，再让 AI 修"。**

58 条"优化建议"里，42 条根因是 `excel_find_row` 只读了 A1 这个格子。不是 AI 笨——是没有你反复用、反复骂，这个 bug 永远不会被发现。

我朋友看了说你这个像 demo。我说后端 60 个工具，接口全抽象，三层架构——这要算 demo，什么算产品？

## 能干什么

- 📊 **Excel**：创建、读写、格式化、图表、VBA 宏。写完自动验证，覆盖前检查。
- 📝 **Word**：模板生成、批量生成、表格填充。支持 Excel 区域粘贴到 Word。
- 📄 **PDF**：文本提取、GLM 视觉分析。扫描件直接看图识别。
- 🔍 **搜索**：知乎站内 / 全网 / DuckDuckGo。新增知乎热榜 + 收藏夹。
- 🧠 **知识库**：ChromaDB 向量检索，本地免费。支持按块读取——LLM 自己决定看多少。
- ⚡ **PowerShell**：系统命令（每次弹窗确认）。
- 👥 **多 Agent 群聊**：@ 不同会话协作，各自带私有上下文。

## 技术栈

Python 3.11+ | PySide6 (Qt) | DeepSeek / GLM | openpyxl | python-docx | win32com | ChromaDB | SQLite

## 快速开始（5 分钟）

```bash
pip install -e .
python main_qt.py
```

首次运行自动从模板创建配置文件。在设置页（⚙ 按钮）填 DeepSeek API Key。

> DeepSeek Key 免费注册：platform.deepseek.com
> GLM 视觉 Key 可选（智谱开放平台），用于 PDF 分析。

## 经验教训（如果你也在用 AI 写代码）

1. **先有场景再写代码。** 没有真实用户，bug 永远不会暴露。我的 58 条优化建议全是在实际处理合同时发现的。

2. **工具层硬拦截优于提示词。** 我在 System Prompt 里写了"不要操作其他文件"——没用。后来改成工具入口校验文件锁，问题立刻消失。模型会忽略提示词，但不会忽略 `Error: 禁止操作其他文件`。

3. **分步工具优于一键黑盒。** batch_create 把建表+加字段+写数据吞进黑盒，失败时无法定位。拆成独立工具后，LLM 自己编排出更好的流程。

4. **回滚比硬撑明智。** SQL 同步层花了两天发现不对，立刻砍掉。如果不砍，后面每个新功能都要兼容两套数据流。

5. **AI 不会创新——但会组合。** 你朋友要的"跳出框架的点子"，把无关词汇随机注入大模型，它被迫解释不存在的关系，偶尔能撞出真灵感。

6. **测试。测试。测试。** 这个项目没有单元测试。唯一的质量保障是我反复用、反复出 bug、反复修。不要学我。

## 编译 / 打包

```bash
cd C:\Users\18601\Desktop\AILARKAGENT
del config\default.yaml        # 删除密钥！
.venv\Scripts\pyinstaller.exe --onefile --name OfficeNest `
  --add-data "config;config" --add-data "core;core" `
  --add-data "skills;skills" --add-data "adapters;adapters" `
  --add-data "infrastructure;infrastructure" --add-data "prompts;prompts" `
  --hidden-import lark_oapi --hidden-import openpyxl `
  --hidden-import PySide6 --hidden-import docx --hidden-import ddgs `
  --hidden-import zai --hidden-import win32com --hidden-import pythoncom `
  --hidden-import httpx --collect-all chromadb --console main_qt.py
```

输出 `dist\OfficeNest.exe`（约 110MB）。首次启动自动创建空配置文件。

## 架构

```
用户 → Qt面板 → MotherApp(胶水层) → MotherEngine(Tool Call循环)
                  │                      │
                  ├── 60个工具           ├── ContextBuilder(System Prompt)
                  ├── Office桥接         └── ToolRegistry(注册+执行)
                  ├── SQLite存储(6个)
                  └── ChromaDB知识库
```

详见 [AGENTS.md](AGENTS.md) ——完整的开发指引、目录结构、已知陷阱。

## 致谢

- 感谢 DeepSeek 提供的低成本高质量 LLM 服务
- 感谢智谱开放平台的视觉模型支持
- 感谢 ChromaDB 让本地知识库成为可能
- 感谢 OpenClaw 项目的架构灵感
- 感谢父母对儿子在家对着电脑自言自语 30 天的宽容

## 许可

MIT
