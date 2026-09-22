"""Remove exact verified upstream Pub test/template files containing private keys."""

import hashlib
import io
import json
import os
from pathlib import Path
import re
import tarfile
import urllib.request


PACKAGE = "flutter_template_images"
MEMBER = "templates/app/winuwp.tmpl/runner_uwp/Windows_TemporaryKey.pfx"
KEY_SHA256 = "a957fb8c8a3e3e7b1b8d2c58e97e02759b61cd7cbecca409c0763c8d6d9691f4"
ARCHIVE_5_SHA256 = "0120589a786dbae4e86af1f61748baccd8530abd56a60e7a13479647a75222fe"
ASSETS = (
    (PACKAGE, MEMBER, 2560, KEY_SHA256, {"5.0.0": ARCHIVE_5_SHA256}),
    ("http_multi_server", "test/http_multi_server_test.dart", 15743,
     "7691587fa5d06046dae7bcb48a4ece6cdcf11e2f5cba58ae6e2310c0f0084b49",
     {"3.2.2": "aa6199f908078bb1c5efb8d8638d4ae191aac11b311132c3ef48ce352fb52ef8"}),
    ("shelf", "test/ssl_certs.dart", 5610,
     "f133db769be943f71c8ef56dfb046e16b4ec7620aa93d3a25717d42d8f0e05c4",
     {"1.4.2": "e7dd780a7ffb623c57850b33f43309312fc863fb6aa3d276a754bb299839ef12"}),
    ("googleapis_auth", "test/test_utils.dart", 3661,
     "f0a9f91be4a427d735d1bfa4a2b1d8490c3c6663a48f02911217be5dddbfe957",
     {"2.3.2": "1417d8846663df5e7b77ca56591c5edd442c66ffc9c01ab036e138a21a148e86"}),
)


def fetch(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def archive_metadata(name, version):
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version):
        raise ValueError("Unexpected template package version")
    metadata = json.loads(fetch(f"https://pub.dev/api/packages/{name}/versions/{version}"))
    archive_url = f"https://pub.dev/api/archives/{name}-{version}.tar.gz"
    if (
        metadata["version"] != version
        or metadata["pubspec"]["name"] != name
        or metadata["archive_url"] != archive_url
    ):
        raise ValueError("Unexpected template package provenance")
    return metadata


def verify_archive(archive_bytes, metadata, known_archives):
    archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    if archive_sha256 != metadata["archive_sha256"]:
        raise ValueError("Template archive checksum mismatch")
    version = metadata["version"]
    if version in known_archives and archive_sha256 != known_archives[version]:
        raise ValueError("Known template archive changed")
    return archive_sha256


def sanitize_package(cache, name, member, size, sha256, known_archives):
    for package in sorted((cache / "hosted/pub.dev").glob(f"{name}-*")):
        target = package / member
        if not target.exists() and not target.is_symlink():
            continue
        # Never follow a substituted path or remove an unrelated signing bundle.
        if target.resolve() != target.absolute() or not target.is_file():
            raise ValueError("Unexpected template key path")
        content = target.read_bytes()
        if len(content) != size or hashlib.sha256(content).hexdigest() != sha256:
            raise ValueError("Unexpected template key content")
        version = package.name.removeprefix(f"{name}-")
        metadata = archive_metadata(name, version)
        archive_bytes = fetch(metadata["archive_url"])
        archive_sha256 = verify_archive(archive_bytes, metadata, known_archives)
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            members = [entry for entry in archive.getmembers() if entry.name == member]
            if len(members) != 1 or not members[0].isfile():
                raise ValueError("Unexpected template archive member")
            if archive.extractfile(members[0]).read() != content:
                raise ValueError("Installed template key differs from the official archive")
        target.unlink()
        print(f"Removed verified {name} {version} {member}; archive SHA-256 {archive_sha256}")


def sanitize(cache):
    for asset in ASSETS:
        sanitize_package(cache, *asset)


def sanitize_preload(root):
    for name, member, size, sha256, known_archives in ASSETS:
        for target in sorted(root.glob(f"{name}-*.tar.gz")):
            if target.resolve() != target.absolute() or not target.is_file():
                raise ValueError("Unexpected preload archive path")
            version = target.name.removeprefix(f"{name}-").removesuffix(".tar.gz")
            metadata = archive_metadata(name, version)
            archive_bytes = target.read_bytes()
            archive_sha256 = verify_archive(archive_bytes, metadata, known_archives)
            with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
                members = [entry for entry in archive.getmembers() if entry.name == member]
                # A later upstream version may have removed the signing fixture.
                if not members:
                    continue
                if len(members) != 1 or not members[0].isfile():
                    raise ValueError("Unexpected preload signing fixture member")
                content = archive.extractfile(members[0]).read()
                if len(content) != size or hashlib.sha256(content).hexdigest() != sha256:
                    raise ValueError("Unexpected preload signing fixture content")
            # Delete the complete original archive; never rewrite a Pub package identity.
            target.unlink()
            print(f"Removed verified preload archive {target.name}; SHA-256 {archive_sha256}")


if __name__ == "__main__":
    sanitize(Path(os.environ["PUB_CACHE"]))
    sanitize_preload(Path("/opt/flutter/.pub-preload-cache"))
