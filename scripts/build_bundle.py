#!/usr/bin/env python3
"""Create an immutable DAG deployment bundle and content manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path


def git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", required=True)
    parser.add_argument("--source", default="dags")
    parser.add_argument("--output", default="build")
    parser.add_argument("--git-sha")
    args = parser.parse_args()

    source = Path(args.source)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    commit = args.git_sha or os.getenv("GITHUB_SHA") or git_sha()
    files = sorted(path for path in source.rglob("*") if path.is_file())
    manifest = {
        "environment": args.environment,
        "git_sha": commit,
        "created_at": datetime.now(UTC).isoformat(),
        "files": [
            {"path": path.as_posix(), "sha256": sha256(path), "size": path.stat().st_size}
            for path in files
        ],
    }
    manifest_path = output / f"dags-{args.environment}-{commit[:12]}.manifest.json"
    bundle_path = output / f"dags-{args.environment}-{commit[:12]}.zip"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.as_posix())
        archive.write(manifest_path, manifest_path.name)
    print(bundle_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
