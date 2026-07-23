"""
飞书 HTTP 客户端。
使用 tenant_access_token 调用飞书 REST API：发送消息、上传文件。
"""
import json
import time
import httpx
from pathlib import Path


class FeishuHTTPClient:
    """
    飞书 HTTP API 封装。
    - 自动获取/刷新 tenant_access_token
    - 发送文本消息
    - 上传文件到群聊
    """

    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self, app_id: str, app_secret: str):
        self._app_id = app_id
        self._app_secret = app_secret
        self._token: str = ""
        self._token_expires: float = 0
        self._client = httpx.Client(timeout=30)

    # ── Token ──

    def _ensure_token(self):
        """确保 token 有效，自动刷新。"""
        if self._token and time.time() < self._token_expires - 60:
            return
        resp = self._client.post(
            f"{self.BASE_URL}/auth/v3/tenant_access_token/internal",
            json={"app_id": self._app_id, "app_secret": self._app_secret},
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取 tenant_access_token 失败: {data.get('msg')}")
        self._token = data["tenant_access_token"]
        self._token_expires = time.time() + data.get("expire", 7200)

    # ── 消息 ──

    def send_text(self, chat_id: str, text: str, receive_id_type: str = "chat_id") -> dict:
        """发送文本消息。返回 API 响应。"""
        self._ensure_token()
        content = json.dumps({"text": text})
        resp = self._client.post(
            f"{self.BASE_URL}/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": content,
            },
        )
        return resp.json()

    # ── 文件上传 ──

    def upload_file(self, chat_id: str, filepath: str,
                    file_type: str = "", receive_id_type: str = "chat_id") -> dict:
        """
        上传文件到群聊。
        飞书文件类型：opus, mp4, pdf, doc, xls, ppt, stream
        """
        self._ensure_token()
        path = Path(filepath)
        if not path.exists():
            return {"code": -1, "msg": f"文件不存在: {filepath}"}

        # 自动判断文件类型
        if not file_type:
            suffix_map = {
                ".xlsx": "xls", ".xls": "xls",
                ".docx": "doc", ".doc": "doc",
                ".pdf": "pdf",
                ".png": "image", ".jpg": "image", ".jpeg": "image",
            }
            file_type = suffix_map.get(path.suffix.lower(), "stream")

        # Step 1: 上传文件获取 file_key
        with open(path, "rb") as f:
            resp = self._client.post(
                f"{self.BASE_URL}/im/v1/files",
                headers={"Authorization": f"Bearer {self._token}"},
                data={"file_type": file_type},
                files={"file": (path.name, f)},
            )
        upload_data = resp.json()
        if upload_data.get("code") != 0:
            return upload_data
        file_key = upload_data["data"]["file_key"]

        # Step 2: 发送文件消息
        content = json.dumps({"file_key": file_key})
        resp = self._client.post(
            f"{self.BASE_URL}/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={
                "receive_id": chat_id,
                "msg_type": "file",
                "content": content,
            },
        )
        return resp.json()

    def close(self):
        self._client.close()
