"""
DeepSeek API 客户端，基于 OpenAI SDK。
支持流式输出 + 思考/回复分离。
"""
import json
from core.interfaces.llm_client import ILLMClient, LLMResponse
from core.interfaces.tool import ToolCall


class DeepSeekClient(ILLMClient):
    """
    使用 OpenAI SDK 调用 DeepSeek API。
    支持 thinking（思考）模式：蓝色=思考，绿色=回复。
    """

    def __init__(self, api_key: str, model: str = "deepseek-v4-pro",
                 base_url: str = "https://api.deepseek.com", temperature: float = 0.3):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._temperature = temperature

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """非流式调用（兼容旧接口）。"""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

        kwargs = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._temperature,
            "stream": False,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        msg = choice.message

        tool_calls = self._parse_tool_calls(msg)
        await client.close()

        return LLMResponse(
            content=msg.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=self._extract_usage(response.usage),
        )

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        on_token: callable = None,  # on_token(type: str, text: str)
    ) -> LLMResponse:
        """
        流式调用，实时回调每个 token。
        on_token("thinking", text) → 思考过程
        on_token("content", text) → 回复内容
        on_token("tool", name) → 工具调用
        """
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

        kwargs = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        stream = await client.chat.completions.create(**kwargs)

        content_parts = []
        thinking_parts = []
        tool_calls_acc: dict[int, dict] = {}  # index → {id, name, args_str}
        usage = {}

        try:
            async for chunk in stream:
                if chunk.usage:
                    usage = {
                        "prompt_tokens": chunk.usage.prompt_tokens or 0,
                        "completion_tokens": chunk.usage.completion_tokens or 0,
                        "total_tokens": chunk.usage.total_tokens or 0,
                    }

                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # 思考内容 (reasoning_content)
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    thinking_parts.append(delta.reasoning_content)
                    if on_token:
                        on_token("thinking", delta.reasoning_content)

                # 正文内容
                if delta.content:
                    content_parts.append(delta.content)
                    if on_token:
                        on_token("content", delta.content)

                # 工具调用
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {"id": "", "name": "", "args_str": ""}
                        if tc.id:
                            tool_calls_acc[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_acc[idx]["name"] = tc.function.name
                                if on_token:
                                    on_token("tool", tc.function.name)
                            if tc.function.arguments:
                                tool_calls_acc[idx]["args_str"] += tc.function.arguments

        finally:
            try:
                await stream.close()
            except Exception:
                pass
            try:
                # 直接关闭底层 httpx response（防止 SSEDecoder aclose 未 await）
                resp = getattr(stream, 'response', None)
                if resp is not None:
                    await resp.aclose()
            except Exception:
                pass
            await client.close()

        # 组装结果
        content = "".join(content_parts)
        thinking = "".join(thinking_parts)

        tool_calls = []
        for idx in sorted(tool_calls_acc.keys()):
            tc = tool_calls_acc[idx]
            if tc["name"]:
                try:
                    args = json.loads(tc["args_str"])
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(id=tc["id"], name=tc["name"], arguments=args))

        return LLMResponse(
            content=content or None,
            thinking=thinking or None,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            usage=usage,
        )

    @staticmethod
    def _parse_tool_calls(msg) -> list[ToolCall]:
        result = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                result.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return result

    @staticmethod
    def _extract_usage(u) -> dict:
        if u:
            return {"prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens, "total_tokens": u.total_tokens}
        return {}
