"""Verify that every ready database media reference can be read from one Local runtime."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.core.blob_store import BlobReference, BlobStoreError
from backend.local.persistence.file_blob_store import FileBlobStore
from backend.local.persistence.local_credentials import load_local_mysql_password


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify media Blob integrity for a running VSummary Local runtime.")
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()

    root = args.data_root.expanduser().resolve()
    runtime = json.loads((root / "mysql" / "runtime.json").read_text(encoding="utf-8"))
    port = runtime.get("port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Runtime metadata has an invalid MySQL port.")
    password = load_local_mysql_password(root / "mysql" / "vsummary_app.dpapi")
    engine = create_engine(f"mysql+pymysql://vsummary_app:{password}@127.0.0.1:{port}/vsummary", future=True)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT m.video_id,m.blob_key,m.sha256,m.byte_size,m.media_type "
                    "FROM media_objects m "
                    "JOIN videos v ON v.id=m.video_id "
                    "JOIN series s ON s.id=v.series_id "
                    "WHERE m.state='ready' AND v.deleted_at IS NULL AND s.deleted_at IS NULL "
                    "ORDER BY m.video_id"
                )
            ).mappings().all()
    finally:
        engine.dispose()

    blobs = FileBlobStore(root / "blobs")
    failures: list[dict[str, str]] = []
    for row in rows:
        reference = BlobReference(row["blob_key"], row["sha256"], row["byte_size"], row["media_type"])
        try:
            actual = blobs.stat(reference)
        except BlobStoreError as error:
            failures.append({"video_id": row["video_id"], "blob_key": row["blob_key"], "error": str(error)})
            continue
        if actual.sha256 != reference.sha256 or actual.byte_size != reference.byte_size:
            failures.append({"video_id": row["video_id"], "blob_key": row["blob_key"], "error": "metadata mismatch"})

    print(json.dumps({"data_root": str(root), "checked": len(rows), "failures": failures}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
