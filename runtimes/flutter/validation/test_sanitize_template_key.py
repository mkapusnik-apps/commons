"""Exercise sanitation with synthetic bytes and archives, never signing keys/network."""

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "sanitize_template_key", Path(__file__).resolve().parents[1] / "sanitize-template-key.py")
sanitizer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sanitizer)

# Intentionally not a PFX. Only the expected digests are substituted in tests;
# production hash, filesystem, archive, provenance and removal logic still execute.
CONTENT = b"synthetic-public-template-fixture".ljust(2560, b".")


def archive(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as package:
        for name, kind, content in entries:
            member = tarfile.TarInfo(name)
            member.type = kind
            if kind == tarfile.REGTYPE:
                member.size = len(content)
                package.addfile(member, io.BytesIO(content))
            else:
                member.linkname = "unrelated-target"
                package.addfile(member)
    return output.getvalue()


class SanitationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.calls = []
        # Forbid transport even if a test accidentally fails to mock the boundary.
        self.transport = patch.object(sanitizer.urllib.request, "urlopen",
                                      side_effect=AssertionError("Network forbidden in unit tests")).start()
        self.addCleanup(patch.stopall)
        patch.object(sanitizer, "KEY_SHA256", hashlib.sha256(CONTENT).hexdigest()).start()

    def installed(self, version="5.0.0", content=CONTENT):
        target = self.cache / "hosted/pub.dev" / f"flutter_template_images-{version}" / sanitizer.MEMBER
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def upstream(self, version="5.0.0", entries=None):
        payload = archive(entries if entries is not None else [(sanitizer.MEMBER, tarfile.REGTYPE, CONTENT)])
        metadata = {"version": version, "pubspec": {"name": "flutter_template_images"},
                    "archive_url": f"https://pub.dev/api/archives/flutter_template_images-{version}.tar.gz",
                    "archive_sha256": hashlib.sha256(payload).hexdigest()}
        if version == "5.0.0":
            patch.object(sanitizer, "ARCHIVE_5_SHA256", metadata["archive_sha256"]).start()
        return metadata, payload

    def execute(self, metadata, payload):
        expected = [f"https://pub.dev/api/packages/flutter_template_images/versions/{metadata['version']}",
                    f"https://pub.dev/api/archives/flutter_template_images-{metadata['version']}.tar.gz"]

        def fetch(url):
            self.calls.append(url)
            if url == expected[0]:
                return json.dumps(metadata).encode()
            if url == expected[1]:
                return payload
            raise AssertionError(f"Unexpected upstream URL: {url}")

        with patch.object(sanitizer, "fetch", side_effect=fetch), contextlib.redirect_stdout(io.StringIO()) as output:
            sanitizer.sanitize(self.cache)
        return output.getvalue()

    def test_exact_verified_asset_removed_only_and_second_run_offline(self):
        target = self.installed()
        unrelated = target.with_name("another-signing-key.pfx")
        unrelated.write_bytes(b"unrelated synthetic data")
        other_package = self.cache / "hosted/pub.dev/other-5.0.0" / sanitizer.MEMBER
        other_package.parent.mkdir(parents=True)
        other_package.write_bytes(CONTENT)
        metadata, payload = self.upstream()
        output = self.execute(metadata, payload)
        self.assertFalse(target.exists())
        self.assertEqual(unrelated.read_bytes(), b"unrelated synthetic data")
        self.assertEqual(other_package.read_bytes(), CONTENT)
        self.assertIn("Removed verified flutter_template_images 5.0.0", output)
        self.assertNotIn(CONTENT.decode(), output)
        self.assertEqual(len(self.calls), 2)
        with patch.object(sanitizer, "fetch", side_effect=AssertionError("Unnecessary fetch")):
            sanitizer.sanitize(self.cache)
        self.transport.assert_not_called()

    def test_absent_package_or_absent_asset_does_not_fetch(self):
        with patch.object(sanitizer, "fetch", side_effect=AssertionError("Unnecessary fetch")):
            sanitizer.sanitize(self.cache)
            package = self.cache / "hosted/pub.dev/flutter_template_images-6.0.0"
            package.mkdir(parents=True)
            (package / "README.md").write_text("Template asset omitted upstream")
            sanitizer.sanitize(self.cache)

    def test_later_version_same_verified_asset_is_removed(self):
        target = self.installed("6.0.0")
        self.execute(*self.upstream("6.0.0"))
        self.assertFalse(target.exists())

    def test_wrong_length_and_same_length_wrong_hash_remain_untouched(self):
        for content in (b"short", b"x" * 2560):
            with self.subTest(length=len(content)):
                target = self.installed(content=content)
                with self.assertRaisesRegex(ValueError, "Unexpected template key content"):
                    sanitizer.sanitize(self.cache)
                self.assertEqual(target.read_bytes(), content)
        self.transport.assert_not_called()

    def test_invalid_version_is_rejected_before_upstream_access(self):
        target = self.installed("not-a-version")
        with self.assertRaisesRegex(ValueError, "package version"):
            sanitizer.sanitize(self.cache)
        self.assertEqual(target.read_bytes(), CONTENT)
        self.transport.assert_not_called()

    def test_file_and_dangling_symlinks_never_followed_or_removed(self):
        outside = self.root / "outside"
        outside.write_bytes(CONTENT)
        target = self.installed()
        target.unlink()
        for link_target in (outside, self.root / "missing"):
            with self.subTest(link_target=str(link_target)):
                target.symlink_to(link_target)
                with self.assertRaisesRegex(ValueError, "Unexpected template key path"):
                    sanitizer.sanitize(self.cache)
                self.assertTrue(target.is_symlink())
                self.assertEqual(outside.read_bytes(), CONTENT)
                target.unlink()
        self.transport.assert_not_called()

    def test_symlinked_package_directory_rejected(self):
        outside = self.root / "outside-package"
        asset = outside / sanitizer.MEMBER
        asset.parent.mkdir(parents=True)
        asset.write_bytes(CONTENT)
        hosted = self.cache / "hosted/pub.dev"
        hosted.mkdir(parents=True)
        (hosted / "flutter_template_images-5.0.0").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Unexpected template key path"):
            sanitizer.sanitize(self.cache)
        self.assertEqual(asset.read_bytes(), CONTENT)
        self.transport.assert_not_called()

    def test_symlinked_intermediate_template_directory_rejected(self):
        target = self.installed()
        directory = target.parent
        outside = self.root / "outside-runner"
        directory.rename(outside)
        directory.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Unexpected template key path"):
            sanitizer.sanitize(self.cache)
        self.assertEqual((outside / target.name).read_bytes(), CONTENT)
        self.transport.assert_not_called()

    def test_directory_instead_of_file_rejected(self):
        target = self.installed()
        target.unlink()
        target.mkdir()
        with self.assertRaisesRegex(ValueError, "Unexpected template key path"):
            sanitizer.sanitize(self.cache)
        self.assertTrue(target.is_dir())

    def test_unexpected_metadata_never_deletes(self):
        target = self.installed()
        for field, replacement in (("version", "9.9.9"), ("pubspec", {"name": "other"}),
                                   ("archive_url", "https://untrusted.invalid/key.tar.gz")):
            with self.subTest(field=field):
                metadata, payload = self.upstream()
                metadata[field] = replacement
                with patch.object(sanitizer, "fetch", return_value=json.dumps(metadata).encode()) as fetch:
                    with self.assertRaisesRegex(ValueError, "package provenance"):
                        sanitizer.sanitize(self.cache)
                fetch.assert_called_once()
                self.assertEqual(target.read_bytes(), CONTENT)

    def test_archive_checksum_mismatch_never_deletes(self):
        target = self.installed()
        metadata, payload = self.upstream()
        metadata["archive_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "archive checksum mismatch"):
            self.execute(metadata, payload)
        self.assertEqual(target.read_bytes(), CONTENT)

    def test_known_version_pin_rejects_changed_archive_even_when_metadata_agrees(self):
        target = self.installed()
        metadata, payload = self.upstream()
        with patch.object(sanitizer, "ARCHIVE_5_SHA256", "0" * 64):
            with self.assertRaisesRegex(ValueError, "Known template archive changed"):
                self.execute(metadata, payload)
        self.assertEqual(target.read_bytes(), CONTENT)

    def test_missing_duplicate_directory_and_link_archive_members_rejected(self):
        target = self.installed("6.0.0")
        valid = (sanitizer.MEMBER, tarfile.REGTYPE, CONTENT)
        for entries in ([], [valid, valid], [(sanitizer.MEMBER, tarfile.DIRTYPE, b"")],
                        [(sanitizer.MEMBER, tarfile.SYMTYPE, b"")],
                        [(sanitizer.MEMBER, tarfile.LNKTYPE, b"")]):
            with self.subTest(entries=[(name, kind) for name, kind, _ in entries]):
                with self.assertRaisesRegex(ValueError, "Unexpected template archive member"):
                    self.execute(*self.upstream("6.0.0", entries))
                self.assertEqual(target.read_bytes(), CONTENT)

    def test_installed_file_must_equal_verified_archive_member(self):
        target = self.installed("6.0.0")
        metadata, payload = self.upstream("6.0.0", [(sanitizer.MEMBER, tarfile.REGTYPE, b"different")])
        with self.assertRaisesRegex(ValueError, "differs from the official archive"):
            self.execute(metadata, payload)
        self.assertEqual(target.read_bytes(), CONTENT)

    def test_upstream_errors_and_malformed_responses_leave_asset_intact(self):
        target = self.installed()
        for response in (OSError("isolated upstream failure"), b"not JSON", b"{}"):
            with self.subTest(response=response):
                kwargs = {"side_effect": response} if isinstance(response, Exception) else {"return_value": response}
                with patch.object(sanitizer, "fetch", **kwargs):
                    with self.assertRaises((OSError, ValueError, KeyError)):
                        sanitizer.sanitize(self.cache)
                self.assertEqual(target.read_bytes(), CONTENT)

    def test_archive_transport_failure_leaves_asset_intact(self):
        target = self.installed()
        metadata, _payload = self.upstream()
        with patch.object(sanitizer, "fetch", side_effect=[json.dumps(metadata).encode(), OSError("download failed")]):
            with self.assertRaisesRegex(OSError, "download failed"):
                sanitizer.sanitize(self.cache)
        self.assertEqual(target.read_bytes(), CONTENT)


class PubSourceSanitationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.cache = Path(temporary.name)
        patcher = patch.object(sanitizer.urllib.request, "urlopen", side_effect=AssertionError("Network forbidden"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def fixture(self, name, version, member, size):
        content = b"synthetic Dart fixture, no private key".ljust(size, b".")
        target = self.cache / "hosted/pub.dev" / f"{name}-{version}" / member
        target.parent.mkdir(parents=True)
        target.write_bytes(content)
        payload = archive([(member, tarfile.REGTYPE, content)])
        metadata = {"version": version, "pubspec": {"name": name},
                    "archive_url": f"https://pub.dev/api/archives/{name}-{version}.tar.gz",
                    "archive_sha256": hashlib.sha256(payload).hexdigest()}
        return target, content, metadata, payload

    def test_dispatch_verifies_and_removes_exact_http_and_shelf_test_sources(self):
        rules = {
            "http_multi_server": ("3.2.2", "test/http_multi_server_test.dart", 15743,
                                  "7691587fa5d06046dae7bcb48a4ece6cdcf11e2f5cba58ae6e2310c0f0084b49"),
            "shelf": ("1.4.2", "test/ssl_certs.dart", 5610,
                      "f133db769be943f71c8ef56dfb046e16b4ec7620aa93d3a25717d42d8f0e05c4"),
        }
        fixtures = {name: self.fixture(name, *rule[:3]) for name, rule in rules.items()}
        original = sanitizer.sanitize_package
        observed = []

        def dispatch(cache, name, member, size, digest, known_archives):
            if name not in rules:
                return original(cache, name, member, size, digest, known_archives)
            observed.append(name)
            version, expected_member, expected_size, expected_digest = rules[name]
            self.assertEqual((member, size, digest), (expected_member, expected_size, expected_digest))
            self.assertIn(version, known_archives)
            target, content, metadata, payload = fixtures[name]
            urls = [f"https://pub.dev/api/packages/{name}/versions/{version}", metadata["archive_url"]]

            def fetch(url):
                return {urls[0]: json.dumps(metadata).encode(), urls[1]: payload}[url]

            with patch.object(sanitizer, "fetch", side_effect=fetch) as network:
                original(cache, name, member, size, hashlib.sha256(content).hexdigest(),
                         {version: metadata["archive_sha256"]})
                self.assertEqual([call.args[0] for call in network.call_args_list], urls)
            self.assertFalse(target.exists())

        # Only fixture expected digests are substituted; generic verification and
        # real dispatch targets/sizes/known-version rules are exercised unchanged.
        with patch.object(sanitizer, "sanitize_package", side_effect=dispatch), \
                contextlib.redirect_stdout(io.StringIO()):
            sanitizer.sanitize(self.cache)
        self.assertEqual(observed, ["http_multi_server", "shelf"])

    def test_new_package_archive_pin_mismatch_preserves_source(self):
        name, version, member = "http_multi_server", "3.2.2", "test/http_multi_server_test.dart"
        target, content, metadata, payload = self.fixture(name, version, member, 15743)
        with patch.object(sanitizer, "fetch", side_effect=[json.dumps(metadata).encode(), payload]):
            with self.assertRaisesRegex(ValueError, "Known template archive changed"):
                sanitizer.sanitize_package(self.cache, name, member, len(content),
                                           hashlib.sha256(content).hexdigest(), {version: "0" * 64})
        self.assertEqual(target.read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
