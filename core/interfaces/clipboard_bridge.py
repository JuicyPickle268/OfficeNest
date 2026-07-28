"""剪切板桥接抽象接口"""
from abc import ABC, abstractmethod


class IClipboardBridge(ABC):
    """Windows 剪切板读写"""

    @abstractmethod
    def read_text(self) -> str:
        """读取剪切板文本内容。"""
        ...

    @abstractmethod
    def write_text(self, text: str) -> None:
        """写入文本到剪切板。"""
        ...

    @abstractmethod
    def read_image(self) -> bytes | None:
        """读取剪切板图片（如有）。返回 PNG 字节或 None。"""
        ...

    @abstractmethod
    def clear(self) -> None:
        """清空剪切板。"""
        ...
