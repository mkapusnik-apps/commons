"""Credential-free, real workload qualification inside one disposable candidate."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zipfile


EVIDENCE = Path("/workspace/evidence")
PROJECT = Path("/workspace/project")
METADATA = Path("/usr/local/share/flutter-runtime")
FIXTURES = Path(__file__).with_name("fixtures")
MATRIX = {
    "sdk34": {"sdk": 34, "build_tools": "35.0.0", "agp": "8.11.1", "gradle": "8.14",
              "kind": "apk", "mode": "debug", "target": "android-arm64"},
    "sdk35": {"sdk": 35, "build_tools": "35.0.0", "agp": "8.13.2", "gradle": "9.4.1",
              "kind": "apk", "mode": "release", "target": "android-x64"},
    "sdk36": {"sdk": 36, "build_tools": "36.0.0", "agp": "8.13.2", "gradle": "9.4.1",
              "kind": "appbundle", "mode": "release", "target": "android-arm,android-arm64,android-x64"},
}


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def classify_downloads(text):
    """Report dependency activity separately; fail recognizable tool acquisition."""
    tool, dependency = [], []
    tool_url = re.compile(
        r"https?://(?:dl\.google\.com/android/repository/|"
        r"storage\.googleapis\.com/(?:flutter_infra_release/|(?:[^/\s]+/)?download\.flutter\.io/))", re.I)
    operation = re.compile(
        r"^(?:Downloading|Downloaded|Download|Fetching|Installing|Installed|Install|"
        r"Preparing|Unzipping|Checking the license for|HTTP (?:GET|HEAD))\b", re.I)
    tooling = re.compile(
        r"\b(?:android-(?:arm|x64|x86)[\w-]*|linux-x64[\w-]*|Dart SDK|Flutter SDK|"
        r"flutter_patched_sdk\w*|Flutter tools|Material fonts|Gradle Wrapper|"
        r"Android SDK|SDK Platforms?|platform-tools|build[- ]tools|NDK|CMake)\b|"
        r"\bplatforms;android-\d+", re.I)
    for line in text.splitlines():
        # Flutter/Gradle timestamps and Pub/CMake log prefixes are not events.
        message = re.sub(r"^(?:\s*\[[^\]\r\n]*\]\s*)+", "", line).strip()
        message = re.sub(r"^(?:IO|MSG|C/C\+\+)\s*:\s*", "", message)
        event = operation.match(message)
        # Match package descriptions outside URLs/paths. Kotlin Maven coordinates
        # named kotlin-build-tools-* are project dependencies, not Android tools.
        description = re.sub(r"(?:https?|file)://\S+|(?<!\S)/\S+", " ", message)
        if ((event and (tool_url.search(message) or tooling.search(description)))
                or tool_url.match(message)):
            tool.append(line)
        elif (event and re.search(r"https?://", message)) or re.match(
                r"^(?:Resolving dependencies|Got dependencies|Downloading packages|"
                r"Get versions from https?://)", message, re.I):
            dependency.append(line)
    return {"toolchain": tool, "project_dependencies": dependency}


def snapshot(full):
    roots = [Path("/opt/flutter/bin/cache/artifacts"), Path("/opt/flutter/bin/cache/dart-sdk")]
    if full:
        roots += [Path("/opt/android-sdk"), Path("/opt/flutter-storage")]
    result = {}
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"Missing preloaded tool directory: {root}")
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            # Android records repository bookkeeping, not tools, in root dotfiles.
            if root.name == "android-sdk" and relative.parts[0].startswith("."):
                continue
            if path.is_file():
                result[str(path)] = digest(path)
    return result


def compare_snapshots(before, after):
    changed = sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
    if changed:
        raise ValueError(f"Preloaded toolchain changed during workload: {changed[:30]}")


def run(command, report, phase, cwd=PROJECT):
    started = time.monotonic()
    print(f"Running {phase}: {' '.join(command)}", flush=True)
    number = len(report["commands"])
    log = EVIDENCE / f"{number:02d}-{phase}.log"
    with log.open("w") as output:
        result = subprocess.run(command, cwd=cwd, text=True, stdout=output,
                                stderr=subprocess.STDOUT, timeout=1800)
    text = log.read_text(errors="replace")
    downloads = classify_downloads(text)
    report["commands"].append({"command": command, "phase": phase, "log": log.name,
                               "seconds": time.monotonic() - started, "exit_code": result.returncode,
                               "downloads": downloads})
    if result.returncode:
        raise RuntimeError(f"{phase} exited {result.returncode}; see {log}")
    if downloads["toolchain"]:
        raise ValueError(f"Runtime toolchain acquisition detected in {phase}")
    return text


def audit(report):
    metadata = json.loads((METADATA / "toolchain.json").read_text())
    report["metadata"] = metadata
    # Inspect pristine images, not the synthetic projects or their debug signing keys.
    findings = []
    for root in (Path("/root"), Path("/home"), Path("/cache"), Path("/workspace"), Path("/tmp")):
        for path in root.rglob("*"):
            if path.name in {".git-credentials", "credentials", "credentials.json", ".netrc", "id_rsa",
                             "id_ed25519", "key.properties", "google-services.json", ".npmrc"}:
                findings.append(str(path))
            if path.is_file() and path.suffix in {".jks", ".keystore", ".p12", ".pfx"}:
                findings.append(str(path))
    if any(Path("/workspace").glob("*")) and set(Path("/workspace").iterdir()) != {EVIDENCE}:
        findings.append("Unexpected project state under /workspace")
    if findings:
        raise ValueError(f"Potential embedded credential/project files: {findings}")
    report["content_assessment"] = {
        "credential_filename_findings": findings,
        "scope": "pristine root/home/cache/workspace/tmp; image environment checked by host",
        "limitation": "targeted assessment, not an exhaustive secret scan of every image layer",
    }


def template_kotlin_version(settings):
    versions = re.findall(
        r'id\(\s*"org\.jetbrains\.kotlin\.android"\s*\)\s+version\s+"(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)"',
        settings)
    if len(versions) != 1:
        raise ValueError("Expected one literal Kotlin version in the selected Flutter template")
    return versions[0]


def configure_android(case):
    android = PROJECT / "android"
    kotlin_version = template_kotlin_version((android / "settings.gradle.kts").read_text())
    properties = android / "gradle.properties"
    with properties.open("a") as output:
        output.write("\nandroid.builder.sdkDownload=false\norg.gradle.daemon=false\n")
    app = android / "app/build.gradle.kts"
    if not app.exists():
        raise ValueError("Flutter Android Kotlin template changed; update the workload explicitly")
    if case != "defaults":
        config = MATRIX[case]
        settings = ((FIXTURES / "settings.gradle.kts").read_text()
                    .replace("@AGP@", config["agp"]).replace("@KOTLIN@", kotlin_version))
        (android / "settings.gradle.kts").write_text(settings)
        text = (FIXTURES / "build.gradle.kts").read_text()
        for name, value in (("SDK", config["sdk"]), ("BUILD_TOOLS", config["build_tools"])):
            text = text.replace(f"@{name}@", str(value))
        app.write_text(text)
        wrapper = android / "gradle/wrapper/gradle-wrapper.properties"
        wrapper.write_text("distributionBase=GRADLE_USER_HOME\ndistributionPath=wrapper/dists\n"
                           "zipStoreBase=GRADLE_USER_HOME\nzipStorePath=wrapper/dists\n"
                           f"distributionUrl=https\\://services.gradle.org/distributions/gradle-{config['gradle']}-bin.zip\n")
    else:
        text = app.read_text()
        if text.count("android {") != 1:
            raise ValueError("Unexpected Flutter Android template")
        app.write_text(text.replace("android {", """android {
    externalNativeBuild {
        cmake { path = file("src/main/cpp/CMakeLists.txt"); version = "3.22.1" }
    }
""", 1))
    native = android / "app/src/main/cpp"
    native.mkdir(parents=True)
    (native / "CMakeLists.txt").write_text(
        'cmake_minimum_required(VERSION 3.22.1)\nproject(readiness C)\nadd_library(readiness SHARED readiness.c)\n')
    (native / "readiness.c").write_text("int readiness(void) { return 42; }\n")
    return kotlin_version


def check_archive(path, abis):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        for abi in abis:
            for library in ("libflutter.so", "libreadiness.so"):
                if not any(name.endswith(f"lib/{abi}/{library}") for name in names):
                    raise ValueError(f"Missing {abi}/{library} in {path}")


def workload(case, report):
    if os.getuid() != 12345 or os.getgid() != 23456:
        raise ValueError("Workloads must run as the arbitrary non-default UID/GID")
    metadata = json.loads((METADATA / "toolchain.json").read_text())
    full = metadata["variant"] == "full"
    report["metadata"] = metadata
    for path in ("/workspace", "/home/runtime", "/cache/pub", "/cache/gradle", "/opt/flutter"):
        marker = Path(path) / ".qualification-writable"
        marker.write_text("probe")
        marker.unlink()
    for cache in ("/cache/pub", "/cache/gradle"):
        if any(Path(cache).iterdir()):
            raise ValueError(f"Project cache is not cold: {cache}")
    if full:
        marker = Path("/opt/android-sdk/.qualification-writable")
        marker.write_text("probe")
        marker.unlink()
        if os.environ.get("FLUTTER_STORAGE_BASE_URL") != "file:///opt/flutter-storage":
            raise ValueError("Full workload must use the image's file-backed engine repository")
        inventory = json.loads((METADATA / "engine-maven.json").read_text())
        for relative, expected in inventory.items():
            if digest(Path("/opt/flutter-storage") / relative) != expected:
                raise ValueError(f"Engine cache checksum mismatch: {relative}")
        if not any("x86_64_release" in key and key.endswith(".jar") for key in inventory):
            raise ValueError("Missing x86_64 release engine cache")
    else:
        if Path("/opt/android-sdk").exists() or shutil.which("sdkmanager"):
            raise ValueError("Lightweight unexpectedly contains Android SDK")
        # Fail closed if Flutter tries to fetch an absent SDK artifact. Pub remains online.
        os.environ["FLUTTER_STORAGE_BASE_URL"] = "http://127.0.0.1:9"
    report["tool_download_controls"] = {
        "flutter_storage": os.environ["FLUTTER_STORAGE_BASE_URL"],
        "android_sdk_download": "disabled in synthetic Gradle project",
        "tool_snapshot": "SHA-256 of preloaded Dart/Flutter artifacts, Android SDK and local engine repository",
        "project_dependencies": "Pub/Maven/Gradle remain network-enabled and are logged separately",
    }
    before = snapshot(full)
    (EVIDENCE / "toolchain-before.json").write_text(json.dumps(before, indent=2))
    try:
        actual = json.loads(run(["flutter", "--version", "--machine"], report, "version", cwd="/workspace"))
        for key in ("frameworkVersion", "frameworkRevision", "dartSdkVersion", "engineRevision"):
            if actual[key] != metadata["flutter"][key]:
                raise ValueError(f"Live tooling disagrees with metadata: {key}")
        run(["flutter", "create", "--no-pub", "--platforms=android", "--project-name=runtime_probe",
             "--org=org.commons.qualification", str(PROJECT)], report, "create", cwd="/workspace")
        for directory in (PROJECT / "lib", PROJECT / "test"):
            shutil.rmtree(directory)
        for name in ("lib", "test"):
            shutil.copytree(FIXTURES / name, PROJECT / name)
        shutil.copyfile(FIXTURES / "pubspec.yaml", PROJECT / "pubspec.yaml")
        run(["flutter", "pub", "get", "--verbose"], report, "pub-dependencies")
        run(["dart", "run", "build_runner", "build", "--delete-conflicting-outputs"], report, "code-generation")
        if not (PROJECT / "lib/model.g.dart").is_file():
            raise ValueError("Code generation did not produce the expected serializer")
        run(["dart", "format", "lib", "test"], report, "format")
        run(["dart", "format", "--output=none", "--set-exit-if-changed", "lib", "test"], report, "format-check")
        run(["flutter", "analyze", "--no-pub"], report, "analysis")
        run(["flutter", "test", "--no-pub", "--reporter=expanded"], report, "unit-widget")
        shutil.copyfile(PROJECT / "pubspec.lock", EVIDENCE / "pubspec.lock")
        if full:
            java = run(["java", "-version"], report, "java")
            if not re.search(r'version "21(?:\.|\")', java):
                raise ValueError("Wrong live JDK")
            report["kotlin_template_version"] = configure_android(case)
            # Preserve the exact synthetic workload/tool configuration, not private source.
            for relative in ("app/build.gradle.kts", "settings.gradle.kts", "gradle.properties",
                             "gradle/wrapper/gradle-wrapper.properties"):
                destination = EVIDENCE / "android" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(PROJECT / "android" / relative, destination)
            config = MATRIX.get(case, {"kind": "appbundle", "mode": "release",
                                      "target": "android-arm,android-arm64,android-x64"})
            report["android_workload"] = config
            run(["flutter", "build", config["kind"], "--" + config["mode"], "--no-pub",
                 "--target-platform=" + config["target"], "--verbose"], report, "android-build")
            suffix = ".apk" if config["kind"] == "apk" else ".aab"
            artifacts = sorted((PROJECT / "build/app/outputs").rglob("*" + suffix))
            if not artifacts:
                raise ValueError("Android build produced no artifact")
            abis = [{"android-arm": "armeabi-v7a", "android-arm64": "arm64-v8a", "android-x64": "x86_64"}[a]
                    for a in config["target"].split(",")]
            report["artifacts"] = []
            for path in artifacts:
                check_archive(path, abis)
                report["artifacts"].append({"path": str(path.relative_to(PROJECT)), "sha256": digest(path),
                                            "bytes": path.stat().st_size, "abis": abis})
    finally:
        after = snapshot(full)
        (EVIDENCE / "toolchain-after.json").write_text(json.dumps(after, indent=2))
        compare_snapshots(before, after)


def main(case):
    EVIDENCE.mkdir(parents=True)
    report = {"status": "failed", "case": case, "uid": os.getuid(), "gid": os.getgid(),
              "worker_started_epoch": time.time(), "commands": []}
    started = time.monotonic()
    try:
        if case == "audit":
            audit(report)
        else:
            workload(case, report)
        report["status"] = "passed"
    except BaseException as error:
        report["error"] = str(error)
        raise
    finally:
        report["seconds"] = time.monotonic() - started
        (EVIDENCE / "result.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
