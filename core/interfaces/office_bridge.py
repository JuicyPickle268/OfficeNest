"""Office 桥接抽象接口（Excel + Word）"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CellRange:
    """Excel 单元格区域"""
    sheet: str
    start: str       # 如 "A1"
    end: str = ""    # 如 "D10"，空表示单个单元格


@dataclass
class TableData:
    """表格数据（用于 Word 表格填充）"""
    headers: list[str]
    rows: list[list[str]]


class IOfficeBridge(ABC):
    """操作本地 Excel 和 Word，屏蔽 win32com 细节"""

    # ── Excel ──

    @abstractmethod
    async def excel_open(self, filepath: str, visible: bool = False) -> str:
        """打开 Excel 文件。返回会话 ID。visible=False 为后台操作。"""
        ...

    @abstractmethod
    async def excel_read(self, session_id: str, range_spec: CellRange) -> list[list]:
        """读取 Excel 区域数据。返回二维列表。"""
        ...

    @abstractmethod
    async def excel_write(self, session_id: str, range_spec: CellRange, data: list[list]) -> int:
        """写入 Excel 区域。返回写入行数。"""
        ...

    @abstractmethod
    async def excel_add_sheet(self, session_id: str, name: str) -> str:
        """添加 Sheet。返回 sheet 名称。"""
        ...

    @abstractmethod
    async def excel_save(self, session_id: str) -> None:
        """保存当前文件。"""
        ...

    @abstractmethod
    async def excel_save_as(self, session_id: str, filepath: str) -> None:
        """另存为。"""
        ...

    @abstractmethod
    async def excel_close(self, session_id: str) -> None:
        """关闭文件，释放 Excel 进程。"""
        ...

    # ── Word ──

    @abstractmethod
    async def word_open(self, filepath: str, visible: bool = False) -> str:
        """打开 Word 文件。返回会话 ID。"""
        ...

    @abstractmethod
    async def word_replace(self, session_id: str, placeholder: str, value: str) -> int:
        """全文替换占位符。返回替换次数。如 {日期} → 2026-07-17"""
        ...

    @abstractmethod
    async def word_fill_table(self, session_id: str, table_index: int, data: TableData) -> int:
        """填充 Word 中的表格。table_index 从 1 开始。返回填充行数。"""
        ...

    @abstractmethod
    async def word_refresh_fields(self, session_id: str) -> None:
        """刷新所有链接字段（如 Excel 链接）。"""
        ...

    @abstractmethod
    async def word_save_as(self, session_id: str, filepath: str) -> None:
        """另存为。"""
        ...

    @abstractmethod
    async def word_close(self, session_id: str) -> None:
        """关闭文件。"""
        ...
