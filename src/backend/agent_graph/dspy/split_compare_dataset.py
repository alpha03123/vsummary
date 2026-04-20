from __future__ import annotations

import json
from pathlib import Path

import dspy


def load_split_compare_records(plan_dir: Path) -> list[dict[str, object]]:
    seed_path = plan_dir / "2026-04-11-dspy-split-compare-seeds.md"
    variant_path = plan_dir / "2026-04-11-dspy-split-compare-variants.md"
    records = _parse_markdown_table(seed_path, prefix="cseed-")
    records.extend(_parse_markdown_table(variant_path, prefix="cvar-"))
    return records


def build_split_compare_trainset(plan_dir: Path) -> list[dspy.Example]:
    records = [record for record in load_split_compare_records(plan_dir) if record["id"].startswith("cvar-")]
    return [_to_example(record) for record in records]


def build_split_compare_devset(plan_dir: Path) -> list[dspy.Example]:
    records = [record for record in load_split_compare_records(plan_dir) if record["id"].startswith("cseed-")]
    return [_to_example(record) for record in records]


def _to_example(record: dict[str, object]) -> dspy.Example:
    example = dspy.Example(
        id=record["id"],
        user_message=record["user_message"],
        queries=record["queries"],
        reason="",
    )
    return example.with_inputs("user_message")


def _parse_markdown_table(path: Path, *, prefix: str) -> list[dict[str, object]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    records: list[dict[str, object]] = []
    for line in lines:
        if not line.startswith(f"| {prefix}"):
            continue
        record_id, user_message, queries_json = [part.strip() for part in line.strip().strip("|").split("|")]
        records.append(
            {
                "id": record_id.strip("`"),
                "user_message": user_message.strip("`"),
                "queries": json.loads(queries_json.strip("`")),
            }
        )
    return records
