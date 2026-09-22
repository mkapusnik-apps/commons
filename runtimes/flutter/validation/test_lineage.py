"""Verify reuse decisions against real, isolated Git histories, without Docker."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import validate


class ProductionLineageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.environment = dict(os.environ, GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                                GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")
        self.git("init", "-q", "--initial-branch=main")
        self.write("runtimes/flutter/Dockerfile", "FROM scratch\n")
        self.write("runtimes/flutter/install.sh", "true\n")
        self.write("runtimes/flutter/validation/worker.py", "# Original validation\n")
        self.write(".github/workflows/flutter-runtimes.yml", "name: Fixture\n")
        self.source = self.commit("Original fixture")
        patcher = patch.object(validate, "REPOSITORY", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, env=self.environment,
                                       text=True, stderr=subprocess.STDOUT).strip()

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def commit(self, message):
        self.git("add", ".")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def test_same_checkpoint_and_validator_only_descendant_have_same_production_identity(self):
        original = validate.check_production_lineage(self.source, self.source)
        self.write("runtimes/flutter/validation/worker.py", "# Corrected classification\n")
        self.write("runtimes/flutter/validation/test_new.py", "# Extra validation coverage\n")
        revision = self.commit("Validation only")
        descendant = validate.check_production_lineage(self.source, revision)
        self.assertEqual(original["production_tree_sha256"], descendant["production_tree_sha256"])
        self.assertEqual(original["production_git_entries"], descendant["production_git_entries"])
        self.assertEqual(descendant["image_source_revision"], self.source)
        self.assertEqual(descendant["validation_revision"], revision)
        self.assertTrue(descendant["ancestor_verified"])

    def test_production_content_change_rejected(self):
        self.write("runtimes/flutter/install.sh", "false\n")
        with self.assertRaisesRegex(ValueError, "different runtime production trees"):
            validate.check_production_lineage(self.source, self.commit("Changed installer"))

    def test_added_production_file_rejected(self):
        self.write("runtimes/flutter/new-helper.py", "# New production input\n")
        with self.assertRaisesRegex(ValueError, "different runtime production trees"):
            validate.check_production_lineage(self.source, self.commit("Added helper"))

    def test_deleted_production_file_rejected(self):
        (self.root / "runtimes/flutter/install.sh").unlink()
        with self.assertRaisesRegex(ValueError, "different runtime production trees"):
            validate.check_production_lineage(self.source, self.commit("Deleted installer"))

    def test_production_mode_change_rejected(self):
        (self.root / "runtimes/flutter/install.sh").chmod(0o755)
        with self.assertRaisesRegex(ValueError, "different runtime production trees"):
            validate.check_production_lineage(self.source, self.commit("Executable installer"))

    def test_publication_workflow_change_rejected(self):
        self.write(".github/workflows/flutter-runtimes.yml", "name: Changed workflow\n")
        with self.assertRaisesRegex(ValueError, "different runtime production trees"):
            validate.check_production_lineage(self.source, self.commit("Changed workflow"))

    def test_matching_production_on_nonancestor_is_rejected(self):
        self.write("runtimes/flutter/validation/worker.py", "# Branch A\n")
        branch_a = self.commit("Validation branch A")
        self.git("switch", "-q", "-c", "branch-b", self.source)
        self.write("runtimes/flutter/validation/worker.py", "# Branch B\n")
        branch_b = self.commit("Validation branch B")
        with self.assertRaises(subprocess.CalledProcessError):
            validate.check_production_lineage(branch_a, branch_b)

    def test_invalid_missing_and_option_like_source_rejected(self):
        for source in (None, "main", "--all", self.source[:7]):
            with self.subTest(source=source), self.assertRaises(ValueError):
                validate.check_production_lineage(source, self.source)
        with self.assertRaises(subprocess.CalledProcessError):
            validate.check_production_lineage("0" * 40, self.source)


if __name__ == "__main__":
    unittest.main()
