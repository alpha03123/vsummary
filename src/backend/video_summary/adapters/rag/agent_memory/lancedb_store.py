from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path

import lancedb

from backend.common.filesystem import atomic_write_text

INDEX_SCHEMA_VERSION = 5
INDEX_TABLE_NAME = f"agent_graph_evidence_v{INDEX_SCHEMA_VERSION}"
LANCEDB_OPTIMIZE_CLEANUP_OLDER_THAN = timedelta(minutes=10)
SeriesSignature = tuple[str, ...]
SeriesSignatureMap = dict[str, SeriesSignature]


def reset_lancedb_table(db_uri: str, table_name: str) -> None:
    connection = lancedb.connect(db_uri)
    try:
        connection.drop_table(table_name)
    except Exception:
        pass


def delete_rows(*, db_uri: str, table_name: str, where: str) -> None:
    connection = lancedb.connect(db_uri)
    table = connection.open_table(table_name)
    table.delete(where)


def optimize_lancedb_table(db_uri: str, table_name: str) -> None:
    connection = lancedb.connect(db_uri)
    table = connection.open_table(table_name)
    table.optimize(cleanup_older_than=LANCEDB_OPTIMIZE_CLEANUP_OLDER_THAN)


def table_exists(db_uri: str, table_name: str) -> bool:
    connection = lancedb.connect(db_uri)
    try:
        table_names = set(connection.table_names())
    except Exception:
        return False
    return table_name in table_names


def escape_lance_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def write_signature_file(
    db_uri: str,
    table_name: str,
    signature: SeriesSignatureMap,
) -> None:
    signature_path = _signature_file_path(db_uri, table_name)
    signature_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        signature_path,
        json.dumps(
            {
                "index_schema_version": INDEX_SCHEMA_VERSION,
                "series_signatures": {
                    series_id: list(series_signature)
                    for series_id, series_signature in sorted(signature.items())
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
    )


def read_signature_file(
    db_uri: str,
    table_name: str,
) -> SeriesSignatureMap | None:
    signature_path = _signature_file_path(db_uri, table_name)
    if not signature_path.exists():
        return None
    try:
        payload = json.loads(signature_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    raw_series_signatures = payload.get("series_signatures")
    if isinstance(raw_series_signatures, dict):
        signatures: SeriesSignatureMap = {}
        for series_id, raw_signature in raw_series_signatures.items():
            if not isinstance(raw_signature, list):
                return None
            signatures[str(series_id)] = tuple(str(item) for item in raw_signature)
        return signatures
    raw_signature = payload.get("signature")
    if (
        not isinstance(raw_signature, list)
        or len(raw_signature) != 2
        or not isinstance(raw_signature[0], list)
        or not isinstance(raw_signature[1], list)
    ):
        return None
    return _series_signatures_from_legacy_workspace_signature(
        tuple(str(item) for item in raw_signature[0]),
        tuple(str(item) for item in raw_signature[1]),
    )


def _signature_file_path(db_uri: str, table_name: str) -> Path:
    return Path(db_uri) / f"{table_name}.signature.json"


def _series_signatures_from_legacy_workspace_signature(
    series_ids: tuple[str, ...],
    video_parts: tuple[str, ...],
) -> SeriesSignatureMap:
    signatures: SeriesSignatureMap = {series_id: () for series_id in series_ids}
    grouped_parts: dict[str, list[str]] = {series_id: [] for series_id in series_ids}
    for part in video_parts:
        series_id = part.split(":", 1)[0]
        grouped_parts.setdefault(series_id, []).append(part)
    for series_id, parts in grouped_parts.items():
        signatures[series_id] = tuple(sorted(parts))
    return signatures
