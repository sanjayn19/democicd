#!/usr/bin/env python3
"""Local deployment adapter used by the example workflow.

Replace this adapter with a Composer, MWAA, Astronomer, or Airflow-specific
deployment command. The example intentionally avoids cloud credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, text=True, capture_output=True
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", required=True)
    parser.add_argument("--source", default="dags")
    parser.add_argument("--target", default="build/deployed")
    parser.add_argument("--git-sha")
    args = parser.parse_args()
    source = Path(args.source)
    destination = Path(args.target) / args.environment / "dags"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    release = {
        "environment": args.environment,
        "git_sha": args.git_sha or os.getenv("GITHUB_SHA") or git_sha(),
        "deployed_at": datetime.now(UTC).isoformat(),
        "dag_files": sorted(
            path.relative_to(destination).as_posix() for path in destination.rglob("*.py")
        ),
    }
    release_path = destination.parent / "release.json"
    release_path.write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
    print(release_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
