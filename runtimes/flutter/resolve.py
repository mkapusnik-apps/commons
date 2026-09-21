"""Resolve one official stable Flutter/Android selection for both image targets."""

import json
from pathlib import Path
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def resolve(base_image):
    index_url = "https://storage.googleapis.com/flutter_infra_release/releases/releases_linux.json"
    index = json.loads(fetch(index_url))
    release = next(
        item for item in index["releases"]
        if item["hash"] == index["current_release"]["stable"]
        and item["channel"] == "stable"
        and item.get("dart_sdk_arch", "x64") == "x64"
    )
    extension_url = (
        "https://raw.githubusercontent.com/flutter/flutter/"
        + release["hash"]
        + "/packages/flutter_tools/gradle/src/main/kotlin/FlutterExtension.kt"
    )
    extension = fetch(extension_url).decode()
    compile_sdk = re.search(r"val compileSdkVersion: Int = (\d+)", extension).group(1)
    ndk = re.search(r'val ndkVersion: String = "([^"]+)"', extension).group(1)
    packages = Path(__file__).with_name("android-packages.txt").read_text().splitlines()
    packages = sorted(set(packages + [f"platforms;android-{compile_sdk}", f"ndk;{ndk}"]))

    repository_url = "https://dl.google.com/android/repository/repository2-1.xml"
    repository = ET.fromstring(fetch(repository_url))
    tools = next(
        item for item in repository.findall("remotePackage")
        if item.get("path") == "cmdline-tools;latest"
        and item.find("channelRef").get("ref") == "channel-0"
    )
    archive = next(
        item.find("complete") for item in tools.findall("archives/archive")
        if item.findtext("host-os") == "linux"
    )
    return {
        "base_image": base_image,
        "platform": "linux/amd64",
        "flutter_index": index_url,
        "flutter": release,
        "flutter_archive_url": index["base_url"] + "/" + release["archive"],
        "flutter_android_defaults_source": extension_url,
        "android_repository": repository_url,
        "android_command_line_tools_url": "https://dl.google.com/android/repository/" + archive.findtext("url"),
        "android_command_line_tools_sha1": archive.findtext("checksum"),
        "android_packages": packages,
        "java_major": 21,
    }


if __name__ == "__main__":
    print(json.dumps(resolve(sys.argv[1]), indent=2))
