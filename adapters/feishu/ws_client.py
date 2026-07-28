"""
飞书 WebSocket 客户端（重写）。
基于 lark-oapi SDK，双通道：群聊 @机器人 + 私聊。
"""
import asyncio
import json
import threading
import time

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from core.interfaces.feishu_gateway import FeishuMessage
from core.events.bus import SimpleEventBus
from core.events.event import Event
from core.events.types import EventType


class FeishuWSClient:
    """
    飞书 WebSocket 客户端。
    """

    def __init__(self, app_id: str, app_secret: str, event_bus: SimpleEventBus | None = None):
        self._app_id = app_id
        self._app_secret = app_secret
        self._bus = event_bus or SimpleEventBus()
        self._handler: callable | None = None
        self._running = False
        self._client: lark.ws.Client | None = None

    def on_message(self, handler):
        """注册消息回调。handler(FeishuMessage) -> None"""
        self._handler = handler

    def start_blocking(self):
        """阻塞式启动 WebSocket（在后台线程中调用）。"""
        self._running = True

        def _on_msg(data: P2ImMessageReceiveV1):
            try:
                msg = _parse(data)
                if msg and self._handler:
                    self._handler(msg)
                if self._bus:
                    self._bus.publish(Event(
                        type=EventType.FEISHU_MESSAGE_RECEIVED,
                        source="feishu.ws",
                        data={"text": msg.text[:100] if msg else ""},
                    ))
            except Exception:
                pass

        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(_on_msg)
            .register_p2_im_chat_member_bot_added_v1(lambda _: None)
            .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(lambda _: None)
            .register_p2_im_message_message_read_v1(lambda _: None)
            .build()
        )

        self._client = lark.ws.Client(
            self._app_id, self._app_secret,
            event_handler=handler,
            log_level=lark.LogLevel.WARNING,
        )

        self._bus.publish(Event(type=EventType.FEISHU_CONNECTION_RESTORED, source="feishu.ws", data={}))
        try:
            self._client.start()  # 阻塞
        except Exception as e:
            if self._running:
                self._bus.publish(Event(type=EventType.FEISHU_CONNECTION_LOST, source="feishu.ws", data={"error": str(e)}))

    def stop(self):
        self._running = False
        if self._client:
            try:
                self._client.stop()
            except Exception:
                pass


def _parse(data: P2ImMessageReceiveV1) -> FeishuMessage | None:
    """解析飞书事件。支持群聊 @机器人和私聊。"""
    try:
        evt = data.event
        if not evt or not evt.message:
            return None
        msg = evt.message

        # 文本提取
        text = ""
        if msg.message_type == "text" and msg.content:
            try:
                content = json.loads(msg.content)
                text = content.get("text", "")
            except json.JSONDecodeError:
                pass

        if not text:
            return None

        # 发送者
        sender_id = ""
        sender_type = ""
        if evt.sender:
            sender_type = evt.sender.sender_type or ""
            if evt.sender.sender_id:
                sender_id = evt.sender.sender_id.open_id or ""

        # 是否是 @机器人（群聊场景）
        mentioned = False
        if msg.mentions:
            for m in msg.mentions:
                # 被 @ 的如果是机器人（mentioned_type == "bot"）
                if hasattr(m, "mentioned_type") and m.mentioned_type == "bot":
                    mentioned = True
                    break

        # 私聊不要求 @
        chat_type = msg.chat_type or "group"

        return FeishuMessage(
            id=msg.message_id or "",
            chat_id=msg.chat_id or "",
            chat_type=chat_type,
            sender_id=sender_id,
            text=text,
            mentioned=mentioned,
            raw={"type": msg.message_type, "sender_type": sender_type},
        )
    except Exception:
        return None
