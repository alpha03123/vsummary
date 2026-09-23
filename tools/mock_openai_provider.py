"""A strict, deterministic OpenAI-compatible provider for PR E2E tests.

This process is deliberately outside the application.  VSummary still uses its
normal LiteLLM clients and performs an actual HTTP request to this server.
"""

from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


EXPECTED_API_KEY = os.environ.get("MOCK_OPENAI_API_KEY", "ci-test-key")
EXPECTED_MODEL = os.environ.get("MOCK_OPENAI_MODEL", "ci-e2e-model")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/v1/models":
            self._error(HTTPStatus.NOT_FOUND, "unsupported endpoint")
            return
        if self.headers.get("Authorization") != f"Bearer {EXPECTED_API_KEY}":
            self._error(HTTPStatus.UNAUTHORIZED, "unexpected authorization header")
            return
        self._json({"object": "list", "data": [{"id": EXPECTED_MODEL, "object": "model"}]})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self._error(HTTPStatus.NOT_FOUND, "unsupported endpoint")
            return
        if self.headers.get("Authorization") != f"Bearer {EXPECTED_API_KEY}":
            self._error(HTTPStatus.UNAUTHORIZED, "unexpected authorization header")
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            content = _response_content(body)
        except (KeyError, TypeError, ValueError) as error:
            self._error(HTTPStatus.BAD_REQUEST, str(error))
            return
        self._json(
            {
                "id": "chatcmpl-ci-e2e",
                "object": "chat.completion",
                "created": 0,
                "model": EXPECTED_MODEL,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        )

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def _json(self, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _error(self, status: HTTPStatus, detail: str) -> None:
        encoded = json.dumps({"error": {"message": detail, "type": "invalid_request_error"}}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def _response_content(request: dict[str, Any]) -> str:
    if request.get("model") != EXPECTED_MODEL:
        raise ValueError(f"unexpected model: {request.get('model')!r}")
    if not isinstance(request.get("messages"), list) or not request["messages"]:
        raise ValueError("messages must be a non-empty list")
    if request.get("stream") is True:
        raise ValueError("the PR E2E uses the non-streaming Talk endpoint")
    schema_name = _schema_name(request)
    _validate_prompt_contract(schema_name, request["messages"])
    payload = _payload_for_schema(schema_name)
    return json.dumps(payload, ensure_ascii=False) if payload is not None else "CI Mock 的固定文本回答。"


def _schema_name(request: dict[str, Any]) -> str | None:
    response_format = request.get("response_format")
    if not isinstance(response_format, dict):
        return None
    json_schema = response_format.get("json_schema")
    if isinstance(json_schema, dict) and isinstance(json_schema.get("name"), str):
        return json_schema["name"]
    return None


def _validate_prompt_contract(schema_name: str | None, messages: list[object]) -> None:
    text = "\n".join(
        str(item.get("content", ""))
        for item in messages
        if isinstance(item, dict)
    )
    if schema_name == "SummaryPayload" and "CI 端到端测试的固定字幕内容" not in text:
        raise ValueError("summary request did not include the fixture transcript")
    if schema_name == "VideoAnswerPayload" and "generated transcript and summary" not in text:
        raise ValueError("video Talk did not reach the answer synthesis stage")
    if schema_name == "SeriesAnswerPayload" and "generated transcript and summary" not in text:
        raise ValueError("series Talk did not reach the answer synthesis stage")


def _payload_for_schema(name: str | None) -> dict[str, object] | None:
    # Names come from the Pydantic schemas passed through the real LiteLLM gateway.
    payloads: dict[str, dict[str, object]] = {
        "SummaryPayload": {
            "title": "CI E2E 视频",
            "one_sentence_summary": "固定字幕说明 CI 端到端测试覆盖核心工作流。",
            "core_problem": "验证从导入到产物和对话的完整业务链路。",
            "chapters": [{"id": "chapter-1", "title": "固定测试内容", "start_seconds": 0, "end_seconds": 6, "summary": "视频包含固定的 CI 测试字幕。", "key_points": ["导入", "生成", "引用"]}],
            "key_takeaways": ["Mock 只替代出站 LLM Provider"],
        },
        "AiSummaryPayload": {
            "markdown": "# CI AI 概括\n\n固定字幕验证了完整工作流。[1]",
            "visual_evidence": [],
            "citations": [{"citation_id": 1, "source_type": "transcript", "timestamp_seconds": 0}],
        },
        "KnowledgeCardCollectionPayload": {
            "cards": [{"id": "ci-card-1", "title": "CI E2E", "kind": "concept", "summary": "固定字幕驱动的端到端测试。", "details": "验证真实项目链路与 Mock Provider 的契约。", "tags": ["ci"], "keywords": ["e2e", "mock"]}],
        },
        "FlatMindmapPayload": {
            "nodes": [
                {"id": "root", "parent_id": None, "title": "CI E2E", "summary": "根节点", "start_seconds": 0, "end_seconds": 6},
                {"id": "workflow", "parent_id": "root", "title": "完整链路", "summary": "导入到对话", "start_seconds": 0, "end_seconds": 6},
            ]
        },
        "VideoActionPlannerPayload": {"tool_calls": [], "action_summary": "CI 测试不需要额外工具调用。"},
        "VideoAnswerPayload": {"answer": "当前视频的固定字幕确认了 CI 端到端工作流。"},
        "SeriesQueryUnderstanding": {"normalized_query": "CI 端到端测试", "subqueries": [], "filters": {}},
        "SeriesAnswerPayload": {"answer": "当前系列的固定测试视频确认了完整工作流。", "citations": [], "used_source_types": ["transcript"]},
    }
    if name is None:
        return None
    if name not in payloads:
        raise ValueError(f"unsupported structured schema: {name}")
    return payloads[name]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8899)
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
