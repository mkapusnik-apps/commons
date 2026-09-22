"""Keep genuine release metadata without retaining Flutter's source blob history."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path("/opt/flutter")
ORIGIN = "https://github.com/flutter/flutter.git"


def git(*arguments):
    return subprocess.check_output(["git", "-C", str(ROOT), *arguments], text=True).strip()


def prepare():
    selection = json.loads(Path("/usr/local/share/flutter-runtime/resolved.json").read_text())
    revision = selection["flutter"]["hash"]
    version = selection["flutter"]["version"]
    # Remove the original packs, refs, reflogs, and index in the extraction layer.
    # A shallow clone with ordinary blobs would still retain HEAD's signing fixtures.
    shutil.rmtree(ROOT / ".git")
    with tempfile.TemporaryDirectory(prefix="flutter-release-git-") as temporary:
        clone = Path(temporary) / "release"
        subprocess.run(
            ["git", "clone", "--filter=blob:none", "--no-checkout", "--depth=1",
             "--single-branch", "--branch", version, "--", ORIGIN, str(clone)],
            check=True,
        )
        shutil.move(str(clone / ".git"), ROOT / ".git")

    # Git 2.43 supports these policies. They also block promisor lazy retrieval.
    # Keep this local to the SDK; consumer repositories and Pub Git deps are unaffected.
    git("config", "--local", "protocol.allow", "never")
    git("config", "--local", "protocol.https.allow", "never")
    if git("rev-parse", "HEAD") != revision or git("rev-parse", f"refs/tags/{version}^{{commit}}") != revision:
        raise ValueError("Flutter release tag does not identify the resolved revision")
    if git("rev-parse", "--is-shallow-repository") != "true":
        raise ValueError("Flutter release metadata is not shallow")
    # Enumerate local objects, including unreachable ones, without requesting missing blobs.
    objects = git("cat-file", "--batch-all-objects", "--batch-check=%(objecttype)")
    if "blob" in objects.splitlines():
        raise ValueError("Filtered Flutter metadata unexpectedly retains Git blobs")

    git("update-ref", "refs/heads/stable", revision)
    git("update-ref", "refs/remotes/origin/stable", revision)
    git("symbolic-ref", "HEAD", "refs/heads/stable")
    git("config", "--local", "remote.origin.fetch", "+refs/heads/stable:refs/remotes/origin/stable")
    git("config", "--local", "branch.stable.remote", "origin")
    git("config", "--local", "branch.stable.merge", "refs/heads/stable")
    # No checkout or update-index refresh: read-tree needs only the retained trees.
    git("read-tree", "HEAD")
    print(f"Prepared shallow blobless Flutter metadata: stable {version} {revision}; SDK Git transports disabled")


if __name__ == "__main__":
    prepare()
