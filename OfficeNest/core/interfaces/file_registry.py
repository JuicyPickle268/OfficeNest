"""文件注册表抽象接口"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class FileEntry:
    """一个已注册的文件"""
    name: str                          # 逻辑名称（如 "招聘数据"）
    path: str                          # 绝对路径
    file_type: str = ""                # excel | word | other
    tags: list[str] = field(default_factory=list)
    created_at: float = 0.0
    modified_at: float = 0.0
    last_synced_at: float = 0.0        # 上次同步到飞书的时间
    metadata: dict = field(default_factory=dict)


class IFileRegistry(ABC):
    """本地文件元数据管理：Mother 知道有哪些文件、在哪、什么类型"""

    @abstractmethod
    def register(self, entry: FileEntry) -> str:
        """注册一个文件。返回注册 ID。"""
        ...

    @abstractmethod
    def find(self, name: str | None = None, file_type: str | None = None, tag: str | None = None) -> list[FileEntry]:
        """按条件查找文件。"""
        ...

    @abstractmethod
    def list_all(self) -> list[FileEntry]:
        """列出所有已注册文件。"""
        ...

    @abstractmethod
    def update(self, name: str, **kwargs) -> None:
        """更新文件元数据。"""
        ...

    @abstractmethod
    def unregister(self, name: str) -> bool:
        """移除注册。返回是否成功。"""
        ...
