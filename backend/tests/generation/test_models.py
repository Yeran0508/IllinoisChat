import json

import httpx
import pytest
from app.generation.models import ChatModelError, OpenAICompatibleChatModel


def test_openai_compatible_model_sends_grounded_json_request() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"sufficient": false}'}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://model.test/v1")
    model = OpenAICompatibleChatModel(
        base_url="http://unused.test/v1",
        api_key="secret",
        model_name="test-model",
        timeout_seconds=1,
        reasoning_effort="none",
        client=client,
    )

    result = model.complete(system_prompt="rules", user_prompt="question")

    assert result == '{"sufficient": false}'
    assert captured["model"] == "test-model"
    assert captured["temperature"] == 0
    assert captured["reasoning_effort"] == "none"
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["messages"][0] == {"role": "system", "content": "rules"}


@pytest.mark.parametrize(
    "response",
    [httpx.Response(503), httpx.Response(200, json={"choices": []})],
)
def test_openai_compatible_model_wraps_provider_failures(response) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: response),
        base_url="http://model.test/v1",
    )
    model = OpenAICompatibleChatModel(
        base_url="http://unused.test/v1",
        api_key="",
        model_name="test-model",
        timeout_seconds=1,
        client=client,
    )

    with pytest.raises(ChatModelError, match="Chat model request failed"):
        model.complete(system_prompt="rules", user_prompt="question")
