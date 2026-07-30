"""Qt 组件——StreamBuffer(流式缓冲) + DropLineEdit(拖放输入框)。"""
import threading
from PySide6.QtWidgets import QTextEdit, QLineEdit
from PySide6.QtCore import Qt, QTimer, Signal, QMimeData
from PySide6.QtGui import QTextCursor, QColor, QTextCharFormat, QPixmap, QImage


class StreamBuffer:
    """线程安全的流式缓冲。主线程定时器轮询，工作线程只管 push。"""
    def __init__(self, widget: QTextEdit, flush_ms: int = 50):
        self._w = widget
        self._buf: list[tuple[str, str]] = []
        self._hidden: list[str] = []
        self._lock = threading.Lock()
        self._active = True
        self._show_thinking = True
        self._timer = QTimer()
        self._timer.setInterval(flush_ms)
        self._timer.timeout.connect(self._flush)
        self._timer.start()

    def feed(self, tag: str, text: str):
        if not self._active: return
        with self._lock: self._buf.append((tag, text))

    def feed_line(self, tag: str, text: str):
        self.feed(tag, text + "\n")

    def set_thinking_visible(self, visible: bool):
        self._show_thinking = visible
        if visible:
            with self._lock:
                for text in self._hidden: self._buf.append(("THINK", text))
                self._hidden.clear()

    def _flush(self):
        if not self._active: return
        with self._lock:
            if not self._buf: return
            buf, self._buf = self._buf, []
        try:
            cursor = self._w.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            colors = {"USER": "#ce9178", "BOT": "#39ff14", "THINK": "#569cd6",
                      "TOOL": "#dcdcaa", "CHART": "#f0a0ff", "ERROR": "#f44747",
                      "INFO": "#4ec9b0", "TS": "#808080"}
            for tag, text in buf:
                if tag == "THINK" and not self._show_thinking:
                    self._hidden.append(text); continue
                fmt = QTextCharFormat()
                if tag in colors: fmt.setForeground(QColor(colors[tag]))
                cursor.insertText(text, fmt)
            self._w.setTextCursor(cursor); self._w.ensureCursorVisible()
        except RuntimeError: self._active = False

    def flush_now(self): self._flush()
    def stop(self): self._active = False; self._timer.stop()


class DropLineEdit(QLineEdit):
    """支持拖放文件 + 粘贴图片的输入框。"""
    image_pasted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent); self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()

    def dropEvent(self, event):
        md = event.mimeData()
        if md.hasUrls():
            for url in md.urls():
                path = url.toLocalFile()
                if path: self.setText(path); self.returnPressed.emit(); return
        elif md.hasImage(): self._handle_image(md)

    def insertFromMimeData(self, source: QMimeData):
        if source.hasImage(): self._handle_image(source)
        elif source.hasUrls():
            for url in source.urls():
                path = url.toLocalFile()
                if path: self.setText(path); self.returnPressed.emit(); return
        else: super().insertFromMimeData(source)

    def _handle_image(self, md: QMimeData):
        img = md.imageData()
        pix = QPixmap.fromImage(img) if isinstance(img, QImage) else QPixmap()
        if not pix.isNull():
            if pix.width() > 1024: pix = pix.scaledToWidth(1024, Qt.TransformationMode.SmoothTransformation)
            ba = pix.toImage().saveToBuffer("PNG")
            import base64
            b64 = base64.b64encode(ba.data()).decode()
            self.setText("看一下这张图片"); self.image_pasted.emit(b64); self.returnPressed.emit()
