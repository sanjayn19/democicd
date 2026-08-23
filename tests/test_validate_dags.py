import tempfile
import unittest
from pathlib import Path

from scripts.validate_dags import validate


class ValidateDagsTests(unittest.TestCase):
    def test_sample_dags_are_structurally_valid(self) -> None:
        self.assertEqual(validate(Path("dags")), [])

    def test_duplicate_dag_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = "from x import DAG\ndag = DAG(dag_id='duplicate')\n"
            (root / "one.py").write_text(content, encoding="utf-8")
            (root / "two.py").write_text(content, encoding="utf-8")
            errors = validate(root)
            self.assertTrue(any("duplicate dag_id" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
