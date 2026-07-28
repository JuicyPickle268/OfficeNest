"""
GLM 视觉客户端——使用官方 zai-sdk（同步）。
支持图片 base64 + PDF 页面分析。
"""


class GLMVisionClient:
    """智谱 GLM-4.6V，官方 zai-sdk，同步调用。"""

    def __init__(self, api_key: str, model: str = "glm-4.6v-flash"):
        self._api_key = api_key
        self._model = model

    def analyze(self, image_b64: str, prompt: str, temperature: float = 0.3) -> str:
        """分析 base64 图片。"""
        from zai import ZhipuAiClient

        if not image_b64.startswith("data:"):
            img_url = f"data:image/png;base64,{image_b64}"
        else:
            img_url = image_b64

        client = ZhipuAiClient(api_key=self._api_key)
        response = client.chat.completions.create(
            model=self._model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": img_url}},
                    {"type": "text", "text": prompt},
                ]
            }],
        )
        return response.choices[0].message.content or ""

    def analyze_file(self, file_url: str, prompt: str, temperature: float = 0.3) -> str:
        """分析文件（PDF/Word 公网 URL）。"""
        from zai import ZhipuAiClient

        client = ZhipuAiClient(api_key=self._api_key)
        response = client.chat.completions.create(
            model=self._model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "file_url", "file_url": {"url": file_url}},
                    {"type": "text", "text": prompt},
                ]
            }],
        )
        return response.choices[0].message.content or ""
