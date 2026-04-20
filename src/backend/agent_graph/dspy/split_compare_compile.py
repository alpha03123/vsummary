from __future__ import annotations

import dspy

from backend.agent_graph.dspy.programs import SplitCompareQuery, normalize_split_compare_prediction


class SplitCompareModule(dspy.Module):
    def __init__(self) -> None:
        super().__init__()
        self.predict = dspy.ChainOfThought(SplitCompareQuery)

    def forward(self, user_message: str):
        return self.predict(user_message=user_message)

    def run(self, *, user_message: str):
        raw = self.forward(user_message=user_message)
        return normalize_split_compare_prediction(raw)


class SplitCompareMetric:
    def __call__(self, example, prediction, trace=None) -> float:
        del trace
        expected = _lookup(example, "queries") or []
        actual = _lookup(prediction, "queries") or []
        if not expected or not actual:
            return 0.0
        expected_norm = [str(item).strip() for item in expected]
        actual_norm = [str(item).strip() for item in actual]
        if expected_norm == actual_norm:
            return 1.0
        overlap = len(set(expected_norm) & set(actual_norm))
        return round(overlap / max(len(expected_norm), len(actual_norm)), 4)


def compile_split_compare_program(*, trainset, optimizer=None):
    resolved_optimizer = optimizer or dspy.BootstrapFewShot(
        metric=SplitCompareMetric(),
        max_bootstrapped_demos=6,
        max_labeled_demos=2,
        max_rounds=1,
        max_errors=5,
    )
    student = SplitCompareModule()
    return resolved_optimizer.compile(student, trainset=trainset)


def _lookup(source, key: str):
    if isinstance(source, dict):
        return source.get(key)
    if hasattr(source, "get"):
        try:
            return source.get(key)
        except Exception:
            pass
    return getattr(source, key, None)
