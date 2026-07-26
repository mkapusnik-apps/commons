# Set Git Tag

## Purpose

`Set Git Tag` creates or updates a lightweight tag in the current repository. It is a legacy, tag-specific action retained for backward compatibility with existing workflows.

For new workflows, prefer [`Set Git Ref`](git-ref.md) with `ref: refs/tags/<tag-name>` because it has explicit outputs, stronger validation, repository selection, and configurable create/no-op behavior.

## User scenario

Use this action only when an existing workflow already depends on the historical interface that accepts a bare tag name and force-updates that tag in the current repository.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `tag` | Yes | None | Tag name to create or update, without the `refs/tags/` prefix. |
| `commit_sha` | No | Current workflow SHA | Commit SHA to tag. If omitted or blank, the action uses `context.sha`. |
| `token` | Yes | None | GitHub token used for ref operations. Use a PAT or GitHub App token when downstream workflow triggering or cross-permission behavior requires it. |

## Outputs

This action declares no public outputs.

## Permissions

The token needs `contents: write` in the current repository. The default `GITHUB_TOKEN` can update tags in the current repository when workflow permissions allow it. Use a PAT or GitHub App token if the workflow needs behavior that the default token cannot provide, such as triggering downstream workflows that ignore `GITHUB_TOKEN`-authored events.

## Success behavior

- The action first looks up the exact `tags/<tag>` ref in the current repository.
- If the tag exists, the action force-updates it to `commit_sha` or `context.sha` without first attempting creation.
- If and only if the lookup returns `404 Not Found`, the action creates the lightweight `refs/tags/<tag>` ref at the target SHA.
- Logs identify whether the action is creating or updating the tag without including the token.

## No-op behavior

The action does not detect or report no-op updates. If the tag already points at the requested SHA, the update path can still call GitHub and finish successfully, but there is no `changed` output.

## Failure behavior

The action fails when `tag` is empty, the token cannot read or mutate the ref, the commit SHA is invalid or inaccessible, or GitHub rejects an API request. Lookup failures other than the expected exact-ref `404` are reported as lookup failures and do not trigger creation. Create and update failures identify the failed operation and do not fall back to the other mutation. Validation is intentionally minimal to preserve the legacy behavior.

## Notable edge cases

- This action only targets the current repository from the workflow context; it has no `repository` input.
- It always force-updates an existing tag after confirming that the exact ref exists.
- Race-condition detection, retries, and recovery are not provided. If the ref changes between lookup and mutation, the resulting create or update failure remains visible.
- It does not validate the tag name beyond checking that it is non-empty before calling GitHub.
- It does not expose `previous_sha`, `new_sha`, or `changed`; use `Set Git Ref` when consumers need those outputs.
