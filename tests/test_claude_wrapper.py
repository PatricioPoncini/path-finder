from __future__ import annotations

import json

import anthropic
import httpx
import pytest

from jobbot.claude import Claude
from jobbot.config import SetupError
from jobbot.matcher import MATCH_TOOL

RESPONSE = {
    "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
    "content": [{"type": "tool_use", "id": "tu_1", "name": "submit_matches",
                 "input": {"matches": [{"id": "1", "score": 77}]}}],
    "stop_reason": "tool_use", "stop_sequence": None,
    "usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 50,
              "cache_creation_input_tokens": 0},
}


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SetupError):
        Claude()


def test_tool_call_request_shape_and_parsing(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=RESPONSE)

    claude = Claude("claude-haiku-5-5")
    claude._client = anthropic.Anthropic(
        api_key="sk-test", http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    out = claude.tool_call("SYSTEM", "hola", MATCH_TOOL)
    assert out == {"matches": [{"id": "1", "score": 77}]}

    body = seen["body"]
    assert body["model"] == "claude-haiku-5-5"
    assert body["tool_choice"] == {"type": "tool", "name": "submit_matches"}
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert body["tools"][0]["input_schema"]["required"] == ["matches"]
    assert claude.usage.calls == 1 and claude.usage.cache_read_tokens == 50
