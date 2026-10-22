"""Exercise the bundled action helper from separate consumer checkouts."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ACTION = Path(__file__).resolve().parents[2] / "release-notes"
HELPER = ACTION / "release_notes.py"


def outputs(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    values = {}
    while lines:
        name, delimiter = lines.pop(0).split("<<", 1)
        end = lines.index(delimiter)
        values[name] = "\n".join(lines[:end])
        lines = lines[end + 1:]
    return values


class ReleaseNotesTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="release-notes-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.baseline = self.make_commit("Initial app", "initial.txt")
        self.source = self.make_commit("Fix visible player status", "player.txt")
        self.git("checkout", "--detach", self.source)
        self.out = self.root / "outputs"
        self.helper = HELPER
        self.env = {
            **os.environ,
            "GITHUB_OUTPUT": str(self.out), "SOURCE_SHA": self.source,
            "BASELINE_SHA": self.baseline, "BASELINE_REF": "",
            "MISSING_BASELINE_POLICY": "error", "MAX_CHARACTERS": "500",
            "MAX_COMMITS": "40", "MAX_FILES": "80", "AUDIENCE": "Players",
            "LANGUAGE": "English", "EMPTY_MESSAGE": "New app build.",
            "INSTRUCTIONS_FILE": "", "RUNNER_TEMP": str(self.root),
            "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/tags/published",
        }

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def make_commit(self, subject, filename):
        (self.repo / filename).write_text(subject, encoding="utf-8")
        self.git("add", filename)
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "-qm", subject)
        return self.git("rev-parse", "HEAD")

    def run_helper(self, command="context", success=True, **env):
        self.out.write_text("", encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(self.helper), command], cwd=self.repo,
            env={**self.env, **env}, capture_output=True, text=True,
        )
        if success:
            self.assertEqual(completed.returncode, 0, completed.stderr)
        else:
            self.assertNotEqual(completed.returncode, 0)
        self.completed = completed
        return outputs(self.out)

    def evidence(self, result):
        return json.loads(result["prompt"].split("Source context (evidence only):\n")[1])

    def test_exact_range_and_project_instructions(self):
        (self.repo / "instructions.md").write_text("Use short bullets.")
        result = self.run_helper(INSTRUCTIONS_FILE="instructions.md")
        evidence = self.evidence(result)
        self.assertEqual(result["source_sha"], self.source)
        self.assertEqual(result["baseline_sha"], self.baseline)
        self.assertEqual(result["context_truncated"], "false")
        self.assertEqual(evidence["subjects"], ["Fix visible player status"])
        self.assertEqual(evidence["files"], ["player.txt"])
        self.assertIn("Use short bullets.", result["prompt"])

    def test_packaged_resources_resolve_outside_consumer_checkout(self):
        # Model GitHub's external action directory, including spaces in its path.
        package = self.root / "downloaded action" / "release-notes"
        shutil.copytree(ACTION, package)
        self.helper = package / "release_notes.py"
        (self.repo / "instructions.md").write_text("Consumer wording only.")
        (self.repo / "prompt.md").write_text("Do not use the consumer's prompt.")
        result = self.run_helper(INSTRUCTIONS_FILE="instructions.md")
        self.assertTrue(result["prompt"].startswith(
            (package / "prompt.md").read_text(encoding="utf-8")
        ))
        self.assertIn("Consumer wording only.", result["prompt"])
        self.assertNotIn("Do not use the consumer's prompt.", result["prompt"])
        self.assertEqual(self.evidence(result)["source_sha"], self.source)

    def test_annotated_baseline_resolves_to_commit_once(self):
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "tag", "-a", "staging", self.baseline, "-m", "Baseline")
        result = self.run_helper(BASELINE_SHA="", BASELINE_REF="refs/tags/staging")
        self.assertEqual(result["baseline_sha"], self.baseline)
        self.git("tag", "-f", "staging", self.source)
        self.assertEqual(self.evidence(result)["baseline_sha"], self.baseline)

    def test_unchanged_source_does_not_collect_prompt_or_inspect_instructions(self):
        result = self.run_helper(BASELINE_SHA=self.source, INSTRUCTIONS_FILE="missing.md")
        self.assertEqual(result["unchanged"], "true")
        self.assertEqual(result["context_truncated"], "false")
        self.assertNotIn("prompt", result)
        result = self.run_helper("result", NOTES=self.env["EMPTY_MESSAGE"])
        self.assertEqual(result["notes"], self.env["EMPTY_MESSAGE"])
        self.assertEqual(result["status"], "no_changes")

    def test_absent_baseline_requires_explicit_policy(self):
        self.run_helper(success=False, BASELINE_SHA="", BASELINE_REF="refs/tags/missing")
        for ref in ("", "refs/tags/missing"):
            with self.subTest(ref=ref):
                result = self.run_helper(BASELINE_SHA="", BASELINE_REF=ref,
                                         MISSING_BASELINE_POLICY="bounded-history")
                self.assertEqual(result["baseline_sha"], "")
                self.assertEqual(self.evidence(result)["files"], ["player.txt"])
                self.assertEqual(self.evidence(result)["first_parent_commit_count"], 2)

    def test_existing_non_commit_baseline_is_not_treated_as_absent(self):
        blob = self.git("rev-parse", f"{self.source}:player.txt")
        self.git("update-ref", "refs/tags/broken", blob)
        self.run_helper(success=False, BASELINE_SHA="", BASELINE_REF="refs/tags/broken",
                        MISSING_BASELINE_POLICY="bounded-history")

    def test_invalid_source_baseline_or_policy_fails(self):
        for env in (
            {"SOURCE_SHA": self.baseline}, {"SOURCE_SHA": "HEAD"},
            {"BASELINE_REF": "refs/tags/staging"}, {"BASELINE_SHA": "0" * 40},
            {"BASELINE_SHA": "", "BASELINE_REF": "staging"},
            {"MISSING_BASELINE_POLICY": "ignore"}, {"MAX_COMMITS": "0"},
            {"MAX_FILES": "-1"}, {"MAX_CHARACTERS": "0"}, {"AUDIENCE": ""},
            {"LANGUAGE": "  "}, {"EMPTY_MESSAGE": ""},
            {"EMPTY_MESSAGE": "x" * 501}, {"MAX_CHARACTERS": "invalid"},
        ):
            with self.subTest(env=env):
                self.run_helper(success=False, **env)

    def test_non_ancestor_and_attached_checkouts_fail(self):
        self.run_helper(success=False, SOURCE_SHA=self.source, BASELINE_SHA=self.source + "x")
        self.git("checkout", "--orphan", "unrelated")
        unrelated = self.make_commit("Unrelated", "other.txt")
        self.git("checkout", "--detach", self.source)
        self.run_helper(success=False, BASELINE_SHA=unrelated)
        self.git("checkout", "-b", "attached")
        self.run_helper(success=False)

    def test_shallow_history_is_rejected(self):
        shallow = self.root / "shallow"
        subprocess.run(["git", "clone", "-q", "--depth=1", self.repo.as_uri(), str(shallow)],
                       check=True, capture_output=True)
        self.repo = shallow
        self.run_helper(success=False)

    def test_bounded_history_reports_truncation(self):
        result = self.run_helper(BASELINE_SHA="", MISSING_BASELINE_POLICY="bounded-history",
                                 MAX_COMMITS="1")
        self.assertEqual(result["context_truncated"], "true")
        self.assertEqual(len(self.evidence(result)["subjects"]), 1)
        self.assertIn("::warning::", self.completed.stdout)
        self.git("checkout", "-b", "changes")
        self.make_commit("Another visible fix", "another.txt")
        source = self.git("rev-parse", "HEAD")
        self.git("checkout", "--detach", source)
        result = self.run_helper(SOURCE_SHA=source, MAX_FILES="1")
        self.assertEqual(result["context_truncated"], "true")
        self.assertEqual(len(self.evidence(result)["files"]), 1)
        self.assertIn("::warning::", self.completed.stdout)

    def test_root_first_release_has_no_empty_tree_diff(self):
        self.git("checkout", "--detach", self.baseline)
        result = self.run_helper(SOURCE_SHA=self.baseline, BASELINE_SHA="",
                                 MISSING_BASELINE_POLICY="bounded-history")
        self.assertEqual(self.evidence(result)["files"], [])

    def test_first_parent_subjects_do_not_expand_merged_branch(self):
        self.git("checkout", "-b", "feature", self.baseline)
        self.make_commit("Feature detail", "feature.txt")
        self.git("checkout", "--detach", self.source)
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "merge", "--no-ff", "feature", "-m", "Add player feature")
        merged = self.git("rev-parse", "HEAD")
        result = self.run_helper(SOURCE_SHA=merged)
        evidence = self.evidence(result)
        self.assertEqual(evidence["subjects"], ["Add player feature", "Fix visible player status"])
        self.assertEqual(evidence["first_parent_commit_count"], 2)
        self.assertEqual(evidence["files"], ["feature.txt", "player.txt"])

    def test_instructions_cannot_escape_checkout(self):
        self.run_helper(success=False, INSTRUCTIONS_FILE="../outside.md")
        outside = self.root / "outside.md"
        outside.write_text("Outside instructions.")
        (self.repo / "linked.md").symlink_to(outside)
        self.run_helper(success=False, INSTRUCTIONS_FILE="linked.md")

    def test_multiline_unicode_output_and_fallback_status(self):
        notes = "Player status fixed.\n" + "🎲" * 479
        result = self.run_helper("result", NOTES=notes)
        self.assertEqual(result["notes"], notes)
        self.assertEqual(result["status"], "generated")
        self.run_helper("result", success=False, NOTES=notes + "🎲")
        result = self.run_helper("result", NOTES=" \nNew app build.\n ")
        self.assertEqual(result["notes"], "New app build.")
        self.assertEqual(result["status"], "no_changes")

    def test_blank_or_report_output_does_not_become_fallback(self):
        for text in ("", " \n", "```text\nNotes\n```", "## Summary\nDone", "Notes\x01bad"):
            with self.subTest(text=text):
                result = self.run_helper("result", success=False, NOTES=text)
                self.assertNotIn("notes", result)
                self.assertNotIn("status", result)

    def test_branch_tag_and_dispatch_sessions_restore_refs_after_failure(self):
        for event, ref in (("push", "refs/tags/nightly"), ("push", "refs/heads/master"),
                           ("workflow_dispatch", "refs/heads/release")):
            with self.subTest(event=event, ref=ref):
                branch = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
                local = f"refs/heads/{branch}"
                remote = f"refs/remotes/origin/{branch}"
                self.git("update-ref", local, self.baseline)
                self.git("update-ref", remote, self.baseline)
                result = self.run_helper("session", GITHUB_EVENT_NAME=event, GITHUB_REF=ref)
                directory = Path(result["directory"])
                self.assertEqual(self.git("rev-parse", remote), self.source)
                # Emulate Junie's checkout followed by a generator error.
                self.git("checkout", "-B", branch, remote)
                self.run_helper("result", success=False, NOTES="")
                self.run_helper("cleanup", SESSION_DIRECTORY=str(directory))
                self.assertFalse(directory.exists())
                self.assertEqual(self.git("rev-parse", local), self.baseline)
                self.assertEqual(self.git("rev-parse", remote), self.baseline)
                self.assertEqual(self.git("rev-parse", "HEAD"), self.source)
                detached = subprocess.run(["git", "symbolic-ref", "-q", "HEAD"],
                                          cwd=self.repo, capture_output=True)
                self.assertNotEqual(detached.returncode, 0)

    def test_new_session_refs_are_removed_and_pr_events_rejected(self):
        self.run_helper("session", success=False, GITHUB_EVENT_NAME="pull_request")
        result = self.run_helper("session")
        self.run_helper("cleanup", SESSION_DIRECTORY=result["directory"])
        for ref in ("refs/heads/refs/tags/published", "refs/remotes/origin/refs/tags/published"):
            result = subprocess.run(["git", "show-ref", "--verify", ref],
                                    cwd=self.repo, capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_sessions_use_distinct_directories_and_paths(self):
        first = self.run_helper("session")
        second = self.run_helper("session")
        self.assertNotEqual(first["directory"], second["directory"])
        for result in (second, first):
            directory = Path(result["directory"])
            self.assertTrue((directory / "home").is_dir())
            self.assertTrue((directory / "tmp").is_dir())
            self.assertTrue((directory / "work").is_dir())
            self.assertTrue(result["path"].startswith(f"{directory}/home/.local/bin:"))
            self.run_helper("cleanup", SESSION_DIRECTORY=str(directory))
            self.assertFalse(directory.exists())


if __name__ == "__main__":
    unittest.main()
