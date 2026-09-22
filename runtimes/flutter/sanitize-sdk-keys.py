"""Remove exact, verified signing fixtures outside Linux/Android workloads."""

import hashlib
import json
from pathlib import Path
import sys
import urllib.request


CMAKE_KEY_SHA256 = "a957fb8c8a3e3e7b1b8d2c58e97e02759b61cd7cbecca409c0763c8d6d9691f4"
FLUTTER_FIXTURES = (
    ("engine/src/flutter/testing/android/native_activity/debug.keystore", 2618,
     "ac4dfce349d2f7c1290b1824cb9fa57084853530a1199d9994a3cf4d3f1ba786"),
    ("packages/flutter_tools/test/data/asset_test/tls_cert/dummy-key.pem", 887,
     "db69c05eb4e8c5a798b606b7b87716f18c37a899e7fa87a6dafa0825fe9785d0"),
    ("examples/image_list/lib/main.dart", 8172,
     "1f163b851b6b4fdd41dfc35e5cd375de2a9a713a9b67cc5e6e1227a8c5796466"),
)


def remove_verified(target, size, sha256, source):
    if not target.exists() and not target.is_symlink():
        return
    if target.resolve() != target.absolute() or not target.is_file():
        raise ValueError(f"Unexpected signing fixture path: {target}")
    content = target.read_bytes()
    if len(content) != size or hashlib.sha256(content).hexdigest() != sha256:
        raise ValueError(f"Unexpected signing fixture content: {target}")
    with urllib.request.urlopen(source, timeout=120) as response:
        if response.read() != content:
            raise ValueError(f"Signing fixture differs from official upstream: {target}")
    target.unlink()
    print(f"Removed verified signing fixture {target}; SHA-256 {sha256}; source {source}")


def sanitize(stage):
    if stage == "system":
        targets = Path("/usr/share").glob("cmake-*/Templates/Windows/Windows_TemporaryKey.pfx")
        source = "https://raw.githubusercontent.com/Kitware/CMake/v3.28.3/Templates/Windows/Windows_TemporaryKey.pfx"
        for target in sorted(targets):
            remove_verified(target, 2560, CMAKE_KEY_SHA256, source)
    elif stage == "android":
        targets = Path("/opt/android-sdk/cmake").glob("*/share/cmake-*/Templates/Windows/Windows_TemporaryKey.pfx")
        source = "https://raw.githubusercontent.com/Kitware/CMake/v3.22.1/Templates/Windows/Windows_TemporaryKey.pfx"
        for target in sorted(targets):
            remove_verified(target, 2560, CMAKE_KEY_SHA256, source)
    elif stage == "flutter":
        selection = json.loads(Path("/usr/local/share/flutter-runtime/resolved.json").read_text())
        revision = selection["flutter"]["hash"]
        for relative, size, sha256 in FLUTTER_FIXTURES:
            source = f"https://raw.githubusercontent.com/flutter/flutter/{revision}/{relative}"
            remove_verified(Path("/opt/flutter") / relative, size, sha256, source)
    else:
        raise ValueError(f"Unknown sanitation stage: {stage}")


if __name__ == "__main__":
    sanitize(sys.argv[1])
