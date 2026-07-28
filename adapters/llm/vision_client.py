"""
统一视觉客户端 —— GLM 优先，商汤/SenseTime 备用。
所有 provider 走 httpx 异步调用，不再依赖 zai-sdk。
"""
import httpx


class VisionClient:
    """多 provider 视觉客户端，自动降级。"""

    PROVIDERS = {
        "glm": {
            "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            "model": "glm-4.6v-flash",
        },
        "sensetime": {
            "url": "https://token.sensenova.cn/v1/chat/completions",
            "model": "sensenova-6.7-flash-lite",
        },
    }

    def __init__(self, glm_key: str = "", sense_key: str = "",
                 priority: list[str] | None = None):
        self._keys = {"glm": glm_key, "sensetime": sense_key}
        self._priority = priority or ["glm", "sensetime"]

    async def analyze(self, image_b64: str, prompt: str) -> str:
        """分析 base64 图片，自动降级到备用 provider。"""
        if not image_b64.startswith("data:"):
            img_url = f"data:image/png;base64,{image_b64}"
        else:
            img_url = image_b64

        last_error = ""
        for prov in self._priority:
            key = self._keys.get(prov, "")
            if not key:
                continue
            info = self.PROVIDERS.get(prov, {})
            try:
                return await self._call(
                    info["url"], key, info["model"],
                    img_url, prompt,
                )
            except Exception as e:
                last_error = str(e)[:100]
                continue
        return f"❌ 所有视觉模型均调用失败（最后错误: {last_error}）"

    async def _call(self, url: str, key: str, model: str,
                     img_url: str, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": img_url}},
                            {"type": "text", "text": prompt},
                        ]
                    }],
                    "max_tokens": 2000,
                },
            )
            data = resp.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"] or ""
            raise Exception(data.get("error", {}).get("message", resp.text[:200]))
