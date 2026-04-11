from __future__ import annotations

import dspy

from backend.agent_graph.programs import DecomposeUserTask, normalize_decompose_prediction


class TaskDecomposerModule(dspy.Module):
    def __init__(self) -> None:
        super().__init__()
        self.predict = dspy.ChainOfThought(DecomposeUserTask)

    def forward(self, user_message: str, scope_type: str, series_id: str, video_id: str = ""):
        return self.predict(
            user_message=user_message,
            scope_type=scope_type,
            series_id=series_id,
            video_id=video_id,
        )

    def run(self, *, user_message: str, scope_type: str, series_id: str, video_id: str = ""):
        raw = self.forward(
            user_message=user_message,
            scope_type=scope_type,
            series_id=series_id,
            video_id=video_id,
        )
        return normalize_decompose_prediction(raw)


class DecomposeMetric:
    def __call__(self, example, prediction, trace=None) -> float:
        del trace
        expected = _lookup(example, "tasks") or []
        actual = _lookup(prediction, "tasks") or []
        if not expected or not actual:
            return 0.0
        score = 0.0

        if len(expected) == len(actual):
            score += 0.45

        pair_count = min(len(expected), len(actual))
        if pair_count == 0:
            return 0.0

        per_task = 0.55 / pair_count
        for expected_task, actual_task in zip(expected, actual):
            if not isinstance(expected_task, dict) or not isinstance(actual_task, dict):
                continue
            task_score = 0.0
            if expected_task.get("kind_hint") == actual_task.get("kind_hint"):
                task_score += 0.5
            if expected_task.get("depends_on") == actual_task.get("depends_on"):
                task_score += 0.25
            expected_instruction = str(expected_task.get("instruction", "")).strip()
            actual_instruction = str(actual_task.get("instruction", "")).strip()
            if expected_instruction and actual_instruction:
                if expected_instruction == actual_instruction:
                    task_score += 0.25
                elif _semantic_overlap(expected_instruction, actual_instruction):
                    task_score += 0.2
            score += per_task * task_score

        return round(min(score, 1.0), 4)


def compile_decompose_program(*, trainset, optimizer=None):
    resolved_optimizer = optimizer or dspy.BootstrapFewShot(
        metric=DecomposeMetric(),
        max_bootstrapped_demos=8,
        max_labeled_demos=2,
        max_rounds=1,
        max_errors=5,
    )
    student = TaskDecomposerModule()
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


def _semantic_overlap(expected_instruction: str, actual_instruction: str) -> bool:
    expected_tokens = {token for token in expected_instruction.replace("，", " ").replace("。", " ").split() if token}
    actual_tokens = {token for token in actual_instruction.replace("，", " ").replace("。", " ").split() if token}
    if expected_tokens and actual_tokens and expected_tokens & actual_tokens:
        return True
    keywords = ["概括", "总结", "定位", "读取", "查询", "打开", "生成", "保存", "比较", "解释", "跳到"]
    return any(word in expected_instruction and word in actual_instruction for word in keywords)
