"""Key-aware SDK/system audit tests; keys are generated locally and never printed."""

import contextlib
import io
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import content_audit


class ContentAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("openssl") is None:
            raise RuntimeError("Run these audit tests in a runtime image containing OpenSSL; do not skip them")
        cls.fixture = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.fixture.cleanup)
        cls.material = Path(cls.fixture.name)

        def openssl(*args):
            subprocess.run(["openssl", *args], check=True, cwd=cls.material,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=audit-test-fixture",
                "-days", "1", "-keyout", "key.pem", "-out", "cert.pem")
        openssl("x509", "-in", "cert.pem", "-outform", "DER", "-out", "cert.der")
        openssl("pkey", "-in", "key.pem", "-outform", "DER", "-out", "private.pk8")
        openssl("pkcs8", "-topk8", "-in", "key.pem", "-outform", "DER", "-passout",
                "pass:fixture-password", "-out", "encrypted.der")
        openssl("pkey", "-in", "key.pem", "-pubout", "-out", "public.pem")
        for password, name in (("", "private.pfx"), ("fixture-password", "opaque.pfx"),
                               ("android", "debug.keystore")):
            openssl("pkcs12", "-export", "-inkey", "key.pem", "-in", "cert.pem",
                    "-passout", "pass:" + password, "-out", name)
        for password, name in (("", "trust.p12"), ("changeit", "java-trust.p12")):
            openssl("pkcs12", "-export", "-nokeys", "-in", "cert.pem",
                    "-passout", "pass:" + password, "-out", name)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def install(self, relative, material):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((self.material / material).read_bytes())
        return path

    def report(self):
        return content_audit.inspect_credentials((self.root,))

    def ordered_report(self):
        walk = content_audit.os.walk

        def ordered(*args, **kwargs):
            for directory, directories, names in walk(*args, **kwargs):
                # Force source/certificate aliases before sensitive filenames,
                # independently of filesystem insertion/enumeration order.
                yield directory, directories, sorted(names, key=lambda name: (not name.startswith("a-"), name))

        with patch.object(content_audit.os, "walk", side_effect=ordered):
            return self.report()

    def store(self, entries, magic=0xFEEDFEED):
        def utf(value):
            return struct.pack(">H", len(value)) + value

        data = struct.pack(">III", magic, 2, len(entries))
        for tag in entries:
            data += struct.pack(">I", tag)
            if tag == 2:
                cert = (self.material / "cert.der").read_bytes()
                data += utf(b"fixture") + b"\0" * 8 + utf(b"X.509") + struct.pack(">I", len(cert)) + cert
            # Private/secret entry fixtures need only the tag: the inspector must
            # reject them without reading/decrypting private contents.
        return data + b"\0" * 20

    def test_reported_system_and_android_cmake_assets_and_engine_keystore_are_caught(self):
        system = self.install("usr/share/cmake-3.28/Templates/Windows/Windows_TemporaryKey.pfx", "private.pfx")
        android = self.install("opt/android-sdk/cmake/3.22.1/share/cmake-3.22/Templates/Windows/Windows_TemporaryKey.pfx", "private.pfx")
        engine = self.root / "opt/flutter/engine/src/flutter/testing/android/native_activity/debug.keystore"
        engine.parent.mkdir(parents=True)
        engine.write_bytes(self.store([1]))
        findings = self.report()["findings"]
        self.assertEqual({f["path"] for f in findings}, {str(system), str(android), str(engine)})
        self.assertEqual({f["reason"] for f in findings}, {"PKCS#12 private-key bag", "Java private/secret-key entry"})
        self.assertTrue(all(len(f["sha256"]) == 64 for f in findings))

    def test_production_scope_includes_system_sdks_and_original_roots(self):
        self.assertTrue({"/opt", "/usr", "/etc", "/var", "/root", "/home", "/cache", "/workspace", "/tmp"}
                        <= {str(p) for p in content_audit.ROOTS})

    def test_normal_certificates_and_certificate_only_pkcs12_jks_stores_pass(self):
        self.install("etc/ssl/certs/ca-certificates.crt", "cert.pem")
        self.install("usr/share/ca-certificates/root.pem", "cert.pem")
        self.install("etc/ssl/trust.p12", "trust.p12")
        self.install("etc/java/trust.p12", "java-trust.p12")
        self.install("etc/ssl/public.pem", "public.pem")
        store = self.root / "etc/ssl/certs/java/cacerts"
        store.parent.mkdir(parents=True)
        store.write_bytes(self.store([2, 2]))
        link = self.root / "etc/ssl/certs/root.pem"
        link.symlink_to(self.root / "usr/share/ca-certificates/root.pem")
        report = self.report()
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["candidate_files_inspected"], 6)

    def test_private_entry_after_trusted_certificate_is_not_mistaken_for_truststore(self):
        self.assertTrue(content_audit.jks_has_key(self.store([2, 1])))

    def test_normal_cacerts_package_configuration_is_not_a_keystore(self):
        path = self.root / "etc/default/cacerts"
        path.parent.mkdir(parents=True)
        path.write_text("# defaults for ca-certificates-java\n#storepass=''\ncacerts_updates=yes\n")
        self.assertEqual(self.report()["findings"], [])

    def test_android_debug_pkcs12_key_and_additional_flutter_pem_fixture_are_caught(self):
        debug = self.install("opt/flutter/engine/src/flutter/testing/android/native_activity/debug.keystore", "debug.keystore")
        pem = self.install("opt/flutter/packages/flutter_tools/test/data/asset_test/tls_cert/dummy-key.pem", "key.pem")
        findings = self.report()["findings"]
        self.assertEqual({f["path"] for f in findings}, {str(debug), str(pem)})
        self.assertEqual({f["reason"] for f in findings}, {"PKCS#12 private-key bag", "PEM private-key material"})

    def test_worker_preserves_key_findings_in_failed_audit_evidence(self):
        import worker
        path = self.install("opt/sdk/private.pem", "key.pem")
        (self.root / "toolchain.json").write_text('{"variant":"fixture"}')
        report = {}
        with patch.object(worker, "METADATA", self.root), \
                patch.object(worker, "inspect_credentials", side_effect=self.report):
            with self.assertRaisesRegex(ValueError, "Potential embedded credential"):
                worker.audit(report)
        self.assertEqual(report["content_assessment"]["findings"][0]["path"], str(path))

    def test_jceks_secret_key_entry_is_rejected(self):
        self.assertTrue(content_audit.jks_has_key(self.store([2, 3], magic=0xCECECECE)))

    def test_opaque_or_corrupt_keystores_fail_closed(self):
        opaque = self.install("opt/tool/opaque.pfx", "opaque.pfx")
        broken = self.root / "opt/tool/broken.jks"
        broken.write_bytes(b"\xfe\xed\xfe\xed\x00")
        findings = self.report()["findings"]
        self.assertEqual({f["path"] for f in findings}, {str(opaque), str(broken)})
        self.assertTrue(all("uninspectable" in f["reason"] for f in findings))

    def test_private_pem_and_der_sdk_files_are_caught(self):
        pem = self.install("opt/flutter/fixtures/private.pem", "key.pem")
        der = self.install("usr/share/tool/private.pk8", "private.pk8")
        ssh = self.install("etc/ssh/ssh_host_rsa_key", "key.pem")
        findings = self.report()["findings"]
        self.assertEqual({f["path"] for f in findings}, {str(pem), str(der), str(ssh)})
        self.assertEqual({f["reason"] for f in findings}, {"PEM private-key material", "DER private-key material"})

    def test_unreadable_encrypted_der_is_not_assumed_to_be_a_certificate(self):
        path = self.install("opt/tool/encrypted.der", "encrypted.der")
        self.assertEqual(content_audit.classify_key_file(path), "uninspectable key/certificate file")

    def test_key_after_long_certificate_bundle_is_not_missed(self):
        path = self.install("etc/ssl/bundle.pem", "cert.pem")
        path.write_bytes(path.read_bytes() * 100 + (self.material / "key.pem").read_bytes())
        self.assertEqual(content_audit.classify_key_file(path), "PEM private-key material")

    def test_reported_dart_source_paths_with_embedded_private_keys_are_caught(self):
        relatives = (
            "opt/flutter/examples/image_list/lib/main.dart",
            "cache/pub/hosted/pub.dev/http_multi_server-3.2.2/test/http_multi_server_test.dart",
            "cache/pub/hosted/pub.dev/shelf-1.4.2/test/ssl_certs.dart",
        )
        paths = []
        for relative in relatives:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"const fixture = r'''" + (self.material / "key.pem").read_bytes() + b"''';\n")
            paths.append(str(path))
        report = self.report()
        self.assertEqual({f["path"] for f in report["findings"]}, set(paths))
        self.assertEqual({f["reason"] for f in report["findings"]}, {"embedded PEM private-key material"})
        self.assertEqual(report["source_files_inspected"], 3)

    def test_escaped_private_pem_detected_but_header_constants_and_certificates_are_not(self):
        private = (self.material / "key.pem").read_bytes()
        self.assertTrue(content_audit.has_embedded_private_pem(private.replace(b"\n", b"\\n")))
        self.assertFalse(content_audit.has_embedded_private_pem((self.material / "cert.pem").read_bytes()))
        self.assertFalse(content_audit.has_embedded_private_pem(
            b"const begin = '-----BEGIN PRIVATE KEY-----'; const end = '-----END PRIVATE KEY-----';"))

    def test_source_scan_bound_is_recorded_and_not_applied_to_key_files(self):
        path = self.root / "large.dart"
        path.write_bytes(b" " * 100 + (self.material / "key.pem").read_bytes())
        key = self.install("key.pem", "key.pem")
        with patch.object(content_audit, "SOURCE_MAX_BYTES", 64):
            report = self.report()
        self.assertEqual(report["source_files_over_limit"], 1)
        self.assertEqual(report["source_file_limit_bytes"], 64)
        self.assertEqual([f["path"] for f in report["findings"]], [str(key)])

    def test_symlinked_key_detected_without_duplicate_inode_or_directory_recursion(self):
        key = self.install("opt/sdk/key.pem", "key.pem")
        key.with_name("alias.pem").symlink_to(key)
        (self.root / "opt/sdk/loop").symlink_to(self.root / "opt", target_is_directory=True)
        key.with_name("dangling.pem").symlink_to(key.with_name("absent"))
        self.assertEqual(len(self.report()["findings"]), 1)

    def test_source_alias_before_binary_store_cannot_suppress_key_inspection(self):
        key = self.install("private.pfx", "private.pfx")
        alias = self.root / "a-source.txt"
        for kind in ("symlink", "hardlink"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    alias.symlink_to(key)
                else:
                    alias.hardlink_to(key)
                report = self.ordered_report()
                alias.unlink()
                self.assertEqual([finding["path"] for finding in report["findings"]], [str(key)])
                self.assertEqual(report["findings"][0]["reason"], "PKCS#12 private-key bag")
                self.assertEqual(report["candidate_files_inspected"], 2)

    def test_oversized_source_alias_is_not_marked_as_inspected(self):
        key = self.install("private.pfx", "private.pfx")
        (self.root / "a-source.txt").symlink_to(key)
        with patch.object(content_audit, "SOURCE_MAX_BYTES", 1):
            report = self.ordered_report()
        self.assertEqual([finding["path"] for finding in report["findings"]], [str(key)])
        self.assertEqual(report["source_files_over_limit"], 1)
        self.assertEqual(report["candidate_files_inspected"], 1)

    def test_credential_name_aliases_are_preserved_after_certificate_inspection(self):
        certificate = self.install("a-certificate.pem", "cert.pem")
        aliases = [self.root / name for name in (".netrc", "credentials.json", "subdir/.netrc")]
        for alias in aliases:
            alias.parent.mkdir(parents=True, exist_ok=True)
            alias.hardlink_to(certificate)
        report = self.ordered_report()
        self.assertEqual({finding["path"] for finding in report["findings"]}, {str(alias) for alias in aliases})
        self.assertTrue(all(finding["reason"] == "credential configuration file" for finding in report["findings"]))
        self.assertEqual(report["candidate_files_inspected"], 4)

    def test_certificate_aliases_only_deduplicate_equivalent_inspection_classes(self):
        source_alias = self.install("a-source.txt", "cert.pem")
        certificate = self.root / "ca.pem"
        certificate.symlink_to(source_alias)
        (self.root / "duplicate.crt").hardlink_to(source_alias)
        with patch.object(content_audit, "classify_key_file", wraps=content_audit.classify_key_file) as classify:
            report = self.ordered_report()
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["candidate_files_inspected"], 2)
        classify.assert_called_once_with(certificate)

    def test_original_credential_configuration_detection_preserved(self):
        path = self.root / "home/runtime/.netrc"
        path.parent.mkdir(parents=True)
        path.write_text("synthetic fixture; no credential")
        self.assertEqual(self.report()["findings"][0]["reason"], "credential configuration file")

    def test_private_material_is_not_printed_or_returned(self):
        self.install("opt/tool/key.pem", "key.pem")
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            report = self.report()
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("BEGIN PRIVATE KEY", repr(report))
        self.assertNotIn((self.material / "key.pem").read_text(), repr(report))

    def test_directory_read_errors_fail_closed(self):
        def unreadable(_root, **kwargs):
            kwargs["onerror"](PermissionError("synthetic unreadable subtree"))

        with patch.object(content_audit.os, "walk", side_effect=unreadable):
            with self.assertRaisesRegex(PermissionError, "unreadable subtree"):
                self.report()


if __name__ == "__main__":
    unittest.main()
