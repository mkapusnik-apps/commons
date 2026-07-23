# Lifecycle Tag Gate

## Purpose

`Lifecycle Tag Gate` decides whether a lifecycle workflow should run by reading a source tag and a target tag from a Git remote. It treats missing tags as normal lifecycle states and peels annotated tags before comparing commit SHAs.

## User scenario

Use this action when a workflow should promote work only if a source lifecycle tag exists and the target lifecycle tag is missing or points at a different commit, such as promoting `staging` to `production`.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `source_tag` | Yes | None | Source lifecycle tag name that must exist before the workflow should run. Do not include `refs/tags/`. |
| `target_tag` | Yes | None | Target lifecycle tag name that is current when it points at the same SHA as `source_tag`. Do not include `refs/tags/`. |
| `repository` | No | Current workflow repository | Repository in `owner/repo` form. Used for validation and log messages. |
| `remote` | No | `origin` | Git remote name or URL used to read lifecycle tags. |

Tag inputs are validated with Git ref-name rules before they are used. `remote` must be non-empty and must not start with `-`.

## Outputs

| Output | Description |
| --- | --- |
| `should_run` | `true` only when `reason` is `pending`; otherwise `false`. |
| `source_sha` | Commit SHA currently referenced by `source_tag`, or an empty string when `source_tag` is missing. |
| `target_sha` | Commit SHA currently referenced by `target_tag`, or an empty string when `target_tag` is missing. |
| `short_sha` | First 12 characters of `source_sha`, or an empty string when `source_tag` is missing. |
| `reason` | Lifecycle gate decision reason: `source-missing`, `already-current`, or `pending`. |

## Permissions

The action reads tags with `git ls-remote` and does not call the GitHub API. Same-repository workflows commonly grant `contents: read` and run `actions/checkout` before calling the local action. Cross-repository use must provide a readable remote URL or remote name.

## Success behavior

- If `source_tag` is missing, the action reports `should_run=false`, clears SHA outputs, and sets `reason=source-missing`.
- If `source_tag` exists and `target_tag` is missing, the action reports `should_run=true` and sets `reason=pending`.
- If both tags exist and point at the same peeled commit SHA, the action reports `should_run=false` and sets `reason=already-current`.
- If both tags exist and point at different peeled commit SHAs, the action reports `should_run=true` and sets `reason=pending`.

## Failure behavior

The action fails before reading tags when required inputs are empty, `repository` is not in `owner/repo` form, a tag input starts with `refs/`, a tag input is not a valid Git tag name, `remote` starts with `-`, or `GITHUB_OUTPUT` is unavailable.

It also fails when `git ls-remote` cannot read from the configured remote for reasons other than a missing tag.

## Notable edge cases

- Tag names are bare names. Use `staging`, not `refs/tags/staging`.
- Annotated tags are peeled to their target commit SHA before comparison.
- Missing source or target tags are handled as lifecycle states, not remote-read failures.
- External consumers should pin the action to a release tag or immutable commit SHA.
