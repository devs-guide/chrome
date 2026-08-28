#!/usr/bin/env python3
"""Write deterministic publication metadata and checksums."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--source-date-epoch", required=True, type=int)
    parser.add_argument("--release", required=True)
    parser.add_argument("--catalog-version", required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    meta = root / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    build_time = datetime.fromtimestamp(args.source_date_epoch, timezone.utc).isoformat().replace("+00:00", "Z")
    publication = {
        "schemaVersion": 1,
        "repository": args.repository,
        "sourceRef": args.source_ref,
        "sourceSha": args.source_sha,
        "buildTime": build_time,
        "release": args.release,
        "catalogVersion": args.catalog_version,
        "artifactVersion": "1",
    }
    (meta / "publication.json").write_text(
        json.dumps(publication, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    checksum_path = meta / "checksums.sha256"
    files = sorted(
        path for path in root.rglob("*")
        if path.is_file() and path != checksum_path
    )
    checksum_path.write_text(
        "".join(f"{sha256(path)}  {path.relative_to(root).as_posix()}\n" for path in files),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
