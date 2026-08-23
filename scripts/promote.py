#!/usr/bin/env python3
"""Create a selective PTEST or PROD promotion PR from labeled source PRs.

The source repository must use squash merging into main. The script applies each
selected source PR's single squash commit to a temporary branch based on the
target environment. It fails closed on ambiguity, mismatched files, conflicts,
or patch-ID changes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def command(
    args: list[str], *, input_text: str | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
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
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            self.base + path,
            data=data,
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
            detail = exc.read().decode()
            raise RuntimeError(f"GitHub API {method} {path} failed: {exc.code} {detail}") from exc

    def pages(self, path: str) -> list[Any]:
        items: list[Any] = []
        separator = "&" if "?" in path else "?"
        for page in range(1, 11):
            batch = self.call("GET", f"{path}{separator}per_page=100&page={page}")
            items.extend(batch)
            if len(batch) < 100:
                return items
        raise RuntimeError("Pagination exceeded 1,000 items; narrow or archive old promotion labels")


@dataclass(frozen=True)
class Candidate:
    number: int
    title: str
    source_sha: str
    merged_at: str
    url: str
    files: tuple[str, ...]


@dataclass
class Promotion:
    pr_number: int
    title: str
    source_sha: str
    promotion_sha: str
    merged_at: str
    files: list[str]
    source_url: str


def labels(item: dict[str, Any]) -> set[str]:
    return {entry["name"] for entry in item.get("labels", [])}


def load_policy(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def pr_files(github: GitHub, number: int) -> tuple[str, ...]:
    files = github.pages(f"/pulls/{number}/files?")
    return tuple(sorted(item["filename"] for item in files))


def collect_candidates(
    github: GitHub, environment: str, policy: dict[str, Any], max_batch: int
) -> tuple[list[Candidate], list[dict[str, Any]]]:
    rules = policy["labels"][environment]
    query = urllib.parse.urlencode({"state": "closed", "labels": rules["request"]})
    issues = github.pages(f"/issues?{query}")
    candidates: list[Candidate] = []
    skipped: list[dict[str, Any]] = []
    for issue in issues:
        if "pull_request" not in issue:
            continue
        number = int(issue["number"])
        item_labels = labels(issue)
        reason = None
        if rules["promoted"] in item_labels:
            reason = "already promoted"
        elif rules["hold"] in item_labels:
            reason = f"blocked by {rules['hold']}"
        elif rules["reject"] in item_labels:
            reason = f"blocked by {rules['reject']}"
        elif environment == "prod" and policy["prod_requires_label"] not in item_labels:
            reason = f"missing {policy['prod_requires_label']}"
        if reason:
            skipped.append({"pr_number": number, "reason": reason})
            continue

        pr = github.call("GET", f"/pulls/{number}")
        if not pr.get("merged_at"):
            skipped.append({"pr_number": number, "reason": "PR is closed but not merged"})
            continue
        if pr["base"]["ref"] != policy["source_branch"]:
            skipped.append(
                {
                    "pr_number": number,
                    "reason": f"base is {pr['base']['ref']}, not {policy['source_branch']}",
                }
            )
            continue
        source_sha = pr.get("merge_commit_sha")
        if not source_sha:
            raise RuntimeError(f"PR #{number} has no merge_commit_sha")
        candidates.append(
            Candidate(
                number=number,
                title=pr["title"],
                source_sha=source_sha,
                merged_at=pr["merged_at"],
                url=pr["html_url"],
                files=pr_files(github, number),
            )
        )

    candidates.sort(key=lambda item: (item.merged_at, item.number))
    if len(candidates) > max_batch:
        skipped.extend(
            {"pr_number": item.number, "reason": f"deferred by max batch size {max_batch}"}
            for item in candidates[max_batch:]
        )
        candidates = candidates[:max_batch]
    return candidates, skipped


def ensure_no_open_promotion(github: GitHub, environment: str, promotion_label: str) -> None:
    pulls = github.pages(f"/pulls?state=open&base={urllib.parse.quote(environment)}&")
    for pull in pulls:
        if promotion_label in labels(pull):
            raise RuntimeError(
                f"Open {environment} promotion PR already exists: #{pull['number']} {pull['html_url']}"
            )


def commit_files(sha: str) -> tuple[str, ...]:
    result = command(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", sha])
    return tuple(sorted(line for line in result.stdout.splitlines() if line))


def patch_id(sha: str) -> str:
    patch = command(["git", "show", "--pretty=format:", "--binary", sha]).stdout
    result = command(["git", "patch-id", "--stable"], input_text=patch)
    parts = result.stdout.split()
    if not parts:
        raise RuntimeError(f"Could not calculate patch ID for {sha}")
    return parts[0]


def verify_source(candidate: Candidate, source_branch: str) -> None:
    ancestry = command(
        ["git", "merge-base", "--is-ancestor", candidate.source_sha, f"origin/{source_branch}"],
        check=False,
    )
    if ancestry.returncode:
        raise RuntimeError(f"PR #{candidate.number} source SHA is not on {source_branch}")
    parents = command(["git", "rev-list", "--parents", "-n", "1", candidate.source_sha]).stdout.split()
    if len(parents) != 2:
        raise RuntimeError(
            f"PR #{candidate.number} source SHA has {len(parents) - 1} parents; "
            "selective promotion requires one squash commit"
        )
    actual_files = commit_files(candidate.source_sha)
    if actual_files != candidate.files:
        raise RuntimeError(
            f"PR #{candidate.number} source file set does not match its squash commit. "
            f"PR files={candidate.files}; commit files={actual_files}. "
            "Confirm that Squash and merge is the only enabled merge method."
        )


def read_record(branch: str, environment: str, number: int) -> dict[str, Any] | None:
    path = f".promotion/records/{environment}/pr-{number}.json"
    result = command(["git", "show", f"origin/{branch}:{path}"], check=False)
    if result.returncode:
        return None
    return json.loads(result.stdout)


def create_promotion(
    github: GitHub,
    repository: str,
    environment: str,
    run_id: str,
    policy: dict[str, Any],
    candidates: list[Candidate],
    skipped: list[dict[str, Any]],
) -> str:
    source_branch = policy["source_branch"]
    target_branch = policy["environment_branches"][environment]
    branch = f"promotion/{environment}/run-{run_id}"
    command(["git", "config", "user.name", "promotion-bot"])
    command(["git", "config", "user.email", "promotion-bot@users.noreply.github.com"])
    command(["git", "fetch", "origin", "--prune", source_branch, target_branch, "ptest"])
    command(["git", "switch", "--force-create", branch, f"origin/{target_branch}"])

    promotions: list[Promotion] = []
    try:
        for candidate in candidates:
            existing = read_record(target_branch, environment, candidate.number)
            if existing:
                raise RuntimeError(
                    f"PR #{candidate.number} already has a {environment} record but its labels are stale"
                )
            verify_source(candidate, source_branch)
            if environment == "prod":
                ptest_record = read_record("ptest", "ptest", candidate.number)
                if not ptest_record:
                    raise RuntimeError(f"PR #{candidate.number} has no PTEST promotion record")
                if ptest_record["source_sha"] != candidate.source_sha:
                    raise RuntimeError(
                        f"PR #{candidate.number} PTEST record refers to a different source SHA"
                    )

            result = command(["git", "cherry-pick", "-x", candidate.source_sha], check=False)
            if result.returncode:
                command(["git", "cherry-pick", "--abort"], check=False)
                raise RuntimeError(
                    f"PR #{candidate.number} conflicts with {target_branch}. "
                    "The batch was aborted; resolve through a new source PR, not in automation.\n"
                    f"{result.stderr}"
                )
            promotion_sha = command(["git", "rev-parse", "HEAD"]).stdout.strip()
            if patch_id(candidate.source_sha) != patch_id(promotion_sha):
                raise RuntimeError(f"PR #{candidate.number} patch ID changed during promotion")
            promotions.append(
                Promotion(
                    pr_number=candidate.number,
                    title=candidate.title,
                    source_sha=candidate.source_sha,
                    promotion_sha=promotion_sha,
                    merged_at=candidate.merged_at,
                    files=list(candidate.files),
                    source_url=candidate.url,
                )
            )

        created_at = datetime.now(UTC).isoformat()
        manifest_path = Path(f".promotion/runs/{environment}-{run_id}.json")
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = {
            "operation": "promotion",
            "environment": environment,
            "target_branch": target_branch,
            "source_branch": source_branch,
            "run_id": run_id,
            "created_at": created_at,
            "promotions": [asdict(item) for item in promotions],
            "skipped": skipped,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        for item in promotions:
            record_path = Path(f".promotion/records/{environment}/pr-{item.pr_number}.json")
            record_path.parent.mkdir(parents=True, exist_ok=True)
            record = asdict(item) | {"environment": environment, "run_id": run_id, "created_at": created_at}
            record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        command(["git", "add", ".promotion"])
        command(["git", "commit", "-m", f"Record {environment} promotion run {run_id}"])
        command(["git", "push", "--set-upstream", "origin", branch])
    except Exception:
        command(["git", "switch", "--detach", f"origin/{target_branch}"], check=False)
        raise

    title = f"Promote {len(promotions)} selected PR(s) to {environment.upper()}"
    lines = [
        f"Automated selective promotion into `{target_branch}`.",
        "",
        "| Source PR | Source SHA | Promotion SHA |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| #{item.pr_number} — {item.title} | `{item.source_sha[:12]}` | `{item.promotion_sha[:12]}` |"
        for item in promotions
    )
    lines.extend(
        [
            "",
            f"Promotion-Manifest: `{manifest_path.as_posix()}`",
            "",
            "Conflict resolution is intentionally disabled. If this PR conflicts or fails CI, fix the source through a new PR into `main` and rerun promotion.",
        ]
    )
    owner = repository.split("/", 1)[0]
    pull = github.call(
        "POST",
        "/pulls",
        {
            "title": title,
            "head": f"{owner}:{branch}",
            "base": target_branch,
            "body": "\n".join(lines),
            "maintainer_can_modify": False,
        },
    )
    github.call(
        "POST",
        f"/issues/{pull['number']}/labels",
        {"labels": [policy["labels"][environment]["promotion_pr"]]},
    )
    return pull["html_url"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=["ptest", "prod"], required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--run-id", default=os.getenv("GITHUB_RUN_ID", "local"))
    parser.add_argument("--policy", default="config/promotion-policy.json")
    parser.add_argument("--max-prs", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--plan-output", default="build/promotion-plan.json")
    args = parser.parse_args()

    policy = load_policy(Path(args.policy))
    maximum = args.max_prs or int(policy["default_max_batch_size"])
    if maximum < 1 or maximum > 100:
        raise ValueError("--max-prs must be between 1 and 100")
    github = GitHub(args.repository, args.token)
    if policy["abort_if_open_promotion_pr_exists"]:
        ensure_no_open_promotion(
            github,
            policy["environment_branches"][args.environment],
            policy["labels"][args.environment]["promotion_pr"],
        )
    candidates, skipped = collect_candidates(github, args.environment, policy, maximum)
    plan = {
        "environment": args.environment,
        "candidates": [asdict(item) for item in candidates],
        "skipped": skipped,
    }
    output = Path(args.plan_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan, indent=2))
    if not candidates:
        print(f"No eligible PRs found for {args.environment}")
        return 0
    if args.dry_run:
        print("Dry run complete; no branch or PR was created")
        return 0
    url = create_promotion(
        github,
        args.repository,
        args.environment,
        str(args.run_id),
        policy,
        candidates,
        skipped,
    )
    print(f"Created promotion PR: {url}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"promotion failed: {exc}", file=sys.stderr)
        raise
