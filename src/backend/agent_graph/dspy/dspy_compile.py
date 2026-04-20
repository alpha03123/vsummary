from __future__ import annotations

import dspy

from backend.agent_graph.dspy.programs import ClassifySeriesQuery, normalize_classifier_prediction


class SeriesQueryClassifierModule(dspy.Module):
    def __init__(self) -> None:
        super().__init__()
        self.predict = dspy.Predict(ClassifySeriesQuery)

    def forward(
        self,
        user_message: str,
        scope_type: str,
        series_id: str,
        video_id: str = "",
        history_summary: str = "",
        history_selected_videos: list[dict[str, object]] | None = None,
    ):
        return self.predict(
            user_message=user_message,
            scope_type=scope_type,
            series_id=series_id,
            video_id=video_id,
            history_summary=history_summary,
            history_selected_videos=history_selected_videos or [],
        )

    def run(
        self,
        *,
        user_message: str,
        scope_type: str,
        series_id: str,
        video_id: str = "",
        history_summary: str = "",
        history_selected_videos: list[dict[str, object]] | None = None,
    ):
        raw = self.forward(
            user_message=user_message,
            scope_type=scope_type,
            series_id=series_id,
            video_id=video_id,
            history_summary=history_summary,
            history_selected_videos=history_selected_videos,
        )
        return normalize_classifier_prediction(raw)


class ClassifierMetric:
    def __call__(self, example, prediction, trace=None) -> float:
        del trace
        weights = {
            "goal": 0.45,
            "target_source": 0.20,
            "context_need": 0.10,
            "action_name": 0.20,
            "action_args": 0.05,
        }
        score = 0.0
        for key, weight in weights.items():
            if _lookup(example, key) == _lookup(prediction, key):
                score += weight
        return round(score, 4)


def compile_classifier_program(*, trainset, optimizer=None):
    resolved_optimizer = optimizer or dspy.BootstrapFewShot(
        metric=ClassifierMetric(),
        max_bootstrapped_demos=4,
        max_labeled_demos=8,
        max_rounds=1,
        max_errors=5,
    )
    student = SeriesQueryClassifierModule()
    return resolved_optimizer.compile(student, trainset=trainset)


def evaluate_classifier_program(*, program, devset, evaluate_factory=None, num_threads: int | None = None):
    resolved_evaluate = evaluate_factory or dspy.Evaluate
    evaluator = resolved_evaluate(
        devset=devset,
        metric=ClassifierMetric(),
        num_threads=num_threads,
        display_progress=False,
        display_table=False,
    )
    return evaluator(program)


def _lookup(source, key: str):
    if isinstance(source, dict):
        return source.get(key)
    if hasattr(source, "get"):
        try:
            return source.get(key)
        except Exception:
            pass
    return getattr(source, key, None)
