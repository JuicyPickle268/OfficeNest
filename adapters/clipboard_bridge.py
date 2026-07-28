"""
剪切板桥接实现（Windows）。
"""
from core.interfaces.clipboard_bridge import IClipboardBridge


class ClipboardBridge(IClipboardBridge):
    """Windows 剪切板读写，基于 win32clipboard。"""

    def read_text(self) -> str:
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            try:
                data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                return data
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            return ""

    def write_text(self, text: str) -> None:
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text)
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            pass

    def read_image(self) -> bytes | None:
        try:
            import win32clipboard
            from PIL import ImageGrab
            img = ImageGrab.grabclipboard()
            if img:
                import io
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue()
            return None
        except Exception:
            return None

    def clear(self) -> None:
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            pass
