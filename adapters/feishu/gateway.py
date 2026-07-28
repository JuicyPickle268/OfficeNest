"""
飞书 Gateway：实现 IFeishuGateway。
"""
import asyncio
import threading
from core.interfaces.feishu_gateway import IFeishuGateway, FeishuMessage
from core.events.bus import SimpleEventBus
from adapters.feishu.ws_client import FeishuWSClient
from adapters.feishu.http_client import FeishuHTTPClient


class FeishuGateway(IFeishuGateway):

    def __init__(self, app_id: str, app_secret: str, event_bus: SimpleEventBus | None = None):
        self._ws = FeishuWSClient(app_id, app_secret, event_bus)
        self._http = FeishuHTTPClient(app_id, app_secret)
        self._ws_thread: threading.Thread | None = None

    def start(self):
        """启动 WebSocket（在后台线程中运行）。"""
        self._ws_thread = threading.Thread(target=self._ws.start_blocking, daemon=True)
        self._ws_thread.start()

    async def stop(self) -> None:
        self._ws.stop()
        self._http.close()

    async def send_message(self, chat_id: str, text: str, files: list[str] | None = None) -> str:
        result = self._http.send_text(chat_id, text)
        return result.get("data", {}).get("message_id", "")

    async def upload_file(self, chat_id: str, file_path: str) -> str:
        result = self._http.upload_file(chat_id, file_path)
        return result.get("data", {}).get("file_key", "")

    def on_message(self, handler) -> None:
        """handler 是同步函数：handler(FeishuMessage) -> None"""
        self._ws.on_message(handler)

    @property
    def is_connected(self) -> bool:
        return self._ws._running
