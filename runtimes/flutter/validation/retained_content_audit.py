"""Bounded acceptance checks for SDK Git objects and confirmed preload fixtures."""

from collections import Counter
import hashlib
import posixpath
import subprocess
import tarfile


GIT_ORIGIN = "https://github.com/flutter/flutter.git"
PRELOAD_ASSETS = {
    "flutter_template_images": ("templates/app/winuwp.tmpl/runner_uwp/Windows_TemporaryKey.pfx",
                                "a957fb8c8a3e3e7b1b8d2c58e97e02759b61cd7cbecca409c0763c8d6d9691f4"),
    "http_multi_server": ("test/http_multi_server_test.dart", "7691587fa5d06046dae7bcb48a4ece6cdcf11e2f5cba58ae6e2310c0f0084b49"),
    "shelf": ("test/ssl_certs.dart", "f133db769be943f71c8ef56dfb046e16b4ec7620aa93d3a25717d42d8f0e05c4"),
    "googleapis_auth": ("test/test_utils.dart", "f0a9f91be4a427d735d1bfa4a2b1d8490c3c6663a48f02911217be5dddbfe957"),
}
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_EXPANDED_BYTES = 128 * 1024 * 1024
MAX_MEMBERS = 20000
MAX_ASSET_BYTES = 2 * 1024 * 1024


def inspect_sdk_git(root, selection):
    report = {"path": str(root / ".git"), "findings": []}

    def git(*args):
        # Do not permit retrieval even if the repository policy under inspection
        # is wrong. --local config reads below still inspect the actual file policy.
        return subprocess.check_output(["git", "-C", str(root), "-c", "protocol.allow=never",
                                        "-c", "protocol.https.allow=never", *args],
                                       text=True, stderr=subprocess.PIPE, timeout=120).strip()

    try:
        revision, version = selection["flutter"]["hash"], selection["flutter"]["version"]
        actual = {"head": git("rev-parse", "HEAD"),
                  "tag": git("rev-parse", f"refs/tags/{version}^{{commit}}"),
                  "branch": git("symbolic-ref", "HEAD"),
                  "remote_stable": git("rev-parse", "refs/remotes/origin/stable"),
                  "origin": git("remote", "get-url", "origin"),
                  "shallow": git("rev-parse", "--is-shallow-repository"),
                  "protocol": git("config", "--local", "--get", "protocol.allow"),
                  "https_protocol": git("config", "--local", "--get", "protocol.https.allow")}
        expected = {"head": revision, "tag": revision, "branch": "refs/heads/stable",
                    "remote_stable": revision, "origin": GIT_ORIGIN, "shallow": "true",
                    "protocol": "never", "https_protocol": "never"}
        report["metadata"] = dict(actual, origin=actual["origin"] if actual["origin"] == GIT_ORIGIN else "<unexpected remote>")
        if actual != expected:
            report["findings"].append("SDK release metadata or transport policy mismatch")
        objects = Counter(git("cat-file", "--batch-all-objects", "--batch-check=%(objecttype)").splitlines())
        report["local_object_counts"] = dict(objects)
        if objects.get("blob", 0):
            report["findings"].append("SDK Git object store retains blobs, including possible unreachable fixtures")
        tree = {}
        for entry in git("ls-tree", "-r", "-z", "HEAD").split("\0"):
            if entry:
                info, path = entry.split("\t", 1)
                mode, _kind, oid = info.split()
                tree[path] = (mode, oid, "0")
        index = {}
        for entry in git("ls-files", "--stage", "-z").split("\0"):
            if entry:
                info, path = entry.split("\t", 1)
                index[path] = tuple(info.split())
        report["index_entries"] = len(index)
        if not tree or index != tree:
            report["findings"].append("SDK index does not exactly describe the retained release tree")
    except (subprocess.SubprocessError, OSError, ValueError, KeyError):
        # Avoid command stderr or arbitrary object contents in evidence.
        report["findings"].append("SDK Git metadata/object inspection failed")
    return report


def inspect_preload_archives(root):
    report = {"root": str(root), "findings": [], "archives_inspected": 0,
              "scope": "confirmed asset paths in four named Pub package families; never extracts files",
              "limits": {"compressed_bytes": MAX_ARCHIVE_BYTES, "expanded_bytes": MAX_EXPANDED_BYTES,
                         "members": MAX_MEMBERS, "asset_bytes": MAX_ASSET_BYTES}}
    for name, (member_path, known_sha) in PRELOAD_ASSETS.items():
        for path in sorted(root.glob(name + "-*.tar.gz")):
            reason = None
            asset_sha = None
            if path.resolve() != path.absolute() or not path.is_file():
                report["findings"].append({"path": str(path), "reason": "unexpected preload archive path"})
                continue
            if path.stat().st_size > MAX_ARCHIVE_BYTES:
                report["findings"].append({"path": str(path), "reason": "preload archive exceeds inspection bound"})
                continue
            report["archives_inspected"] += 1
            try:
                expanded = 0
                with tarfile.open(path, "r|gz") as archive:
                    for count, entry in enumerate(archive, 1):
                        expanded += entry.size
                        if count > MAX_MEMBERS or expanded > MAX_EXPANDED_BYTES:
                            reason = "preload archive exceeds inspection bound"
                            break
                        if posixpath.normpath(entry.name) != member_path:
                            continue
                        if not entry.isfile() or entry.size > MAX_ASSET_BYTES:
                            reason = "uninspectable confirmed preload asset"
                            break
                        asset_sha = hashlib.sha256(archive.extractfile(entry).read()).hexdigest()
                        reason = ("confirmed private-key asset retained in preload archive" if asset_sha == known_sha
                                  else "changed confirmed preload asset requires review")
                        break
            except (tarfile.TarError, OSError, EOFError):
                reason = "preload archive cannot be inspected"
            if reason:
                finding = {"path": str(path), "reason": reason}
                if asset_sha:
                    finding["asset_sha256"] = asset_sha
                report["findings"].append(finding)
    return report
