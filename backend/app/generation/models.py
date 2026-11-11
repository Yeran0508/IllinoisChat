from typing import Protocol

import httpx


class ChatModelError(RuntimeError):
    pass


class ChatModelProvider(Protocol):
    model_name: str

    def complete(self, *, system_prompt: str, user_prompt: str) -> str: ...


class OpenAICompatibleChatModel:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_name: str,
        timeout_seconds: float,
        reasoning_effort: str = "none",
        client=None,
    ) -> None:
        self.model_name = model_name
        self.reasoning_effort = reasoning_effort
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        try:
            response = self._client.post(
                "/chat/completions",
                json={
                    "model": self.model_name,
                    "temperature": 0,
                    "reasoning_effort": self.reasoning_effort,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
            return str(payload["choices"][0]["message"]["content"])
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            raise ChatModelError(f"Chat model request failed: {error}") from error
