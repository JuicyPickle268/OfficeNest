"""
统一视觉客户端 —— GLM(zai-sdk)优先，商汤(httpx)备用。
"""
import httpx


class VisionClient:
    """多 provider 视觉客户端，自动降级。"""

    def __init__(self, glm_key: str = "", sense_key: str = "",
                 priority: list[str] | None = None):
        self._keys = {"glm": glm_key, "sensetime": sense_key}
        self._priority = priority or ["glm", "sensetime"]

    async def analyze(self, image_b64: str, prompt: str) -> str:
        """分析图片，自动降级到备用 provider。"""
        last_error = ""
        for prov in self._priority:
            key = self._keys.get(prov, "")
            if not key:
                continue
            try:
                if prov == "glm":
                    return await self._call_glm(key, image_b64, prompt)
                elif prov == "sensetime":
                    return await self._call_sensetime(key, image_b64, prompt)
            except Exception as e:
                last_error = str(e)[:100]
                continue
        return f"❌ 所有视觉模型均调用失败（最后错误: {last_error}）"

    async def _call_glm(self, key: str, image_b64: str, prompt: str) -> str:
        """zai-sdk 调用 GLM-4.6V。"""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._call_glm_sync(key, image_b64, prompt)
        )

    def _call_glm_sync(self, key: str, image_b64: str, prompt: str) -> str:
        from zai import ZhipuAiClient
        if not image_b64.startswith("data:"):
            img_url = f"data:image/png;base64,{image_b64}"
        else:
            img_url = image_b64

        client = ZhipuAiClient(api_key=key)
        response = client.chat.completions.create(
            model="glm-4.6v",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": img_url}},
                    {"type": "text", "text": prompt},
                ]
            }],
        )
        return response.choices[0].message.content or ""

    async def _call_sensetime(self, key: str, image_b64: str, prompt: str) -> str:
        """httpx 调用商汤 SenseNova。"""
        if not image_b64.startswith("data:"):
            img_url = f"data:image/png;base64,{image_b64}"
        else:
            img_url = image_b64

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://token.sensenova.cn/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sensenova-6.7-flash-lite",
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
