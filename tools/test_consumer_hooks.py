"""Native generated regressions for the consumer's two guard forwarders."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from make_fixtures import review10_hook

ROOT = Path(__file__).resolve().parents[1]


class ConsumerHookTests(unittest.TestCase):
    def check_hook(self, hook, kind):
        with tempfile.TemporaryDirectory(prefix="qq-hook-fixture-") as directory:
            fixture = review10_hook(directory, hook, (ROOT / ".githooks" / hook).read_bytes(), kind)
            result = subprocess.run(["sh", str(fixture["path"]), *fixture["args"]],
                                    cwd=directory, input=fixture["stdin"],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, fixture["expected_exit"], result.stdout + result.stderr)
            if kind in ("valid", "failure"):
                self.assertEqual(result.stdout, fixture["expected_stdout"])
                self.assertEqual(result.stderr, "")
            else:
                self.assertIn("BLOCKED", result.stdout + result.stderr)
                self.assertNotIn("synthetic-guard-ran", result.stdout + result.stderr)

    def test_pre_commit_missing(self):
        self.check_hook("pre-commit", "missing")

    def test_pre_commit_empty(self):
        self.check_hook("pre-commit", "empty")

    def test_pre_commit_directory(self):
        self.check_hook("pre-commit", "directory")

    def test_pre_commit_valid(self):
        self.check_hook("pre-commit", "valid")

    def test_pre_commit_failure(self):
        self.check_hook("pre-commit", "failure")

    def test_pre_push_missing(self):
        self.check_hook("pre-push", "missing")

    def test_pre_push_empty(self):
        self.check_hook("pre-push", "empty")

    def test_pre_push_directory(self):
        self.check_hook("pre-push", "directory")

    def test_pre_push_valid(self):
        self.check_hook("pre-push", "valid")

    def test_pre_push_failure(self):
        self.check_hook("pre-push", "failure")


if __name__ == "__main__":
    unittest.main()
