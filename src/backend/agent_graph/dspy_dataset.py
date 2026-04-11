from __future__ import annotations

from pathlib import Path

import dspy


BOUNDARY_EXCLUDED_IDS = {"seed-030", "var-099"}
DEFAULT_TRAIN_IDS = {
    "seed-001",
    "seed-002",
    "seed-006",
    "seed-007",
    "seed-011",
    "seed-012",
    "seed-015",
    "seed-016",
    "seed-017",
    "seed-018",
    "seed-019",
    "seed-020",
    "seed-021",
    "seed-022",
    "seed-023",
    "seed-025",
    "seed-026",
    "seed-027",
    "seed-028",
    "seed-029",
}
DEFAULT_DEV_IDS = {
    "seed-003",
    "seed-004",
    "seed-005",
    "seed-008",
    "seed-009",
    "seed-010",
    "seed-013",
    "seed-014",
    "seed-024",
}


def load_classifier_records(plan_dir: Path) -> list[dict[str, object]]:
    seed_path = plan_dir / "2026-04-10-dspy-classifier-seeds.md"
    variant_path = plan_dir / "2026-04-10-dspy-classifier-variants.md"
    records = _parse_markdown_table(seed_path, prefix="seed-")
    records.extend(_parse_markdown_table(variant_path, prefix="var-"))
    return records


def build_classifier_trainset(plan_dir: Path) -> list[dspy.Example]:
    records = [
        record
        for record in load_classifier_records(plan_dir)
        if record["id"] in DEFAULT_TRAIN_IDS and record["id"] not in BOUNDARY_EXCLUDED_IDS
    ]
    return [_to_example(record) for record in records]


def build_classifier_devset(plan_dir: Path) -> list[dspy.Example]:
    records = [
        record
        for record in load_classifier_records(plan_dir)
        if record["id"] in DEFAULT_DEV_IDS and record["id"] not in BOUNDARY_EXCLUDED_IDS
    ]
    return [_to_example(record) for record in records]


def slice_examples(examples: list[dspy.Example], limit: int | None) -> list[dspy.Example]:
    if limit is None or limit <= 0:
        return examples
    return examples[:limit]


def _to_example(record: dict[str, object]) -> dspy.Example:
    example = dspy.Example(
        id=record["id"],
        user_message=record["user_message"],
        scope_type=record["scope_type"],
        series_id="agent-frameworks",
        video_id="1-4 准备工作：百度地图API秘钥(AK)" if record["scope_type"] == "video" else "",
        goal=record["goal"],
        target_source=record["target_source"],
        context_need=record["context_need"],
        action_name=record["action_name"],
        action_args={},
    )
    return example.with_inputs("user_message", "scope_type", "series_id", "video_id")


def _parse_markdown_table(path: Path, *, prefix: str) -> list[dict[str, object]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    records: list[dict[str, object]] = []
    for line in lines:
        if not line.startswith(f"| {prefix}"):
            continue
        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if prefix == "seed-":
            record_id, _source, scope, user_message, goal, target_source, context_need, action_name = parts
        else:
            record_id, scope, user_message, goal, target_source, context_need, action_name = parts
        records.append(
            {
                "id": _clean_markdown_cell(record_id),
                "scope_type": _clean_markdown_cell(scope),
                "user_message": _clean_markdown_cell(user_message),
                "goal": _clean_markdown_cell(goal),
                "target_source": _clean_markdown_cell(target_source),
                "context_need": _clean_markdown_cell(context_need),
                "action_name": _clean_markdown_cell(action_name),
            }
        )
    return records


def _clean_markdown_cell(value: str) -> str:
    return value.strip().strip("`").strip()
