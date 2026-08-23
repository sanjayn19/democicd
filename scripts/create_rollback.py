#!/usr/bin/env python3
"""Create a PR that reverts one recorded environment promotion commit."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def command(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if check and result.returncode:
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{result.stdout}\n{result.stderr}")
    return result


class GitHub:
    def __init__(self, repository: str, token: str) -> None:
        self.base = f"https://api.github.com/repos/{repository}"
        self.token = token

    def call(self, method: str, path: str, body: dict[str, Any]) -> Any:
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(body).encode(),
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"GitHub API failed: {exc.read().decode()}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=["ptest", "prod"], required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--run-id", default=os.getenv("GITHUB_RUN_ID", "local"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    command(["git", "config", "user.name", "promotion-bot"])
    command(["git", "config", "user.email", "promotion-bot@users.noreply.github.com"])
    command(["git", "fetch", "origin", "--prune", args.environment])
    record_path = Path(f".promotion/records/{args.environment}/pr-{args.pr_number}.json")
    raw = command(["git", "show", f"origin/{args.environment}:{record_path.as_posix()}"]).stdout
    record = json.loads(raw)
    promotion_sha = record["promotion_sha"]
    branch = f"rollback/{args.environment}/pr-{args.pr_number}-run-{args.run_id}"
    print(json.dumps({"environment": args.environment, "record": record, "branch": branch}, indent=2))
    if args.dry_run:
        return 0

    command(["git", "switch", "--force-create", branch, f"origin/{args.environment}"])
    revert = command(["git", "revert", "--no-edit", promotion_sha], check=False)
    if revert.returncode:
        command(["git", "revert", "--abort"], check=False)
        raise RuntimeError(
            "Rollback conflicts with later environment changes. Use a reviewed forward fix or a manually prepared rollback PR.\n"
            + revert.stderr
        )
    revert_sha = command(["git", "rev-parse", "HEAD"]).stdout.strip()
    manifest_path = Path(f".promotion/runs/rollback-{args.environment}-{args.run_id}.json")
    manifest = {
        "operation": "rollback",
        "environment": args.environment,
        "run_id": str(args.run_id),
        "created_at": datetime.now(UTC).isoformat(),
        "source_pr_number": args.pr_number,
        "source_sha": record["source_sha"],
        "promotion_sha": promotion_sha,
        "revert_sha": revert_sha,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    command(["git", "add", manifest_path.as_posix()])
    command(["git", "commit", "-m", f"Record {args.environment} rollback for PR #{args.pr_number}"])
    command(["git", "push", "--set-upstream", "origin", branch])

    owner = args.repository.split("/", 1)[0]
    body = (
        f"Rollback source PR #{args.pr_number} from `{args.environment}`.\n\n"
        f"Reverts promotion commit `{promotion_sha}`.\n\n"
        f"Rollback-Manifest: `{manifest_path.as_posix()}`\n\n"
        "Automation does not resolve rollback conflicts. Validate downstream DAG dependencies and already-running DAG runs before merging."
    )
    github = GitHub(args.repository, args.token)
    pull = github.call(
        "POST",
        "/pulls",
        {
            "title": f"Rollback PR #{args.pr_number} from {args.environment.upper()}",
            "head": f"{owner}:{branch}",
            "base": args.environment,
            "body": body,
            "maintainer_can_modify": False,
        },
    )
    github.call(
        "POST",
        f"/issues/{pull['number']}/labels",
        {"labels": [f"rollback:{args.environment}"]},
    )
    print(pull["html_url"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

