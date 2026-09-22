"""Real isolated Git tests for release metadata without blobs or network access."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("prepare_sdk_git", Path(__file__).resolve().parents[1] / "prepare-sdk-git.py")
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


class ReleaseFixture:
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.remote = self.base / "upstream"
        self.remote.mkdir()
        self.sdk = self.base / "sdk"
        self.version = "1.2.3"
        # Identity is per process; only temporary fixture repositories are configured.
        environment = patch.dict(os.environ, {
            "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.git(self.remote, "init", "-q", "--initial-branch=stable")
        self.git(self.remote, "config", "--local", "uploadpack.allowFilter", "true")
        (self.remote / "runtime.txt").write_text("required SDK worktree content\n")
        (self.remote / "fixture.txt").write_text("synthetic removed source fixture; no key\n")
        self.git(self.remote, "add", ".")
        self.git(self.remote, "commit", "-q", "-m", "Synthetic release")
        self.revision = self.git(self.remote, "rev-parse", "HEAD").strip()
        self.git(self.remote, "tag", "-a", self.version, "-m", "Synthetic release tag")
        subprocess.run(["git", "clone", "--quiet", str(self.remote), str(self.sdk)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.index = self.git(self.sdk, "ls-files", "--stage", "-z")
        self.fixture_oid = self.git(self.sdk, "rev-parse", "HEAD:fixture.txt").strip()
        self.orphan = subprocess.check_output(["git", "-C", str(self.sdk), "hash-object", "-w", "--stdin"],
                                             input="unreachable synthetic fixture", text=True).strip()
        (self.sdk / "fixture.txt").unlink()  # Model worktree sanitation before metadata preparation.
        self.selection = self.base / "resolved.json"
        self.selection.write_text(json.dumps({"flutter": {"hash": self.revision, "version": self.version}}))
        self.origin = self.remote.as_uri()
        for patcher in (
            patch.object(prepare, "ROOT", self.sdk), patch.object(prepare, "ORIGIN", self.origin),
            patch.object(prepare, "Path", side_effect=lambda value: self.selection
                         if str(value) == "/usr/local/share/flutter-runtime/resolved.json" else Path(value)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def git(self, root, *args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True, stderr=subprocess.PIPE)

    def prepared(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            prepare.prepare()


class GitPreparationTests(ReleaseFixture, unittest.TestCase):
    def test_exact_tag_branch_remote_and_index_without_local_blobs(self):
        self.prepared()
        self.assertEqual(self.git(self.sdk, "rev-parse", "HEAD").strip(), self.revision)
        self.assertEqual(self.git(self.sdk, "rev-parse", f"refs/tags/{self.version}^{{commit}}").strip(), self.revision)
        self.assertEqual(self.git(self.sdk, "symbolic-ref", "HEAD").strip(), "refs/heads/stable")
        self.assertEqual(self.git(self.sdk, "describe", "--tags", "--exact-match", "HEAD").strip(), self.version)
        self.assertEqual(self.git(self.sdk, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}").strip(), "origin/stable")
        self.assertEqual(self.git(self.sdk, "config", "--local", "--get", "remote.origin.fetch").strip(),
                         "+refs/heads/stable:refs/remotes/origin/stable")
        self.assertEqual(self.git(self.sdk, "rev-parse", "refs/remotes/origin/stable").strip(), self.revision)
        self.assertEqual(self.git(self.sdk, "remote", "get-url", "origin").strip(), self.origin)
        self.assertEqual(self.git(self.sdk, "rev-parse", "--is-shallow-repository").strip(), "true")
        self.assertEqual(self.git(self.sdk, "ls-files", "--stage", "-z"), self.index)
        objects = self.git(self.sdk, "cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype)")
        self.assertNotIn(" blob", objects)
        self.assertNotIn(self.orphan, objects)
        self.assertFalse((self.sdk / "fixture.txt").exists())
        self.assertEqual((self.sdk / "runtime.txt").read_text(), "required SDK worktree content\n")

    def test_local_and_https_promisor_retrieval_blocked_without_global_policy_changes(self):
        self.prepared()
        for key in ("protocol.allow", "protocol.https.allow"):
            self.assertEqual(self.git(self.sdk, "config", "--local", "--get", key).strip(), "never")
        for origin, protocol in ((self.origin, "file"), ("https://example.invalid/fixture.git", "https")):
            self.git(self.sdk, "remote", "set-url", "origin", origin)
            result = subprocess.run(["git", "-C", str(self.sdk), "cat-file", "-e", self.fixture_oid], text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(f"transport '{protocol}' not allowed", result.stderr)
        consumer = self.base / "consumer"
        consumer.mkdir()
        self.git(consumer, "init", "-q")
        self.git(consumer, "fetch", "--depth=1", self.origin, f"refs/tags/{self.version}")
        self.assertNotIn("blob", self.git(self.sdk, "cat-file", "--batch-all-objects", "--batch-check=%(objecttype)").splitlines())

    def test_release_commit_mismatch_fails(self):
        self.selection.write_text(json.dumps({"flutter": {"hash": "0" * 40, "version": self.version}}))
        with self.assertRaisesRegex(ValueError, "does not identify the resolved revision"):
            self.prepared()

    def test_server_ignoring_filter_is_rejected(self):
        self.git(self.remote, "config", "--local", "uploadpack.allowFilter", "false")
        with self.assertRaisesRegex(ValueError, "retains Git blobs"):
            self.prepared()

    def test_missing_release_tag_fails_instead_of_using_other_revision(self):
        self.selection.write_text(json.dumps({"flutter": {"hash": self.revision, "version": "9.9.9"}}))
        with self.assertRaises(subprocess.CalledProcessError):
            self.prepared()


if __name__ == "__main__":
    unittest.main()
