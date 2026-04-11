from __future__ import annotations

import json
from pathlib import Path

import dspy


PRIORITY_DECOMPOSE_TRAIN_IDS = [
    "dseed-010",  # 隐式动作：记重点 -> 总结 + 保存
    "dseed-011",  # 复杂依赖：总结 -> 保存 -> 打开
    "dseed-003",  # meta_state：状态查询
    "dseed-015",  # compare：比较关系
    "dseed-021",  # 4 步复杂依赖
    "dseed-022",  # compare -> understand -> action
    "dseed-023",  # 状态 -> 动作决策
    "dseed-024",  # understand -> locate -> understand -> compare
]


def load_decompose_records(plan_dir: Path) -> list[dict[str, object]]:
    seed_path = plan_dir / "2026-04-11-dspy-decompose-seeds.md"
    variant_path = plan_dir / "2026-04-11-dspy-decompose-variants.md"
    records = _parse_markdown_table(seed_path, prefix="dseed-")
    records.extend(_parse_markdown_table(variant_path, prefix="dvar-"))
    return records


def build_decompose_trainset(plan_dir: Path) -> list[dspy.Example]:
    all_records = load_decompose_records(plan_dir)
    record_by_id = {record["id"]: record for record in all_records}
    ordered_records: list[dict[str, object]] = []
    seen: set[str] = set()

    for record_id in PRIORITY_DECOMPOSE_TRAIN_IDS:
        record = record_by_id.get(record_id)
        if record is None:
            continue
        ordered_records.append(record)
        seen.add(record_id)

    for record in all_records:
        if record["id"] in seen:
            continue
        ordered_records.append(record)

    records = ordered_records
    return [_to_example(record) for record in records]


def build_decompose_devset(plan_dir: Path) -> list[dspy.Example]:
    records = [record for record in load_decompose_records(plan_dir) if record["id"].startswith("dseed-")]
    return [_to_example(record) for record in records]


def _to_example(record: dict[str, object]) -> dspy.Example:
    example = dspy.Example(
        id=record["id"],
        user_message=record["user_message"],
        scope_type=record["scope_type"],
        series_id="agent-frameworks",
        video_id="1-4 准备工作：百度地图API秘钥(AK)" if record["scope_type"] == "video" else "",
        tasks=record["tasks"],
        reason="",
    )
    return example.with_inputs("user_message", "scope_type", "series_id", "video_id")


def _parse_markdown_table(path: Path, *, prefix: str) -> list[dict[str, object]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    records: list[dict[str, object]] = []
    for line in lines:
        if not line.startswith(f"| {prefix}"):
            continue
        record_id, scope, user_message, tasks_json = [part.strip() for part in line.strip().strip("|").split("|")]
        records.append(
            {
                "id": record_id.strip("`"),
                "scope_type": scope.strip("`"),
                "user_message": user_message.strip("`"),
                "tasks": json.loads(tasks_json.strip("`")),
            }
        )
    return records
