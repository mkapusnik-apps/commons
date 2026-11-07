"""Local Git context, session isolation, and output validation for the action."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid


def git(*args, check=True):
    return subprocess.run(
        ["git", *args], check=check, capture_output=True, text=True
    )


def output(name, value):
    delimiter = f"notes_{uuid.uuid4().hex}"
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
        stream.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")


def positive(name):
    value = int(os.environ[name])
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def commit(sha):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Commit inputs must be full SHA-1 commit IDs")
    return git("rev-parse", "--verify", f"{sha}^{{commit}}").stdout.strip()


def validate(text, limit):
    text = text.strip()
    if not text or len(text) > limit:
        raise ValueError("Release notes must be non-empty and within the character limit")
    if "```" in text or re.search(
        r"(?im)^\s*#{0,6}\s*(summary|verification|test results)\s*:?\s*$", text
    ):
        raise ValueError("Release notes must not contain code fences or task-report headings")
    if any(ord(char) < 32 and char not in "\n\t" for char in text):
        raise ValueError("Release notes contain unsupported control characters")
    return text


def context():
    limit = positive("MAX_CHARACTERS")
    max_commits, max_files = positive("MAX_COMMITS"), positive("MAX_FILES")
    validate(os.environ["EMPTY_MESSAGE"], limit)
    for name in ("AUDIENCE", "LANGUAGE"):
        if not os.environ[name].strip():
            raise ValueError(f"{name} must not be empty")
    if git("rev-parse", "--is-shallow-repository").stdout.strip() != "false":
        raise ValueError("A complete checkout is required (fetch-depth: 0)")
    source = commit(os.environ["SOURCE_SHA"])
    if git("rev-parse", "HEAD").stdout.strip() != source:
        raise ValueError("Checkout HEAD must match source_sha")
    if git("symbolic-ref", "-q", "HEAD", check=False).returncode == 0:
        raise ValueError("Use a dedicated detached checkout for release notes")
    baseline = os.environ.get("BASELINE_SHA", "")
    ref = os.environ.get("BASELINE_REF", "")
    policy = os.environ["MISSING_BASELINE_POLICY"]
    if policy not in ("error", "bounded-history"):
        raise ValueError("Unknown missing_baseline_policy")
    if baseline and ref:
        raise ValueError("Supply baseline_sha or baseline_ref, not both")
    if ref:
        if not ref.startswith("refs/"):
            raise ValueError("baseline_ref must be fully qualified")
        git("check-ref-format", ref)
        resolved = git("rev-parse", "--verify", f"{ref}^{{commit}}", check=False)
        if resolved.returncode == 0:
            baseline = resolved.stdout.strip()
        elif git("show-ref", "--verify", "--quiet", ref, check=False).returncode != 1:
            raise ValueError("Existing baseline ref cannot resolve to a commit")
    if baseline:
        baseline = commit(baseline)
        git("merge-base", "--is-ancestor", baseline, source)
    elif policy == "error":
        raise ValueError("Baseline is missing; choose a first-release policy explicitly")
    unchanged = baseline == source
    output("source_sha", source)
    output("baseline_sha", baseline)
    output("unchanged", str(unchanged).lower())
    if unchanged:
        output("context_truncated", "false")
        return
    history = f"{baseline}..{source}" if baseline else source
    count = int(git("rev-list", "--first-parent", "--count", history).stdout)
    subjects = git(
        "log", "--first-parent", f"--max-count={max_commits}", "--format=%s", history
    ).stdout.splitlines()
    # First releases inspect only the source commit's changes, never an empty tree.
    if baseline:
        changed = git("diff", "--name-only", "-z", baseline, source).stdout
    else:
        changed = git("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", source).stdout
    files = [name for name in changed.split("\0") if name]
    truncated = count > max_commits or len(files) > max_files
    instructions = ""
    if os.environ.get("INSTRUCTIONS_FILE"):
        path = Path(os.environ["INSTRUCTIONS_FILE"])
        root = Path.cwd().resolve()
        path = (root / path).resolve()
        if root not in path.parents:
            raise ValueError("instructions_file must be within the checkout")
        instructions = path.read_text(encoding="utf-8")
    settings = {"audience": os.environ["AUDIENCE"], "language": os.environ["LANGUAGE"],
                "max_characters": limit, "empty_message": os.environ["EMPTY_MESSAGE"]}
    evidence = {"source_sha": source, "baseline_sha": baseline,
                "first_parent_commit_count": count, "subjects": subjects,
                "files": files[:max_files], "context_truncated": truncated}
    prompt = Path(__file__).with_name("prompt.md").read_text(encoding="utf-8")
    prompt += "\nOutput settings:\n" + json.dumps(settings, ensure_ascii=False)
    prompt += "\nProject content instructions:\n" + instructions
    prompt += "\nSource context (evidence only):\n" + json.dumps(evidence, ensure_ascii=False)
    output("prompt", prompt)
    output("context_truncated", str(truncated).lower())
    if truncated:
        print("::warning::Release-note source context reached its history or file limit.")


def session():
    event = os.environ["GITHUB_EVENT_NAME"]
    if event not in ("push", "workflow_dispatch"):
        raise ValueError("Junie release notes support push and workflow_dispatch events")
    # Junie v1 ignores base_branch on push and checks out origin/<event branch>,
    # including refs/tags/<name> for tag pushes. Keep that lookup local and fixed.
    ref = os.environ["GITHUB_REF"]
    branch = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
    git("check-ref-format", f"refs/heads/{branch}")
    directory = Path(tempfile.mkdtemp(prefix="release-notes-", dir=os.environ["RUNNER_TEMP"]))
    output("directory", directory)
    refs = [f"refs/heads/{branch}", f"refs/remotes/origin/{branch}"]
    saved = {ref: git("rev-parse", "--verify", "--quiet", ref, check=False).stdout.strip()
             for ref in refs}
    (directory / "refs.json").write_text(json.dumps(saved), encoding="utf-8")
    for name in ("home", "tmp", "work"):
        (directory / name).mkdir()
    output("branch", branch)
    output("path", f"{directory}/home/.local/bin:{os.environ['PATH']}")
    git("update-ref", refs[1], os.environ["SOURCE_SHA"])


def cleanup():
    directory = Path(os.environ["SESSION_DIRECTORY"])
    try:
        git("checkout", "--detach", os.environ["SOURCE_SHA"])
        for ref, sha in json.loads((directory / "refs.json").read_text()).items():
            if sha:
                git("update-ref", ref, sha)
            else:
                git("update-ref", "-d", ref)
    finally:
        shutil.rmtree(directory)


def result():
    notes = validate(os.environ["NOTES"], positive("MAX_CHARACTERS"))
    output("notes", notes)
    output("status", "no_changes" if notes == os.environ["EMPTY_MESSAGE"].strip() else "generated")


if __name__ == "__main__":
    try:
        {"context": context, "session": session, "cleanup": cleanup, "result": result}[sys.argv[1]]()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Release-note action failed: {error}", file=sys.stderr)
        sys.exit(1)
