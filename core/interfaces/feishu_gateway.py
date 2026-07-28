"""飞书网关抽象接口"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class FeishuMessage:
    """飞书消息结构"""
    id: str                             # 消息 ID（去重用）
    chat_id: str                        # 群聊或私聊 ID
    chat_type: str = "group"            # group | private
    sender_id: str = ""                 # 发送者 open_id
    text: str = ""                      # 消息文本
    mentioned: bool = False             # 是否 @了机器人
    files: list[str] = field(default_factory=list)  # 附带文件 URL 列表
    raw: dict = field(default_factory=dict)  # 飞书原始事件


class IFeishuGateway(ABC):
    """飞书通信抽象"""

    @abstractmethod
    async def start(self) -> None:
        """启动 WebSocket 长连接。"""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """关闭连接。"""
        ...

    @abstractmethod
    async def send_message(self, chat_id: str, text: str, files: list[str] | None = None) -> str:
        """发送文字消息到群聊/私聊。返回消息 ID。"""
        ...

    @abstractmethod
    async def upload_file(self, chat_id: str, file_path: str) -> str:
        """上传文件到群聊。返回文件 key。"""
        ...

    @abstractmethod
    def on_message(self, handler) -> None:
        """注册消息处理回调。handler(FeishuMessage) -> None"""
        ...
