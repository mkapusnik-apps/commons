"""Bounded retained-object/archive audit tests; no real keys or remote services."""

import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import retained_content_audit as audit
from test_prepare_sdk_git import ReleaseFixture


class GitContentAuditTests(ReleaseFixture, unittest.TestCase):
    def report(self):
        with patch.object(audit, "GIT_ORIGIN", self.origin):
            return audit.inspect_sdk_git(self.sdk, json.loads(self.selection.read_text()))

    def test_genuine_blobless_release_and_index_pass(self):
        self.prepared()
        report = self.report()
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["local_object_counts"].get("blob", 0), 0)
        self.assertEqual(report["index_entries"], 2)

    def test_unreachable_blob_is_rejected_without_reading_its_content(self):
        self.prepared()
        import subprocess
        subprocess.run(["git", "-C", str(self.sdk), "hash-object", "-w", "--stdin"],
                       input=b"synthetic unreachable content", check=True, stdout=subprocess.PIPE)
        report = self.report()
        self.assertEqual(report["local_object_counts"]["blob"], 1)
        self.assertTrue(any("retains blobs" in finding for finding in report["findings"]))
        self.assertNotIn("synthetic unreachable content", repr(report))

    def test_index_entry_removal_fails(self):
        self.prepared()
        self.git(self.sdk, "update-index", "--force-remove", "fixture.txt")
        self.assertTrue(any("index" in finding for finding in self.report()["findings"]))

    def test_wrong_revision_or_origin_fails_without_logging_unexpected_remote(self):
        self.prepared()
        metadata = {"flutter": {"hash": "0" * 40, "version": self.version}}
        report = audit.inspect_sdk_git(self.sdk, metadata)  # Default official origin also mismatches.
        self.assertTrue(report["findings"])
        self.assertEqual(report["metadata"]["origin"], "<unexpected remote>")

    def test_missing_sdk_repository_fails_closed(self):
        report = audit.inspect_sdk_git(self.base / "absent", {"flutter": {"hash": self.revision, "version": self.version}})
        self.assertTrue(report["findings"])

    def test_command_transport_guard_does_not_mask_bad_repository_policy(self):
        self.prepared()
        self.git(self.sdk, "config", "--local", "protocol.https.allow", "always")
        report = self.report()
        self.assertEqual(report["metadata"]["https_protocol"], "always")
        self.assertTrue(report["findings"])


class PreloadAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def archive(self, name, entries):
        target = self.root / name
        with tarfile.open(target, "w:gz") as package:
            for path, content, kind in entries:
                member = tarfile.TarInfo(path)
                member.type = kind
                if kind == tarfile.REGTYPE:
                    member.size = len(content)
                    package.addfile(member, io.BytesIO(content))
                else:
                    member.linkname = "outside"
                    package.addfile(member)
        return target

    def test_confirmed_fixture_is_detected_by_exact_member_hash_without_export(self):
        data = b"synthetic fixture content"
        target = self.archive("googleapis_auth-2.3.2.tar.gz", [("test/test_utils.dart", data, tarfile.REGTYPE)])
        with patch.dict(audit.PRELOAD_ASSETS, {"googleapis_auth": ("test/test_utils.dart", hashlib.sha256(data).hexdigest())}):
            report = audit.inspect_preload_archives(self.root)
        self.assertEqual(report["findings"][0]["path"], str(target))
        self.assertIn("confirmed private-key asset", report["findings"][0]["reason"])
        self.assertNotIn(data.decode(), repr(report))

    def test_other_packages_and_absent_confirmed_members_do_not_false_positive(self):
        self.archive("unrelated-1.0.0.tar.gz", [("test/test_utils.dart", b"ordinary test", tarfile.REGTYPE)])
        self.archive("googleapis_auth-9.0.0.tar.gz", [("lib/auth.dart", b"runtime library", tarfile.REGTYPE)])
        report = audit.inspect_preload_archives(self.root)
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["archives_inspected"], 1)

    def test_changed_confirmed_member_is_not_silently_exempted(self):
        self.archive("shelf-9.0.0.tar.gz", [("./test/ssl_certs.dart", b"changed fixture", tarfile.REGTYPE)])
        self.assertIn("requires review", audit.inspect_preload_archives(self.root)["findings"][0]["reason"])

    def test_archive_symlink_member_and_corrupt_archive_fail_closed(self):
        self.archive("shelf-1.0.0.tar.gz", [("test/ssl_certs.dart", b"", tarfile.SYMTYPE)])
        (self.root / "http_multi_server-1.0.0.tar.gz").write_bytes(b"not an archive")
        report = audit.inspect_preload_archives(self.root)
        self.assertEqual(len(report["findings"]), 2)

    def test_symlinked_preload_archive_is_not_followed(self):
        target = self.archive("unrelated.tar.gz", [])
        alias = self.root / "shelf-1.0.0.tar.gz"
        alias.symlink_to(target)
        self.assertIn("unexpected preload archive path", audit.inspect_preload_archives(self.root)["findings"][0]["reason"])

    def test_compressed_expanded_member_and_asset_bounds_fail_closed(self):
        path = self.archive("shelf-1.0.0.tar.gz", [("lib/normal.dart", b"x" * 100, tarfile.REGTYPE),
                                                 ("test/ssl_certs.dart", b"fixture" * 10, tarfile.REGTYPE)])
        for setting in ("MAX_ARCHIVE_BYTES", "MAX_EXPANDED_BYTES", "MAX_MEMBERS", "MAX_ASSET_BYTES"):
            with self.subTest(setting=setting), patch.object(audit, setting, 1):
                self.assertTrue(audit.inspect_preload_archives(self.root)["findings"])
                self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
