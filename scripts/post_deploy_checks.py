#!/usr/bin/env python3
"""Run deterministic checks against the example deployed DAG directory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_python_files(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*.py"))


def check_deployment(
    environment: str,
    expected_sha: str,
    source: Path,
    deployed_root: Path,
) -> list[str]:
    errors: list[str] = []
    environment_root = deployed_root / environment
    deployed_dags = environment_root / "dags"
    release_path = environment_root / "release.json"
    if not release_path.is_file():
        return [f"missing deployment release file: {release_path}"]
    if not deployed_dags.is_dir():
        return [f"missing deployed DAG directory: {deployed_dags}"]

    release = json.loads(release_path.read_text(encoding="utf-8"))
    if release.get("environment") != environment:
        errors.append(
            f"release environment {release.get('environment')!r} does not match {environment!r}"
        )
    if release.get("git_sha") != expected_sha:
        errors.append(
            f"release SHA {release.get('git_sha')!r} does not match {expected_sha!r}"
        )

    source_files = relative_python_files(source)
    deployed_files = relative_python_files(deployed_dags)
    if release.get("dag_files") != source_files:
        errors.append("release DAG list does not match the source DAG list")
    if deployed_files != source_files:
        errors.append("deployed DAG list does not match the source DAG list")
    for relative_path in sorted(set(source_files) & set(deployed_files)):
        if digest(source / relative_path) != digest(deployed_dags / relative_path):
            errors.append(f"deployed content differs from source: {relative_path}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--source", default="dags")
    parser.add_argument("--deployed-root", default="build/deployed")
    args = parser.parse_args()
    errors = check_deployment(
        args.environment,
        args.expected_sha,
        Path(args.source),
        Path(args.deployed_root),
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"post-deployment checks passed for {args.environment} at {args.expected_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
