"""Fast local behavioral tests; mocked Docker tests are not image/registry evidence."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import validate
import worker


def metadata(variant):
    return {
        "variant": variant,
        "selection": {"flutter": {"hash": "revision", "version": "version"},
                      "android_packages": ["platform-tools", "ndk;28.2.13676358"]},
        "flutter": {"frameworkRevision": "revision", "frameworkVersion": "version",
                    "dartSdkVersion": "dart", "engineRevision": "engine"},
        "android": {"platform-tools": {}, "ndk;28.2.13676358": {}},
        "java": 'openjdk version "21.0.1"',
    }


def image(variant):
    return {"Id": "sha256:" + variant, "Os": "linux", "Architecture": "amd64",
            "Config": {"User": "10001:10001", "Env": ["PATH=/opt/flutter/bin"], "Labels": {
                "org.opencontainers.image.revision": "checkpoint", "io.commons.flutter.publication": "pair"}}}


class PairTests(unittest.TestCase):
    def test_matching_pair(self):
        validate.check_pair(metadata("lightweight"), metadata("full"), ["platform-tools"])

    def test_each_version_mismatch_rejects_pair(self):
        for key in metadata("full")["flutter"]:
            with self.subTest(key=key):
                full = metadata("full")
                full["flutter"][key] = "other"
                with self.assertRaisesRegex(ValueError, "mismatch"):
                    validate.check_pair(metadata("lightweight"), full, [])

    def test_missing_retained_support_fails_even_when_selection_omits_it(self):
        with self.assertRaisesRegex(ValueError, "Missing supported Android"):
            validate.check_pair(metadata("lightweight"), metadata("full"), ["platforms;android-34"])

    def test_wrong_jdk_selection_and_variant_rejected(self):
        for field, value in (("java", 'openjdk version "17"'), ("variant", "lightweight"),
                             ("selection", {})):
            with self.subTest(field=field), self.assertRaises(ValueError):
                full = metadata("full")
                full[field] = value
                validate.check_pair(metadata("lightweight"), full, [])

    def test_metadata_must_match_resolved_release(self):
        light, full = metadata("lightweight"), metadata("full")
        light["selection"]["flutter"]["hash"] = "not-installed"
        full["selection"] = copy.deepcopy(light["selection"])
        with self.assertRaisesRegex(ValueError, "differs from resolved"):
            validate.check_pair(light, full, [])

    def test_image_provenance_architecture_user_and_credentials(self):
        validate.check_image(image("full"), "checkpoint")
        cases = []
        wrong = image("full")
        wrong["Architecture"] = "arm64"
        cases.append(wrong)
        wrong = image("full")
        wrong["Config"]["User"] = "0:0"
        cases.append(wrong)
        wrong = image("full")
        wrong["Config"]["Env"] += ["GITHUB_TOKEN=synthetic-test-value"]
        cases.append(wrong)
        for candidate in cases:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                validate.check_image(candidate, "checkpoint")
        with self.assertRaisesRegex(ValueError, "source revision"):
            validate.check_image(image("full"), "another-checkpoint")


class WorkloadTests(unittest.TestCase):
    def test_root_cannot_run_workloads(self):
        with patch.object(worker.os, "getuid", return_value=0):
            with self.assertRaisesRegex(ValueError, "arbitrary non-default UID"):
                worker.workload("lightweight", {})

    def test_separates_dependencies_from_tool_downloads(self):
        text = """Resolving dependencies...
Downloading https://services.gradle.org/distributions/gradle-8.14-bin.zip
Downloading https://repo.maven.apache.org/maven2/example.jar
Downloading android-arm64-release/linux-x64 tools...
Installing Android SDK Build-Tools 36
Preparing "Install NDK (Side by side) 28.2.13676358".
Downloading https://dl.google.com/android/repository/platform-36.zip
"""
        result = worker.classify_downloads(text)
        self.assertEqual(len(result["toolchain"]), 4)
        self.assertEqual(len(result["project_dependencies"]), 3)

    def test_local_engine_access_is_not_a_download(self):
        self.assertEqual(worker.classify_downloads(
            "file:///opt/flutter-storage/download.flutter.io/io/flutter/x86_64_release/artifact.jar"
        ), {"toolchain": [], "project_dependencies": []})

    def test_added_removed_and_replaced_artifacts_fail(self):
        worker.compare_snapshots({"sdk": "hash"}, {"sdk": "hash"})
        for after in ({}, {"sdk": "hash", "new": "download"}, {"sdk": "different"}):
            with self.subTest(after=after), self.assertRaisesRegex(ValueError, "toolchain changed"):
                worker.compare_snapshots({"sdk": "hash"}, after)

    def test_real_subprocess_failures_are_not_converted_to_success(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(worker, "EVIDENCE", Path(directory)):
            report = {"commands": []}
            with self.assertRaisesRegex(RuntimeError, "exited 7"):
                worker.run([sys.executable, "-c", "raise SystemExit(7)"], report, "failure", cwd=directory)
            self.assertEqual(report["commands"][0]["exit_code"], 7)

    def test_successful_command_that_installs_tools_still_fails(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(worker, "EVIDENCE", Path(directory)):
            with self.assertRaisesRegex(ValueError, "toolchain acquisition"):
                worker.run([sys.executable, "-c", "print('Installing Android SDK Platform 36')"],
                           {"commands": []}, "download", cwd=directory)

    def test_archive_requires_actual_engine_and_native_library_for_each_abi(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "test.aab"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("base/lib/x86_64/libflutter.so", b"synthetic fixture")
                output.writestr("base/lib/x86_64/libreadiness.so", b"synthetic fixture")
            worker.check_archive(archive, ["x86_64"])
            with self.assertRaisesRegex(ValueError, "Missing arm64"):
                worker.check_archive(archive, ["x86_64", "arm64-v8a"])


class FailClosedTests(unittest.TestCase):
    """Exercise real orchestration control flow with explicit external-boundary fakes."""

    def test_failed_workload_preserves_refs_cleans_resources_and_reports_failure(self):
        calls = []

        def fake_docker(*args, **_kwargs):
            calls.append(args)
            if args[:2] == ("image", "inspect"):
                return json.dumps([image(args[2])])
            if args[0] in ("rm", "volume"):
                return ""
            self.fail(f"Unexpected Docker mutation: {args}")

        def fake_git(command, **_kwargs):
            return "checkpoint\n" if command[1] == "rev-parse" else ""

        def fake_container(_image, case, destination, containers, volumes):
            containers.append("synthetic-container")
            volumes.append("synthetic-volume")
            if case == "audit":
                data = metadata(destination.parent.name)
                for package in (validate.HERE.parent / "android-packages.txt").read_text().splitlines():
                    data["android"][package] = {}
                return {"metadata": data}
            raise RuntimeError("controlled real-workload boundary failure")

        with tempfile.TemporaryDirectory() as directory, \
                patch.object(validate, "docker", side_effect=fake_docker), \
                patch.object(validate.subprocess, "check_output", side_effect=fake_git), \
                patch.object(validate, "run_container", side_effect=fake_container):
            with self.assertRaisesRegex(RuntimeError, "controlled real-workload"):
                validate.validate(["lightweight", "full"], Path(directory))
            summary = json.loads(next(Path(directory).glob("*/summary.json")).read_text())
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["cleanup_errors"], [])
            self.assertIn("controlled real-workload", summary["error"])
        self.assertTrue(any(call[0] == "rm" for call in calls))
        self.assertTrue(any(call[:2] == ("volume", "rm") for call in calls))
        self.assertEqual(sum(call[:2] == ("image", "inspect") for call in calls), 4)
        self.assertFalse(any(call[0] in ("push", "tag", "login", "buildx") for call in calls))

    def test_actual_container_exit_failure_is_fatal(self):
        calls = []

        def fake_docker(*args, **_kwargs):
            calls.append(args)
            if args[0] == "inspect":
                return json.dumps([{"State": {"ExitCode": 19}}])
            if args[0] == "wait":
                return "0\n"
            return ""

        with tempfile.TemporaryDirectory() as directory, patch.object(validate, "docker", side_effect=fake_docker), \
                patch.object(validate.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
            with self.assertRaisesRegex(RuntimeError, "sdk35 failed"):
                validate.run_container("sha256:test", "sdk35", Path(directory) / "result", [], [])
        self.assertTrue(any(call[0] == "stop" for call in calls))
        self.assertTrue(any(call[0] == "cp" and ":/workspace/evidence/." in call[1] for call in calls))


class ResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("resolve", Path(__file__).resolve().parents[1] / "resolve.py")
        cls.resolver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.resolver)

    def test_resolves_current_stable_x64_and_retains_consumer_versions(self):
        index = {"base_url": "https://official.invalid", "current_release": {"stable": "new"}, "releases": [
            {"hash": "old", "channel": "stable", "version": "old"},
            {"hash": "new", "channel": "stable", "dart_sdk_arch": "arm64"},
            {"hash": "new", "channel": "stable", "dart_sdk_arch": "x64", "archive": "new.tar.xz",
             "version": "new", "sha256": "checksum"},
        ]}
        xml = b'''<repository><remotePackage path="cmdline-tools;latest"><channelRef ref="channel-0"/>
        <archives><archive><host-os>linux</host-os><complete><url>tools.zip</url><checksum>sum</checksum>
        </complete></archive></archives></remotePackage></repository>'''
        with patch.object(self.resolver, "fetch", side_effect=[json.dumps(index).encode(),
                          b'val compileSdkVersion: Int = 37\nval ndkVersion: String = "29.0.1"', xml]):
            result = self.resolver.resolve("ubuntu@sha256:fixture")
        self.assertEqual(result["flutter"]["version"], "new")
        self.assertEqual(result["flutter"]["dart_sdk_arch"], "x64")
        for package in ("platforms;android-34", "platforms;android-35", "platforms;android-36",
                        "platforms;android-37", "ndk;28.2.13676358", "ndk;29.0.1", "cmake;3.22.1"):
            self.assertIn(package, result["android_packages"])

    def test_upstream_failure_does_not_select_stale_release(self):
        with patch.object(self.resolver, "fetch", side_effect=OSError("upstream unavailable")):
            with self.assertRaisesRegex(OSError, "upstream unavailable"):
                self.resolver.resolve("base")


if __name__ == "__main__":
    unittest.main()
