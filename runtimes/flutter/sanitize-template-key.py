"""Remove only the verified upstream Windows UWP template signing key."""

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


def fetch(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def sanitize(cache):
    for package in sorted((cache / "hosted/pub.dev").glob(f"{PACKAGE}-*")):
        target = package / MEMBER
        if not target.exists() and not target.is_symlink():
            continue
        # Never follow a substituted path or remove an unrelated signing bundle.
        if target.resolve() != target.absolute() or not target.is_file():
            raise ValueError("Unexpected template key path")
        content = target.read_bytes()
        if len(content) != 2560 or hashlib.sha256(content).hexdigest() != KEY_SHA256:
            raise ValueError("Unexpected template key content")
        version = package.name.removeprefix(f"{PACKAGE}-")
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version):
            raise ValueError("Unexpected template package version")
        metadata = json.loads(fetch(f"https://pub.dev/api/packages/{PACKAGE}/versions/{version}"))
        archive_url = f"https://pub.dev/api/archives/{PACKAGE}-{version}.tar.gz"
        if (
            metadata["version"] != version
            or metadata["pubspec"]["name"] != PACKAGE
            or metadata["archive_url"] != archive_url
        ):
            raise ValueError("Unexpected template package provenance")
        archive_bytes = fetch(archive_url)
        archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()
        if archive_sha256 != metadata["archive_sha256"]:
            raise ValueError("Template archive checksum mismatch")
        if version == "5.0.0" and archive_sha256 != ARCHIVE_5_SHA256:
            raise ValueError("Known template archive changed")
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            members = [member for member in archive.getmembers() if member.name == MEMBER]
            if len(members) != 1 or not members[0].isfile():
                raise ValueError("Unexpected template archive member")
            if archive.extractfile(members[0]).read() != content:
                raise ValueError("Installed template key differs from the official archive")
        target.unlink()
        print(f"Removed verified {PACKAGE} {version} Windows UWP template key; archive SHA-256 {archive_sha256}")


if __name__ == "__main__":
    sanitize(Path(os.environ["PUB_CACHE"]))
