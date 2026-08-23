#!/usr/bin/env python3
"""Finalize source-PR labels only after a successful environment deployment.

The deployment workflow calls this script after validation, deployment, smoke
checks, and evidence upload. It discovers immutable promotion or rollback
manifests added by the environment-branch push and updates source PR state.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ZERO_SHA = "0" * 40
RUNS_DIRECTORY = Path(".promotion/runs")


def command(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if check and result.returncode:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(args)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


class GitHub:
    def __init__(self, repository: str, token: str) -> None:
        self.base = f"https://api.github.com/repos/{repository}"
        self.token = token

    def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        request = urllib.request.Request(
            self.base + path,
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            if method == "DELETE" and exc.code == 404:
                return None
            detail = exc.read().decode()
            raise RuntimeError(
                f"GitHub API {method} {path} failed: {exc.code} {detail}"
            ) from exc

    def pages(self, path: str) -> list[Any]:
        items: list[Any] = []
        separator = "&" if "?" in path else "?"
        for page in range(1, 11):
            batch = self.call("GET", f"{path}{separator}per_page=100&page={page}")
            items.extend(batch)
            if len(batch) < 100:
                return items
        raise RuntimeError("Pagination exceeded 1,000 items")


def safe_manifest_path(value: str | Path) -> Path:
    path = Path(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or path.parent != RUNS_DIRECTORY
        or path.suffix != ".json"
    ):
        raise ValueError(f"Unsafe deployment manifest path: {path}")
    return path


def discover_manifest_paths(before_sha: str, after_sha: str) -> list[Path]:
    """Return manifests added by this push; existing manifests are immutable."""
    if before_sha == ZERO_SHA:
        result = command(
            [
                "git",
                "diff-tree",
                "--root",
                "--no-commit-id",
                "--name-only",
                "--diff-filter=A",
                "-r",
                after_sha,
                "--",
                RUNS_DIRECTORY.as_posix(),
            ]
        )
    else:
        ancestry = command(
            ["git", "merge-base", "--is-ancestor", before_sha, after_sha], check=False
        )
        if ancestry.returncode:
            raise ValueError("Deployment push is not a fast-forward; refusing label updates")
        result = command(
            [
                "git",
                "diff",
                "--name-only",
                "--diff-filter=A",
                before_sha,
                after_sha,
                "--",
                RUNS_DIRECTORY.as_posix(),
            ]
        )
    return sorted(safe_manifest_path(line) for line in result.stdout.splitlines() if line)


def load_manifest(path: Path, environment: str, after_sha: str) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("environment") != environment:
        raise ValueError(f"Manifest {path} does not target {environment}")

    operation = manifest.get("operation", "promotion")
    if operation == "promotion":
        promotions = manifest.get("promotions")
        if not isinstance(promotions, list) or not promotions:
            raise ValueError(f"Promotion manifest {path} has no promotions")
        commit_shas = [str(item["promotion_sha"]) for item in promotions]
    elif operation == "rollback":
        if "source_pr_number" not in manifest or "revert_sha" not in manifest:
            raise ValueError(f"Rollback manifest {path} is incomplete")
        commit_shas = [str(manifest["revert_sha"])]
    else:
        raise ValueError(f"Unsupported operation {operation!r} in {path}")

    for sha in commit_shas:
        ancestry = command(
            ["git", "merge-base", "--is-ancestor", sha, after_sha], check=False
        )
        if ancestry.returncode:
            raise ValueError(f"Manifest commit {sha} is not present in deployed SHA {after_sha}")
    return manifest


def remove_label(github: GitHub, number: int, label: str) -> None:
    encoded = urllib.parse.quote(label, safe="")
    github.call("DELETE", f"/issues/{number}/labels/{encoded}")


def add_labels(github: GitHub, number: int, labels: list[str]) -> None:
    github.call("POST", f"/issues/{number}/labels", {"labels": labels})


def comment_once(github: GitHub, number: int, marker: str, body: str) -> None:
    comments = github.pages(f"/issues/{number}/comments")
    if any(marker in str(comment.get("body", "")) for comment in comments):
        return
    github.call("POST", f"/issues/{number}/comments", {"body": f"{body}\n\n{marker}"})


def finalize_promotion(
    github: GitHub,
    environment: str,
    path: Path,
    manifest: dict[str, Any],
    deployed_sha: str,
) -> None:
    for item in manifest["promotions"]:
        number = int(item["pr_number"])
        remove_label(github, number, f"promote:{environment}")
        remove_label(github, number, f"rolledback:{environment}")
        add_labels(github, number, [f"promoted:{environment}"])
        marker = f"<!-- deployment-finalizer:{environment}:{path.as_posix()} -->"
        comment_once(
            github,
            number,
            marker,
            (
                f"Successfully deployed to **{environment}** and passed post-deployment "
                f"checks using `{path}`. Deployed branch SHA: `{deployed_sha}`; source SHA: "
                f"`{item['source_sha']}`; promotion SHA: `{item['promotion_sha']}`."
            ),
        )
        print(f"finalized successful {environment} deployment for source PR #{number}")


def finalize_rollback(
    github: GitHub,
    environment: str,
    path: Path,
    manifest: dict[str, Any],
    deployed_sha: str,
) -> None:
    number = int(manifest["source_pr_number"])
    remove_label(github, number, f"promote:{environment}")
    remove_label(github, number, f"promoted:{environment}")
    add_labels(
        github,
        number,
        [f"rolledback:{environment}", f"reject:{environment}"],
    )
    marker = f"<!-- deployment-finalizer:rollback:{environment}:{path.as_posix()} -->"
    comment_once(
        github,
        number,
        marker,
        (
            f"Rollback from **{environment}** was deployed successfully and passed "
            f"post-deployment checks using `{path}`. Deployed branch SHA: `{deployed_sha}`; "
            f"revert SHA: `{manifest['revert_sha']}`. A corrective source PR is required "
            "before re-promotion."
        ),
    )
    print(f"finalized successful {environment} rollback for source PR #{number}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=["ptest", "prod"], required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--before-sha", required=True)
    parser.add_argument("--after-sha", required=True)
    args = parser.parse_args()

    paths = discover_manifest_paths(args.before_sha, args.after_sha)
    if not paths:
        print("No new promotion or rollback manifests in this deployment; no labels to update")
        return 0

    manifests = [
        (path, load_manifest(path, args.environment, args.after_sha)) for path in paths
    ]
    github = GitHub(args.repository, args.token)
    for path, manifest in manifests:
        if manifest.get("operation", "promotion") == "rollback":
            finalize_rollback(github, args.environment, path, manifest, args.after_sha)
        else:
            finalize_promotion(github, args.environment, path, manifest, args.after_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
