#!/usr/bin/env python3
"""Perform dependency-free structural validation of Airflow DAG Python files."""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path


def dag_ids_from_tree(tree: ast.AST) -> list[str]:
    dag_ids: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg != "dag_id":
                continue
            if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                dag_ids.append(keyword.value.value)
    return dag_ids


def validate(directory: Path) -> list[str]:
    errors: list[str] = []
    seen: dict[str, Path] = {}
    files = sorted(path for path in directory.rglob("*.py") if not path.name.startswith("_"))
    if not files:
        return [f"No DAG Python files found under {directory}"]

    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            errors.append(f"{path}: syntax error: {exc}")
            continue
        ids = dag_ids_from_tree(tree)
        if not ids:
            errors.append(f"{path}: no literal dag_id was found")
        for dag_id in ids:
            if dag_id in seen:
                errors.append(f"{path}: duplicate dag_id {dag_id!r}; first seen in {seen[dag_id]}")
            else:
                seen[dag_id] = path
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?", default="dags")
    args = parser.parse_args()
    errors = validate(Path(args.directory))
    if errors:
        print("DAG validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"DAG validation passed for {args.directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

