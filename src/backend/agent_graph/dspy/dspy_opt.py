from __future__ import annotations

import dspy


class DspyCompiler:
    def __init__(self, optimizer=None) -> None:
        self._optimizer = optimizer or dspy.BootstrapFewShot()

    def compile_program(self, *, student, trainset, valset=None):
        return self._optimizer.compile(
            student=student,
            trainset=trainset,
            valset=valset,
        )


class DspyEvaluator:
    def __init__(self, evaluate_factory=None) -> None:
        self._evaluate_factory = evaluate_factory or dspy.Evaluate

    def evaluate_program(self, *, program, devset, metric, num_threads: int | None = None):
        evaluator = self._evaluate_factory(
            devset=devset,
            metric=metric,
            num_threads=num_threads,
            display_progress=False,
            display_table=False,
        )
        return evaluator(program)
