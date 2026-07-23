"""
文件系统桥接实现。
"""
from pathlib import Path
import shutil

from core.interfaces.file_bridge import IFileBridge


class FileBridge(IFileBridge):
    """本地文件系统操作。"""

    def list_dir(self, path: str, pattern: str = "*") -> list[Path]:
        p = Path(path)
        if not p.exists():
            return []
        return list(p.glob(pattern))

    def read_file(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def copy_file(self, src: str, dst: str) -> None:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    def move_file(self, src: str, dst: str) -> None:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dst)

    def delete_file(self, path: str) -> None:
        p = Path(path)
        if p.exists():
            p.unlink()

    def exists(self, path: str) -> bool:
        return Path(path).exists()
