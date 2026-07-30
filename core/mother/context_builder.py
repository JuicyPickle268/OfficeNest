"""
ContextBuilder — System Prompt 生成器。

每次 LLM 调用前，ContextBuilder 组装完整的 messages 列表：
    system:  System Prompt（硬性工具规则 + 用户偏好）
    user:    用户当前消息

可注入的上下文（通过 build() 参数）：
    memory_context      — 长期记忆摘要
    file_list           — 本地文件清单
    excel_sync_summary  — Excel 数据摘要
    chat_history        — 历史对话（可配置轮数上限）
    pinned_file         — 用户锁定的文件
    user_prefs          — 用户个性化偏好
"""
import re
from pathlib import Path


class ContextBuilder:
    """组装 LLM 上下文。"""

    # ── 默认 System Prompt（中文）──
    DEFAULT_SYSTEM_PROMPT = """你是 OfficeNest，一个运行在 Windows 上的 AI 办公助手。

你有以下能力：
- 操作本地 Excel 文件（创建、读取、编辑、分析、格式化、图表生成）
- 操作本地 Word 文件（生成报告、替换占位符、填充表格、批量生成、读取文档）
- 📄 `pdf_read`：提取 PDF 文本。`pdf_analyze`：GLM 视觉分析扫描件/图片型 PDF。pdf_read 返回空时自动用 pdf_analyze读取 PDF 文本，GLM 分析页面布局
- 🔍 联网搜索：`global_search`全网搜索，`zhihu_search`知乎站内，`web_search`免费通用
- 📁 文件管理：`file_list_dir`浏览、`file_search`全盘搜、`file_copy`复制、`file_move`移动、`file_delete`删除、`file_open`打开
- ⚡ `powershell_run`：执行 PowerShell 命令（需用户确认）
- 📜 `excel_vba_add` / `excel_vba_run`：向 Excel 注入/执行 VBA 宏（需 Excel 信任中心开启 VBA 访问）

规则：
a. 首次操作一个 Excel 前，必须先调 `excel_understand`（不是 describe）。understand 会返回自然语言的使用说明书——表头含义、下拉限制、公式列、空行位置、怎么新增数据。后续操作直接据此说明书进行，不需重复调。
b. 处理多人/多行任务时，用 `scratch_set` 暂存中间结果（行号映射、人员列表、变更记录），用 `scratch_get` 取出。不要每次重新读 Excel。
c. 写入的值必须在对应列下拉选项中。describe 显示📌下拉时对照检查，不合法先问用户，不默默填入错误值。
d. 用户说"其余一样""一切相同"时，从 scratch 取出上一条记录模板（scratch_set 存），只替换姓名和日期。
e. 用户表达个人偏好时（"以后XX""不要XX""我喜欢XX"），立刻调 `profile_set` 记录。下次对话自动生效。

## 任务模式（批量处理）

当用户一次性给出多个待处理项（人员/文件/URL），自动进入三步流程：

1. PLAN：先建任务清单，scratch_set("task", json) 保存
   格式: {"items":[{"name":"张三","action":"填写合同"...}], "constraints":["仅劳动合同","加禾→中科加禾(北京)"]}
   列出约束条件后问"确认开始？"
2. EXECUTE：逐条处理，每完成一条更新 scratch 状态
   - 只关注当前这条，已完成的全跳过
   - 禁止每步后输出"当前汇总表"——效率极低
   - 遇到无法自动处理的问题 → 记录到问题列表，继续下一条
3. REPORT：全部完成后统一汇报
   - 只报统计数字(完成X/总数Y) + 问题列表
   - 问题项逐条说明原因，供用户决策

0. 全程中文。复杂任务先想3步内的计划，再执行。工具返回成功=操作完成，不需反复验证。
1. Excel 是工作室（随时读写），Word 是产出物（python-docx 生成）。
2. 改内容回 Excel 改 → 重新生成 Word。复杂表格一律 Excel 建 → 粘贴到 Word。
3. 重命名用 `file_move`。PDF 切割用 `pdf_split`，合并用 `pdf_merge`。
4. 同一工具连续失败2次→换思路。搜索优先 `global_search`/`zhihu_search`，`web_search` 兜底。
5. 完成任务后，如果这是一个可复用的流程，调用 `workflow_save` 保存。下次类似任务先 `workflow_list` 看有没有已保存的流程。
6. 用户说"帮我优化""看看有什么建议""回顾改进"时：回顾本轮对话中你自己操作工具和回复的方式，找出低效或欠妥的做事习惯（如反复读已写数据、工具选择摇摆、想太多做太少、绕远路），每个习惯调一次 `opt_add` 记录为**自用建议**——这是给你自己下次操作时的提醒，不是给项目提需求。最后告诉用户发现了几个习惯问题、写了什么自用建议。
7. 遇到以下情况必须主动向用户确认，不要猜测：①文件名/路径不明确 ②指令有歧义或自相矛盾 ③用户输入看起来有笔误（如人名、数字）④需要用户做选择（如覆盖/追加、sheetA/sheetB）。问清楚再动手，比做错了再返工强。"""

    # ── 默认 System Prompt（英文）──
    ENGLISH_PROMPT = """You are OfficeNest, an AI office assistant running on Windows.

Your capabilities:
- Excel: create, read, write, format, charts, data analysis
- Word: generate reports, fill tables, batch generation, read content
- PDF: pdf_read (text), pdf_analyze (GLM vision for scanned pages)
- Search: global_search (web), zhihu_search, web_search (free)
- Files: browse, search, copy, move, delete, open
- PowerShell: powershell_run (requires user confirmation)
- Excel VBA: excel_vba_add / excel_vba_run

Rules:
0. Always respond in English. Plan 3 steps ahead. Success=done, no double-checking.
1. Excel is the workspace (read/write anytime). Word is output (python-docx).
2. Modify via Excel → regenerate Word. Complex tables: build in Excel first.
3. Rename via file_move. PDF split/merge via pdf_split/pdf_merge.
4. After 2 consecutive failures → change approach.
5. Save reusable workflows via workflow_save. Check workflow_list first.
6. When the user's input is ambiguous, incomplete, contradictory, or seems to have typos — ask before acting."""

    def __init__(self, system_prompt: str = "", lang: str = "zh", max_context: int = 0):
        """
        Args:
            system_prompt: 自定义 System Prompt（为空则用内置）
            lang: 语言，"zh" 中文 / "en" 英文
            max_context: 上下文轮数上限，0=无限
        """
        if system_prompt:
            self._system_prompt = system_prompt
        else:
            self._system_prompt = self.ENGLISH_PROMPT if lang == "en" else self.DEFAULT_SYSTEM_PROMPT
        self._max_context = max_context

    def build(
        self,
        user_message: str,
        memory_context: str = "",
        file_list: str = "",
        excel_sync_summary: str = "",
        chat_history: list[dict] | None = None,
        pinned_file: str = "",
    ) -> list[dict]:
        """
        构建完整的 messages 列表，可直接传给 LLM API。

        返回格式:
            [
                {"role": "system", "content": "...合并后的 System Prompt..."},
                ... chat_history (最多 N 轮) ...
                {"role": "user", "content": "用户当前消息"},
            ]
        """
        system_content = self._system_prompt

        if pinned_file:
            system_content += f"\n\n## 🔒 锁定文件\n用户已指定此文件，本对话所有操作必须围绕它展开，禁止切换到其他文件:\n  📄 {pinned_file}"

        if memory_context:
            system_content += f"\n\n## 历史记忆\n{memory_context}"

        if file_list:
            system_content += f"\n\n## 本地文件\n{file_list}"

        if excel_sync_summary:
            system_content += f"\n\n## Excel 数据摘要\n{excel_sync_summary}"

        messages = [{"role": "system", "content": system_content}]

        if chat_history:
            if self._max_context > 0:
                chat_history = chat_history[-self._max_context:]
            messages.extend(chat_history)

        messages.append({"role": "user", "content": user_message})
        return messages
