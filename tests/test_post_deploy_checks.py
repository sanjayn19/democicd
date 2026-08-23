import json
import tempfile
import unittest
from pathlib import Path

from scripts.post_deploy_checks import check_deployment


class PostDeploymentCheckTests(unittest.TestCase):
    def create_release(self, root: Path, *, deployed_content: str = "dag") -> tuple[Path, Path]:
        source = root / "dags"
        deployed_root = root / "build" / "deployed"
        deployed_dags = deployed_root / "ptest" / "dags"
        source.mkdir(parents=True)
        deployed_dags.mkdir(parents=True)
        (source / "sample.py").write_text("dag", encoding="utf-8")
        (deployed_dags / "sample.py").write_text(deployed_content, encoding="utf-8")
        release = {
            "environment": "ptest",
            "git_sha": "abc123",
            "dag_files": ["sample.py"],
        }
        (deployed_dags.parent / "release.json").write_text(
            json.dumps(release), encoding="utf-8"
        )
        return source, deployed_root

    def test_matching_deployment_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, deployed_root = self.create_release(Path(directory))
            self.assertEqual(
                check_deployment("ptest", "abc123", source, deployed_root), []
            )

    def test_content_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, deployed_root = self.create_release(
                Path(directory), deployed_content="different"
            )
            errors = check_deployment("ptest", "abc123", source, deployed_root)
            self.assertTrue(any("content differs" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
