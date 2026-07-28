"""
事件类型枚举。
所有模块通过统一的事件类型通信，不直接耦合。
"""
from enum import Enum


class EventType(str, Enum):
    """点分命名：{域}.{对象}.{动作}"""

    # ── 飞书域 ──
    FEISHU_MESSAGE_RECEIVED = "feishu.message.received"
    FEISHU_FILE_UPLOADED = "feishu.file.uploaded"
    FEISHU_CONNECTION_LOST = "feishu.connection.lost"
    FEISHU_CONNECTION_RESTORED = "feishu.connection.restored"

    # ── Mother 引擎域 ──
    MOTHER_ROUND_START = "mother.round.start"
    MOTHER_ROUND_END = "mother.round.end"
    MOTHER_TOOL_CALL_DECIDED = "mother.tool_call.decided"
    MOTHER_TASK_START = "mother.task.start"
    MOTHER_TASK_DONE = "mother.task.done"
    MOTHER_TASK_ERROR = "mother.task.error"

    # ── 工具执行域 ──
    TOOL_CALL_START = "tool.call.start"
    TOOL_CALL_DONE = "tool.call.done"
    TOOL_CALL_ERROR = "tool.call.error"
    TOOL_CALL_RETRY = "tool.call.retry"

    # ── Office 域 ──
    OFFICE_EXCEL_OPENED = "office.excel.opened"
    OFFICE_EXCEL_WRITTEN = "office.excel.written"
    OFFICE_EXCEL_CLOSED = "office.excel.closed"
    OFFICE_WORD_GENERATED = "office.word.generated"
    OFFICE_WORD_SAVED = "office.word.saved"

    # ── 存储域 ──
    STORAGE_MEMORY_SAVED = "storage.memory.saved"
    STORAGE_MEMORY_RETRIEVED = "storage.memory.retrieved"

    # ── 系统域 ──
    SYSTEM_CLIPBOARD_READ = "system.clipboard.read"
    SYSTEM_CLIPBOARD_WRITTEN = "system.clipboard.written"
    SYSTEM_FILE_CREATED = "system.file.created"
    SYSTEM_FILE_MODIFIED = "system.file.modified"

    # ── 错误域（自我修正链条） ──
    ERROR_MODULE_CRASH = "error.module_crash"
    ERROR_API_FORMAT = "error.api_format"
    ERROR_SELF_HEAL_ATTEMPT = "error.self_heal.attempt"
    ERROR_SELF_HEAL_SUCCESS = "error.self_heal.success"
    ERROR_SELF_HEAL_FAILED = "error.self_heal.failed"

    # ── 系统 ──
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_HEARTBEAT = "system.heartbeat"
