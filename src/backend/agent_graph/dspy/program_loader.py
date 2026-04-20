from __future__ import annotations

import json
from pathlib import Path

from backend.agent_graph.dspy.decompose_compile import TaskDecomposerModule
from backend.agent_graph.dspy.dspy_compile import SeriesQueryClassifierModule
from backend.agent_graph.dspy.split_compare_compile import SplitCompareModule


def load_or_create_classifier_program(
    *,
    artifact_path: Path,
    program_factory=None,
):
    program = (program_factory or SeriesQueryClassifierModule)()
    if artifact_path.exists():
        _load_program_state(program, artifact_path)
    return program


def load_or_create_decompose_program(
    *,
    artifact_path: Path,
    program_factory=None,
):
    program = (program_factory or TaskDecomposerModule)()
    if artifact_path.exists():
        _load_program_state(program, artifact_path)
    return program


def load_or_create_split_compare_program(
    *,
    artifact_path: Path,
    program_factory=None,
):
    program = (program_factory or SplitCompareModule)()
    if artifact_path.exists():
        _load_program_state(program, artifact_path)
    return program


def _load_program_state(program, artifact_path: Path) -> None:
    state = json.loads(artifact_path.read_text(encoding="utf-8"))
    program.load_state(state)
