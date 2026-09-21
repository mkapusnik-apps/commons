"""Record actual image tooling, not only requested versions."""

import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


root = Path("/usr/local/share/flutter-runtime")
selection = json.loads((root / "resolved.json").read_text())
version = json.loads(subprocess.check_output(["flutter", "--version", "--machine"], text=True))
if version["frameworkRevision"] != selection["flutter"]["hash"]:
    raise ValueError("Installed Flutter revision differs from the resolved release")
if version["frameworkVersion"] != selection["flutter"]["version"]:
    raise ValueError("Installed Flutter version differs from the resolved release")
metadata = {"variant": sys.argv[1], "selection": selection, "flutter": version}
if sys.argv[1] == "full":
    metadata["java"] = subprocess.check_output(["java", "-version"], stderr=subprocess.STDOUT, text=True)
    metadata["android"] = {}
    for path in sorted(Path("/opt/android-sdk").rglob("package.xml")):
        package = ET.parse(path).getroot().find("localPackage")
        if package is not None:
            metadata["android"][package.get("path")] = {
                child.tag: child.text for child in package.find("revision")
            }
    missing = set(selection["android_packages"]) - metadata["android"].keys()
    if missing:
        raise ValueError(f"Missing Android packages: {sorted(missing)}")
(root / "toolchain.json").write_text(json.dumps(metadata, indent=2) + "\n")
subprocess.run(
    ["dpkg-query", "-W", "-f=${Package}\t${Version}\n"],
    stdout=(root / "os-packages.txt").open("w"), check=True,
)
