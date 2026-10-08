"""Exercise real LiteLLM dispatch and HTTP serialization, not injected completions."""

import asyncio
import json
from http.server import ThreadingHTTPServer
from threading import Thread

import pytest
from pydantic import BaseModel

from backend.shared.llm.litellm_gateway import LiteLLMCompletionGateway
from tools.mock_openai_provider import Handler, EXPECTED_API_KEY


CONTENT = '{"answer":"ok"}'
MESSAGES = [{"role": "user", "content": "ping"}]


@pytest.fixture
def provider_server(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    requests = []

    class RecordingHandler(Handler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, self.headers.get("Authorization"), body))
            common = {"id": "chatcmpl-routing", "created": 0, "model": body["model"]}
            if body.get("stream"):
                chunks = [
                    {**common, "object": "chat.completion.chunk", "choices": [
                        {"index": 0, "delta": {"content": CONTENT}, "finish_reason": None}]},
                    {**common, "object": "chat.completion.chunk", "choices": [
                        {"index": 0, "delta": {}, "finish_reason": "stop"}]},
                ]
                encoded = ("".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
                           + "data: [DONE]\n\n").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            else:
                self._json({**common, "object": "chat.completion", "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": CONTENT},
                     "finish_reason": "stop"}]})

    server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize(("provider", "model", "upstream_model"), [
    ("openai", "gpt-4o", "gpt-4o"),
    ("openai", "qwen-max", "qwen-max"),
    ("openai", "openai/gpt-4o", "gpt-4o"),
    ("openai", "group/auto-deepseek-v4-1-flash", "group/auto-deepseek-v4-1-flash"),
    ("openai", "meta-llama/Llama-3-70b", "meta-llama/Llama-3-70b"),
    ("custom_openai", "org/model-x", "org/model-x"),
    ("hosted_vllm", "org/model-x", "org/model-x"),
    ("openrouter", "anthropic/claude-3.5-sonnet", "anthropic/claude-3.5-sonnet"),
])
def test_selected_provider_controls_real_dispatch(provider_server, provider, model, upstream_model):
    base_url, requests = provider_server
    gateway = LiteLLMCompletionGateway(provider=provider, model=model, base_url=base_url,
                                       api_key=EXPECTED_API_KEY)
    assert gateway.complete_text(MESSAGES, timeout=5) == CONTENT
    path, authorization, body = requests.pop()
    assert path == "/v1/chat/completions"
    assert authorization == f"Bearer {EXPECTED_API_KEY}"
    assert body["model"] == upstream_model
    assert body["messages"] == MESSAGES
    assert "custom_llm_provider" not in body


@pytest.mark.parametrize("mode", ["async", "stream", "metadata_stream", "async_stream", "structured"])
def test_namespaced_models_work_in_all_gateway_modes(provider_server, mode):
    base_url, requests = provider_server
    gateway = LiteLLMCompletionGateway(provider="openai", model="group/model-x",
                                       base_url=base_url, api_key=EXPECTED_API_KEY)
    if mode == "async":
        result = asyncio.run(gateway.acomplete_text(MESSAGES, timeout=5))
    elif mode == "stream":
        result = "".join(gateway.stream_text(MESSAGES))
    elif mode == "metadata_stream":
        result = "".join(chunk.delta for chunk in gateway.stream_text_with_metadata(MESSAGES))
    elif mode == "async_stream":
        async def collect():
            return "".join([chunk async for chunk in gateway.astream_text(MESSAGES)])
        result = asyncio.run(collect())
    else:
        class Answer(BaseModel):
            answer: str
        assert gateway.complete_structured(MESSAGES, response_model=Answer).answer == "ok"
        result = CONTENT
    assert result == CONTENT
    assert len(requests) == 1
    assert requests[0][0] == "/v1/chat/completions"
    assert requests[0][2]["model"] == "group/model-x"
