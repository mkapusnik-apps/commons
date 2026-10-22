# Release Notes

## Purpose

`Release Notes` generates bounded, audience-facing release notes from immutable
local Git context with `JetBrains/junie-github-action@v1`. It returns validated
text, not a file. It does not publish releases, update lifecycle tags, or persist
notes for retries; those responsibilities remain with the caller.

The action was extracted from `mkapusnik-apps/shift-tac-toe` at
`29dfa477349da862488ee510bed6d6d9e458aa87`. Its public interface is the composite
action's inputs and outputs. The bundled Python helper is an implementation
detail, not a supported standalone validation API.

## Caller prerequisites and permissions

- Use a dedicated Linux job with Bash, Python 3.8 or later, Git, and the tools
  required by the upstream Junie action, including its Bun/CLI setup.
- Check out the source at the workspace root using a full commit SHA,
  `fetch-depth: 0`, and `persist-credentials: false`. HEAD must be detached.
- Supported events are branch/tag `push` and `workflow_dispatch`. PR events are
  unsupported because Junie selects the PR head independently.
- Select runner, Environment, job timeout, and `contents: read` in the caller.
  Supply `junie_api_key` explicitly from secrets. Do not put signing, cloud, or
  distribution credentials in the generation job.
- Fetch the baseline before calling the action. Resolve it once in the caller
  when other jobs must use the same checkpoint. Context collection never
  refreshes refs from the network.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `source_sha` | Yes | None | Full SHA-1 commit ID matching the detached checkout. |
| `baseline_sha` | No | Empty | Captured ancestor commit SHA; mutually exclusive with `baseline_ref`. |
| `baseline_ref` | No | Empty | Fully qualified, already fetched local ref, resolved once to a commit. |
| `missing_baseline_policy` | No | `error` | `error` or `bounded-history`; the latter explicitly permits a first release without a baseline. |
| `audience` | Yes | None | Intended readers; must not be blank. |
| `language` | No | `English` | Output language; must not be blank. |
| `max_characters` | Yes | None | Positive maximum length in Unicode code points, including internal whitespace. |
| `empty_message` | Yes | None | Valid fallback text for unchanged source or no meaningful audience-facing change. |
| `instructions_file` | No | Empty | Optional wording/format instructions within the caller checkout; relative to its root. |
| `max_commits` | No | `40` | Positive maximum number of first-parent commit subjects supplied to Junie. |
| `max_files` | No | `80` | Positive maximum number of changed file names supplied to Junie. |
| `junie_api_key` | Yes | None | Caller-supplied Junie secret. |

## Outputs

All outputs are strings. Multiline text uses GitHub's output protocol with unique
delimiters. Pass text through job outputs when another job needs it; local paths
do not cross job runners.

| Output | Description |
| --- | --- |
| `notes` | Validated release-note text with surrounding whitespace removed. |
| `status` | `no_changes` when the text equals the trimmed `empty_message`; otherwise `generated`. This is not a semantic classifier. |
| `source_sha` | Resolved source commit SHA. |
| `baseline_sha` | Resolved baseline commit SHA, or empty for an explicit first release. |
| `context_truncated` | `true` if the history or changed-file list exceeded its configured limit; otherwise `false`. |

## Behavior contract

- **RN-01 — Immutable context:** Require a complete detached checkout matching
  `source_sha`. Accept at most one baseline input, resolve refs once, and require
  a supplied baseline to be an ancestor of the source.
- **RN-02 — Bounded evidence:** Supply first-parent subjects and changed file
  names within the configured limits, with the full first-parent count and a
  truncation flag. Emit a warning when context is truncated. Without a baseline,
  use bounded source history and only the source commit's changed files, never
  an empty-tree diff. A root commit has no parent diff.
- **RN-03 — No-change path:** When source and baseline match, skip Junie and
  return the validated fallback with `status: no_changes`. Otherwise ask Junie
  for only supported audience-facing changes in the requested language and
  format, or the fallback when no meaningful audience-facing change exists.
- **RN-04 — Output validation:** Trim surrounding whitespace and reject blank
  or overlength text, code fences, common task-report headings, and ASCII control
  characters below U+0020 other than newline and tab. Execution errors fail the
  action; they never become fallback notes. Validation does not establish
  factual completeness or audience relevance.
- **RN-05 — Session lifecycle:** Isolate HOME, temporary files, Bun/XDG state,
  Junie state, and work directories per invocation. Temporarily provide Junie's
  local origin lookup at `source_sha`, including on tag pushes, without pushing
  a synthetic remote branch. After success or failure, run cleanup to restore
  saved local refs and detached source HEAD and remove the session directory.
  A runner termination can prevent cleanup.

Missing baselines fail unless `bounded-history` is explicit. Invalid policies,
corrupt/non-commit refs, unrelated baselines, shallow history, invalid limits,
source/HEAD mismatches, and instruction paths escaping the checkout fail.

Isolation is not an OS sandbox. Junie installs tools, authenticates with its
service, uses GitHub metadata, and can upload diagnostic artifacts under the
upstream action's policy. Prompt restrictions govern model behavior, not every
network operation of the upstream action. Keep the job minimally privileged.
The action implements no retries or release recovery; callers persist approved
text when a release must reuse it on reruns.

## Example

```yaml
permissions:
  contents: read

steps:
  - uses: actions/checkout@v7
    with:
      ref: ${{ github.sha }}
      fetch-depth: 0
      persist-credentials: false
  - name: Generate release notes
    id: notes
    uses: mkapusnik-apps/commons/release-notes@v1
    with:
      source_sha: ${{ github.sha }}
      baseline_ref: refs/tags/staging
      missing_baseline_policy: bounded-history
      audience: Android staging testers
      max_characters: '1200'
      empty_message: Nightly snapshot was generated.
      instructions_file: .github/prompts/staging-release-notes.md
      junie_api_key: ${{ secrets.JUNIE_API_KEY }}
```

The optional instructions file belongs to the consumer. Choose an existing
fetched baseline and project-specific audience, fallback, and character limit.
Use `v1` only after a release containing `release-notes/` has been published;
older fixed releases do not gain the new action path. A reviewed full commit SHA
provides stricter pinning.

## Local checks

Run `python3 .github/scripts/test-release-notes.py`. The tests execute the bundled
helper against temporary consumer Git repositories, including from outside the
action directory. They do not call Junie or publish releases.
