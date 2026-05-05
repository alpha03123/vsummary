from __future__ import annotations

from collections.abc import Callable
from typing import Any

import dspy

from backend.agent_graph.prompts import VIDEO_ANSWER_SYNTHESIZER_SYSTEM_PROMPT


class SynthesizeVideoAnswer(dspy.Signature):
    __doc__ = VIDEO_ANSWER_SYNTHESIZER_SYSTEM_PROMPT

    user_message: str = dspy.InputField()
    retrieval_results: list[dict[str, object]] = dspy.InputField()
    meta_state: dict[str, object] = dspy.InputField()
    answer: str = dspy.OutputField()


class AnswerSynthesisProgram:
    def __init__(self, predictor: Callable[..., Any] | None = None) -> None:
        self._predictor = predictor or dspy.ChainOfThought(SynthesizeVideoAnswer)

    def run(
        self,
        *,
        user_message: str,
        retrieval_results: list[dict[str, object]],
        meta_state: dict[str, object] | None = None,
    ) -> str:
        raw = self._predictor(
            user_message=user_message,
            retrieval_results=retrieval_results,
            meta_state=meta_state or {},
        )
        payload = _coerce_prediction(raw)
        answer = payload.get("answer", "")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("DSPy answer synthesis 缺少 answer。")
        return answer.strip()


def _coerce_prediction(value: Any) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "items"):
        return dict(value.items())
    if hasattr(value, "__dict__"):
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    raise TypeError("无法将 DSPy 输出转换为结构化字典。")
