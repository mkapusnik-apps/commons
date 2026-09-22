"""SDK sanitation behavior with synthetic files and isolated upstream responses."""

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("sanitize_sdk_keys", Path(__file__).resolve().parents[1] / "sanitize-sdk-keys.py")
sdk = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sdk)


class SdkSanitationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = b"synthetic fixture, not key bytes".ljust(2560, b".")
        self.digest = hashlib.sha256(self.data).hexdigest()
        patcher = patch.object(sdk.urllib.request, "urlopen", side_effect=AssertionError("Unmocked upstream request"))
        self.transport = patcher.start()
        self.addCleanup(patcher.stop)

    def put(self, relative, data=None):
        path = self.root / relative.lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.data if data is None else data)
        return path

    def remove(self, path):
        with contextlib.redirect_stdout(io.StringIO()):
            sdk.remove_verified(path, len(self.data), self.digest, "https://upstream.invalid/fixture")

    def test_exact_removal_idempotence_and_unrelated_files_preserved(self):
        path = self.put("target.pfx")
        other = self.put("other.pfx", b"unrelated")
        with patch.object(sdk.urllib.request, "urlopen", return_value=io.BytesIO(self.data)) as fetch:
            self.remove(path)
            fetch.assert_called_once_with("https://upstream.invalid/fixture", timeout=120)
        self.assertFalse(path.exists())
        self.assertEqual(other.read_bytes(), b"unrelated")
        self.remove(path)
        self.transport.assert_not_called()

    def test_wrong_size_or_digest_rejected_before_upstream(self):
        for data in (b"short", b"x" * len(self.data)):
            with self.subTest(size=len(data)):
                path = self.put("target.pfx", data)
                with self.assertRaisesRegex(ValueError, "Unexpected signing fixture content"):
                    self.remove(path)
                self.assertEqual(path.read_bytes(), data)
        self.transport.assert_not_called()

    def test_missing_path_is_noop_but_directory_is_not(self):
        self.remove(self.root / "missing")
        directory = self.root / "directory.pfx"
        directory.mkdir()
        with self.assertRaisesRegex(ValueError, "Unexpected signing fixture path"):
            self.remove(directory)
        self.transport.assert_not_called()

    def test_file_dangling_and_parent_symlinks_rejected_without_following(self):
        real = self.put("real/file.pfx")
        link = self.root / "link.pfx"
        for target in (real, self.root / "absent"):
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "Unexpected signing fixture path"):
                self.remove(link)
            self.assertTrue(link.is_symlink())
            link.unlink()
        directory_link = self.root / "linked-directory"
        directory_link.symlink_to(real.parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Unexpected signing fixture path"):
            self.remove(directory_link / real.name)
        self.assertEqual(real.read_bytes(), self.data)
        self.transport.assert_not_called()

    def test_mismatched_upstream_leaves_local_file_intact(self):
        path = self.put("target.pfx")
        with patch.object(sdk.urllib.request, "urlopen", return_value=io.BytesIO(b"changed upstream")):
            with self.assertRaisesRegex(ValueError, "differs from official upstream"):
                self.remove(path)
        self.assertEqual(path.read_bytes(), self.data)

    def test_network_failure_leaves_local_file_intact(self):
        path = self.put("target.pfx")
        with patch.object(sdk.urllib.request, "urlopen", side_effect=OSError("isolated transport error")):
            with self.assertRaisesRegex(OSError, "transport error"):
                self.remove(path)
        self.assertEqual(path.read_bytes(), self.data)

    def stage(self, stage, responses, fixtures=None):
        def fetch(url, timeout):
            self.assertEqual(timeout, 120)
            return io.BytesIO(responses[url])  # Reject every unexpected URL.

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(sdk, "Path", side_effect=lambda path: self.root / str(path).lstrip("/")))
            stack.enter_context(patch.object(sdk, "CMAKE_KEY_SHA256", self.digest))
            stack.enter_context(patch.object(sdk.urllib.request, "urlopen", side_effect=fetch))
            if fixtures is not None:
                stack.enter_context(patch.object(sdk, "FLUTTER_FIXTURES", fixtures))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            sdk.sanitize(stage)

    def test_system_cmake_scope_and_official_provenance(self):
        target = self.put("usr/share/cmake-3.28/Templates/Windows/Windows_TemporaryKey.pfx")
        unrelated = self.put("usr/share/cmake-3.28/Templates/Windows/other.pfx")
        self.stage("system", {"https://raw.githubusercontent.com/Kitware/CMake/v3.28.3/Templates/Windows/Windows_TemporaryKey.pfx": self.data})
        self.assertFalse(target.exists())
        self.assertTrue(unrelated.exists())

    def test_android_cmake_scope_does_not_remove_system_asset(self):
        target = self.put("opt/android-sdk/cmake/3.22.1/share/cmake-3.22/Templates/Windows/Windows_TemporaryKey.pfx")
        system = self.put("usr/share/cmake-3.28/Templates/Windows/Windows_TemporaryKey.pfx")
        self.stage("android", {"https://raw.githubusercontent.com/Kitware/CMake/v3.22.1/Templates/Windows/Windows_TemporaryKey.pfx": self.data})
        self.assertFalse(target.exists())
        self.assertTrue(system.exists())

    def test_all_flutter_fixtures_verified_at_selected_revision(self):
        revision = "a" * 40
        self.put("usr/local/share/flutter-runtime/resolved.json", json.dumps({"flutter": {"hash": revision}}).encode())
        fixtures, responses, targets = [], {}, []
        expected_paths = {
            "engine/src/flutter/testing/android/native_activity/debug.keystore",
            "packages/flutter_tools/test/data/asset_test/tls_cert/dummy-key.pem",
            "examples/image_list/lib/main.dart",
        }
        self.assertEqual({entry[0] for entry in sdk.FLUTTER_FIXTURES}, expected_paths)
        for relative, size, _digest in sdk.FLUTTER_FIXTURES:
            data = b"synthetic".ljust(size, b".")
            fixtures.append((relative, size, hashlib.sha256(data).hexdigest()))
            targets.append(self.put("opt/flutter/" + relative, data))
            responses[f"https://raw.githubusercontent.com/flutter/flutter/{revision}/{relative}"] = data
        core = self.put("opt/flutter/packages/flutter_tools/lib/runner.dart", b"required runtime")
        self.stage("flutter", responses, tuple(fixtures))
        self.assertTrue(all(not target.exists() for target in targets))
        self.assertEqual(core.read_bytes(), b"required runtime")

    def test_unknown_stage_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown sanitation stage"):
            sdk.sanitize("unexpected")


if __name__ == "__main__":
    unittest.main()
