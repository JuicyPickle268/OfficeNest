"""文件系统桥接抽象接口"""
from abc import ABC, abstractmethod
from pathlib import Path


class IFileBridge(ABC):
    """本地文件系统操作"""

    @abstractmethod
    def list_dir(self, path: str, pattern: str = "*") -> list[Path]:
        """列出目录下匹配的文件。"""
        ...

    @abstractmethod
    def read_file(self, path: str) -> str:
        """读取文本文件。"""
        ...

    @abstractmethod
    def write_file(self, path: str, content: str) -> None:
        """写入文本文件。"""
        ...

    @abstractmethod
    def copy_file(self, src: str, dst: str) -> None:
        """复制文件。"""
        ...

    @abstractmethod
    def move_file(self, src: str, dst: str) -> None:
        """移动/重命名文件。"""
        ...

    @abstractmethod
    def delete_file(self, path: str) -> None:
        """删除文件。"""
        ...

    @abstractmethod
    def exists(self, path: str) -> bool:
        """检查文件/目录是否存在。"""
        ...
