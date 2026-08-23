import json
import unittest
from pathlib import Path
from typing import Any

from scripts.finalize_deployment import (
    finalize_promotion,
    finalize_rollback,
    safe_manifest_path,
)
from scripts.promote import labels, load_policy


class FakeGitHub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def call(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        self.calls.append((method, path, body))
        return None

    def pages(self, path: str) -> list[Any]:
        self.calls.append(("PAGES", path, None))
        return []


class PromotionPolicyTests(unittest.TestCase):
    def test_prod_requires_ptest_evidence(self) -> None:
        policy = load_policy(Path("config/promotion-policy.json"))
        self.assertEqual(policy["prod_requires_label"], "promoted:ptest")
        self.assertEqual(policy["environment_branches"]["prod"], "prod")

    def test_all_operational_labels_are_unique(self) -> None:
        policy = json.loads(Path("config/promotion-policy.json").read_text(encoding="utf-8"))
        values = [value for env in policy["labels"].values() for value in env.values()]
        self.assertEqual(len(values), len(set(values)))

    def test_label_extraction(self) -> None:
        item = {"labels": [{"name": "promote:ptest"}, {"name": "team:data"}]}
        self.assertEqual(labels(item), {"promote:ptest", "team:data"})

    def test_manifest_path_is_limited_to_promotion_runs(self) -> None:
        path = ".promotion/runs/ptest-123.json"
        self.assertEqual(safe_manifest_path(path), Path(path))
        for unsafe in ["/tmp/run.json", "../run.json", ".promotion/records/run.json"]:
            with self.subTest(path=unsafe), self.assertRaises(ValueError):
                safe_manifest_path(unsafe)

    def test_promotion_labels_change_only_in_deployment_finalizer(self) -> None:
        github = FakeGitHub()
        path = Path(".promotion/runs/ptest-123.json")
        manifest = {
            "promotions": [
                {
                    "pr_number": 42,
                    "source_sha": "source",
                    "promotion_sha": "promotion",
                }
            ]
        }
        finalize_promotion(github, "ptest", path, manifest, "deployed")
        self.assertIn(
            ("POST", "/issues/42/labels", {"labels": ["promoted:ptest"]}),
            github.calls,
        )
        self.assertTrue(
            any(
                method == "DELETE" and "promote%3Aptest" in api_path
                for method, api_path, _ in github.calls
            )
        )

    def test_rollback_labels_change_only_in_deployment_finalizer(self) -> None:
        github = FakeGitHub()
        path = Path(".promotion/runs/rollback-prod-123.json")
        manifest = {"source_pr_number": 42, "revert_sha": "revert"}
        finalize_rollback(github, "prod", path, manifest, "deployed")
        self.assertIn(
            (
                "POST",
                "/issues/42/labels",
                {"labels": ["rolledback:prod", "reject:prod"]},
            ),
            github.calls,
        )
        self.assertTrue(
            any(
                method == "DELETE" and "promoted%3Aprod" in api_path
                for method, api_path, _ in github.calls
            )
        )


if __name__ == "__main__":
    unittest.main()
