"""Local-only candidate qualification. Never pulls, tags, logs in, or publishes."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid


HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[2]
PRODUCTION_PATHS = ("runtimes/flutter", ".github/workflows/flutter-runtimes.yml")
UID = "12345:23456"
CASES = {
    "lightweight": ["lightweight"],
    "full": ["defaults", "sdk34", "sdk35", "sdk36"],
}


def docker(*args, timeout=120):
    return subprocess.check_output(["docker", *args], text=True, timeout=timeout)


def check_production_lineage(source, revision):
    """Reuse only an ancestor's identical production Git objects and file modes."""
    if not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{40}", source):
        raise ValueError("Image source revision must be a full commit SHA")
    subprocess.run(["git", "merge-base", "--is-ancestor", source, revision],
                   cwd=REPOSITORY, check=True, capture_output=True, text=True)

    def production_tree(commit):
        tree = subprocess.check_output(
            ["git", "ls-tree", "-r", "-z", commit, "--", *PRODUCTION_PATHS],
            cwd=REPOSITORY, text=True)
        entries = sorted(entry for entry in tree.split("\0") if entry
                         and not entry.split("\t", 1)[1].startswith("runtimes/flutter/validation/"))
        if not any(entry.endswith("\truntimes/flutter/Dockerfile") for entry in entries):
            raise ValueError("Missing runtime production tree")
        return entries

    source_tree = production_tree(source)
    validation_tree = production_tree(revision)
    if source_tree != validation_tree:
        raise ValueError("Image source and validation checkpoint have different runtime production trees")
    return {"image_source_revision": source, "validation_revision": revision,
            "ancestor_verified": True, "production_paths": PRODUCTION_PATHS,
            "excluded_path": "runtimes/flutter/validation/",
            "production_tree_sha256": hashlib.sha256("\0".join(source_tree).encode()).hexdigest(),
            "production_git_entries": source_tree}


def check_image(image, revision):
    if image["Os"] != "linux" or image["Architecture"] != "amd64":
        raise ValueError("Candidates must be Linux AMD64")
    labels = image["Config"].get("Labels") or {}
    if labels.get("org.opencontainers.image.revision") != revision:
        raise ValueError("Candidate source revision does not match the clean checkpoint")
    if not labels.get("io.commons.flutter.publication"):
        raise ValueError("Missing publication identity")
    if image["Config"].get("User") != "10001:10001":
        raise ValueError("Unexpected default execution identity")
    for entry in image["Config"].get("Env", []):
        name, _, value = entry.partition("=")
        if value and re.search(r"TOKEN|PASSWORD|SECRET|CREDENTIAL|PRIVATE_KEY", name, re.I):
            raise ValueError(f"Potential credential environment variable: {name}")


def check_pair(light, full, required):
    if light["variant"] != "lightweight" or full["variant"] != "full":
        raise ValueError("Wrong candidate variants")
    if light["selection"] != full["selection"]:
        raise ValueError("Candidates have different resolved selections")
    for key in ("frameworkVersion", "frameworkRevision", "dartSdkVersion", "engineRevision"):
        if not light["flutter"].get(key) or light["flutter"][key] != full["flutter"].get(key):
            raise ValueError(f"Candidate pair mismatch: {key}")
    selected = light["selection"]["flutter"]
    if (light["flutter"]["frameworkRevision"] != selected["hash"]
            or light["flutter"]["frameworkVersion"] != selected["version"]):
        raise ValueError("Actual Flutter differs from resolved release")
    expected = set(required) | set(full["selection"]["android_packages"])
    missing = expected - full.get("android", {}).keys()
    if missing:
        raise ValueError(f"Missing supported Android packages: {sorted(missing)}")
    if not re.search(r'version "21(?:\.|\")', full.get("java", "")):
        raise ValueError("JDK 21 is required")


def run_container(image, case, destination, containers, volumes):
    name = "commons-flutter-check-" + uuid.uuid4().hex
    mounts = []
    locations = () if case == "audit" else (
        ("workspace", "/workspace"), ("home", "/home/runtime"),
        ("pub", "/cache/pub"), ("gradle", "/cache/gradle"))
    for slot, path in locations:
        volume = name + "-" + slot
        docker("volume", "create", volume)
        volumes.append(volume)
        mounts += ["--mount", f"type=volume,src={volume},dst={path},volume-nocopy"]
    # Empty volumes otherwise default to root-only write access. This offline,
    # root-only preparation never touches a host path, SDK, or candidate image.
    if locations:
        initializer = name + "-mounts"
        docker("create", "--name", initializer, "--user", "0:0", "--network", "none",
               "--pull", "never", *mounts, "--entrypoint", "chmod", image, "0777",
               "/workspace", "/home/runtime", "/cache/pub", "/cache/gradle")
        containers.append(initializer)
        docker("start", initializer)
        if docker("wait", initializer).strip() != "0":
            raise RuntimeError("Could not prepare writable cold cache volumes")
    user = "0:0" if case == "audit" else UID
    args = ["create", "--name", name, "--platform", "linux/amd64", "--user", user,
            "--pull", "never", *mounts]
    if case == "audit":
        args += ["--network", "none"]
    args += ["--entrypoint", "python3", image, "/tmp/validation/worker.py", case]
    docker(*args)
    containers.append(name)
    docker("cp", str(HERE), f"{name}:/tmp/validation")
    destination.mkdir(parents=True)
    start = time.time()
    try:
        with (destination / "container.log").open("w") as output:
            result = subprocess.run(["docker", "start", "--attach", name], stdout=output,
                                    stderr=subprocess.STDOUT, timeout=2700)
        state = json.loads(docker("inspect", name))[0]["State"]
        if result.returncode or state["ExitCode"]:
            raise RuntimeError(f"{case} failed; see {destination}/container.log")
    finally:
        # Stop on timeout before copying partial evidence. No candidate image is removed.
        docker("stop", "--time", "10", name)
        docker("cp", f"{name}:/workspace/evidence/.", str(destination))
        (destination / "container.json").write_text(json.dumps({
            "image_id": image, "case": case, "uid_gid": user,
            "mounts": mounts, "cold_project_caches": case != "audit",
            "start_epoch": start, "elapsed_seconds": time.time() - start,
        }, indent=2) + "\n")
    report = json.loads((destination / "result.json").read_text())
    if report.get("status") != "passed":
        raise ValueError(f"Incomplete qualification: {case}")
    (destination / "startup.json").write_text(json.dumps({
        "seconds_to_worker_start": report["worker_started_epoch"] - start,
        "includes": "Docker start and Python startup; image already local",
    }, indent=2) + "\n")
    return report


def validate(refs, evidence):
    evidence.mkdir(parents=True, exist_ok=True)
    root = evidence / ("validation-" + uuid.uuid4().hex)
    root.mkdir()
    containers, volumes, images = [], [], {}
    summary = {"status": "failed", "started_epoch": time.time(), "cases": CASES,
               "execution_uid_gid": UID, "pull": "not performed; local candidates required",
               "build_timing": "supplied separately by image builder",
               "promotion": "not performed; registry failure/recovery evidence is an operator gate"}
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
            raise ValueError("Qualification requires a clean immutable checkpoint")
        summary["validation_revision"] = revision
        summary["workload_sha256"] = {
            str(path.relative_to(HERE)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(HERE.rglob("*")) if path.is_file() and "__pycache__" not in path.parts
        }
        for variant, ref in zip(CASES, refs):
            image = json.loads(docker("image", "inspect", ref))[0]
            images[ref] = image["Id"]
            source = (image["Config"].get("Labels") or {}).get("org.opencontainers.image.revision")
            lineage = check_production_lineage(source, revision)
            check_image(image, source)
            summary[variant] = {"ref": ref, "id": image["Id"], "digests": image.get("RepoDigests", []),
                                "labels": image["Config"]["Labels"], "lineage": lineage}
        if len(set(images.values())) != 2:
            raise ValueError("Expected two distinct candidate images")
        if (summary["lightweight"]["labels"]["io.commons.flutter.publication"]
                != summary["full"]["labels"]["io.commons.flutter.publication"]):
            raise ValueError("Different publication identities")
        if (summary["lightweight"]["lineage"]["image_source_revision"]
                != summary["full"]["lineage"]["image_source_revision"]):
            raise ValueError("Different image source revisions")
        summary["source_revision"] = summary["lightweight"]["lineage"]["image_source_revision"]
        audits = {}
        for variant in CASES:
            audits[variant] = run_container(summary[variant]["id"], "audit", root / variant / "audit",
                                            containers, volumes)["metadata"]
        required = (HERE.parent / "android-packages.txt").read_text().splitlines()
        check_pair(audits["lightweight"], audits["full"], required)
        for variant, cases in CASES.items():
            for case in cases:
                run_container(summary[variant]["id"], case, root / variant / case, containers, volumes)
        summary["status"] = "passed"
    except BaseException as error:
        summary["error"] = str(error)
        raise
    finally:
        errors = []
        for container in reversed(containers):
            try:
                docker("rm", "--force", container)
            except Exception as error:
                errors.append(str(error))
        for volume in reversed(volumes):
            try:
                docker("volume", "rm", volume)
            except Exception as error:
                errors.append(str(error))
        for ref, identity in images.items():
            try:
                if json.loads(docker("image", "inspect", ref))[0]["Id"] != identity:
                    errors.append(f"Candidate reference changed during qualification: {ref}")
            except Exception as error:
                errors.append(str(error))
        summary["cleanup_errors"] = errors
        summary["elapsed_seconds"] = time.time() - summary["started_epoch"]
        if errors:
            summary["status"] = "failed"
        (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(f"Validation evidence: {root}", flush=True)
        if errors:
            raise RuntimeError("Cleanup or reference preservation failed: " + "; ".join(errors))


def interrupted(signum, _frame):
    raise KeyboardInterrupt(f"Interrupted by signal {signum}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lightweight")
    parser.add_argument("full")
    parser.add_argument("evidence", type=Path)
    arguments = parser.parse_args()
    signal.signal(signal.SIGTERM, interrupted)
    validate([arguments.lightweight, arguments.full], arguments.evidence.resolve())
