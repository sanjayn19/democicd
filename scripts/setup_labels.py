#!/usr/bin/env python3
"""Create or update the labels used by the promotion workflow."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request

LABELS = {
    "promote:ptest": ("1D76DB", "Request inclusion in the next PTEST batch"),
    "promoted:ptest": ("0E8A16", "Deployed to PTEST and post-deployment checks passed"),
    "hold:ptest": ("FBCA04", "Temporarily hold PTEST promotion"),
    "reject:ptest": ("D93F0B", "Block PTEST promotion"),
    "promotion:ptest": ("5319E7", "Automation-generated PTEST promotion PR"),
    "rollback:ptest": ("B60205", "Automation-generated PTEST rollback PR"),
    "rolledback:ptest": ("D93F0B", "PTEST rollback deployed and checks passed"),
    "promote:prod": ("B60205", "Request inclusion in the next PROD batch"),
    "promoted:prod": ("006B75", "Deployed to PROD and post-deployment checks passed"),
    "hold:prod": ("FBCA04", "Temporarily hold PROD promotion"),
    "reject:prod": ("D93F0B", "Block PROD promotion"),
    "promotion:prod": ("5319E7", "Automation-generated PROD promotion PR"),
    "rollback:prod": ("B60205", "Automation-generated PROD rollback PR"),
    "rolledback:prod": ("D93F0B", "PROD rollback deployed and checks passed"),
}


def request(url: str, token: str, method: str, body: dict[str, str]) -> None:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as response:
        response.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    base = f"https://api.github.com/repos/{args.repository}/labels"
    for name, (color, description) in LABELS.items():
        encoded = urllib.parse.quote(name, safe="")
        try:
            request(
                f"{base}/{encoded}",
                args.token,
                "PATCH",
                {"color": color, "description": description},
            )
            print(f"updated {name}")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            request(
                base,
                args.token,
                "POST",
                {"name": name, "color": color, "description": description},
            )
            print(f"created {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
