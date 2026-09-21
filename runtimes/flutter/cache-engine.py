"""Cache the official Android engine Maven repository for the installed SDK."""

import hashlib
import json
from pathlib import Path
import shutil
import urllib.request


cache = Path("/opt/flutter/bin/cache")
version = "1.0.0-" + (cache / "engine.stamp").read_text().strip()
realm = (cache / "engine.realm").read_text().strip()
repository = (realm + "/" if realm else "") + "download.flutter.io"
root = Path("/opt/flutter-storage")
inventory = {}
for mode in ("debug", "profile", "release"):
    for component in ("flutter_embedding", "armeabi_v7a", "arm64_v8a", "x86_64"):
        artifact = f"{component}_{mode}"
        for extension in ("pom", "jar"):
            relative = f"{repository}/io/flutter/{artifact}/{version}/{artifact}-{version}.{extension}"
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen("https://storage.googleapis.com/" + relative, timeout=120) as response:
                with destination.open("wb") as output:
                    shutil.copyfileobj(response, output)
            with destination.open("rb") as content:
                inventory[relative] = hashlib.file_digest(content, "sha256").hexdigest()
Path("/usr/local/share/flutter-runtime/engine-maven.json").write_text(
    json.dumps(inventory, indent=2) + "\n"
)
