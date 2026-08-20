# Set Git Ref

## Purpose

`Set Git Ref` creates or updates a full Git ref with the GitHub REST refs API. It is the general-purpose replacement for workflows that need to move branch refs, tag refs, or other full refs without checking out the repository or running local `git push` commands.

## User scenario

Use this action when a workflow promotes a commit by moving a lifecycle pointer such as `refs/tags/nightly`, `refs/tags/staging`, or `refs/heads/release-candidate` to a known commit SHA.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `repository` | No | Current workflow repository | Target repository in `owner/repo` form. |
| `ref` | Yes | None | Full ref name, for example `refs/heads/nightly` or `refs/tags/nightly`. Short names are rejected. |
| `commit_sha` | No | Current workflow SHA | Target commit SHA. Must be a 40- or 64-character hexadecimal SHA. |
| `token` | Yes | None | GitHub token authorized to create or update refs in the target repository. |
| `force` | No | `true` | Whether GitHub may force-update an existing ref. Set to `false` to let GitHub reject non-fast-forward or otherwise unsafe moves. |
| `create_if_missing` | No | `true` | Whether to create the ref when it does not already exist. |
| `noop_if_unchanged` | No | `true` | Whether to skip the update API call when the ref already points at `commit_sha`. |

`force`, `create_if_missing`, and `noop_if_unchanged` must be exactly `true` or `false` after trimming and lowercasing.

## Outputs

| Output | Description |
| --- | --- |
| `changed` | `true` when the ref was created or moved to a different SHA; otherwise `false`. |
| `previous_sha` | Previous object SHA for the ref, or an empty string when the ref did not exist. |
| `new_sha` | Target commit SHA after a successful run. |
| `ref` | Full ref name that was evaluated. |

## Permissions

The token needs `contents: write` in the target repository. The default `GITHUB_TOKEN` can update refs in the current repository when workflow permissions allow it. Cross-repository updates usually require a fine-grained PAT or GitHub App token with write access to contents in the target repository.

## Success behavior

- If the ref is missing and `create_if_missing` is `true`, the action creates it and reports `changed=true` with an empty `previous_sha`.
- If the ref exists and points at a different SHA, the action updates it and reports `changed=true`.
- If `force` is `false`, GitHub decides whether the update is allowed and rejected moves fail.

## No-op behavior

When the ref already points at `commit_sha` and `noop_if_unchanged` is `true`, the action skips the update call, reports `changed=false`, and keeps `previous_sha` equal to `new_sha`.

If `noop_if_unchanged` is `false`, the action still calls the update API. The final `changed` output remains `false` when the previous and requested SHAs are equal.

## Failure behavior

The action fails before changing the ref when required inputs are empty, `repository` is not in `owner/repo` form, `commit_sha` is not a supported hexadecimal SHA, `ref` is not a valid full Git ref, or a boolean input is not `true` or `false`.

It also fails when GitHub cannot read, create, or update the ref because of authorization, repository access, API validation, or rejected non-forced updates. API errors include the status and documentation URL when GitHub provides them.

## Notable edge cases

- The `ref` input must include the `refs/` prefix. Use `refs/tags/name` for tags, not `name`.
- The action accepts both 40-character SHA-1 and 64-character SHA-256 style hexadecimal object IDs.
- Updating multiple refs by calling the action more than once is not atomic; later calls may fail after earlier refs have already moved.
- External consumers should pin the action to a release tag or immutable commit SHA.
