# Set Git Tag

## Purpose

`Set Git Tag` creates or updates a lightweight or annotated tag in the current repository. Existing inputs and default behavior are unchanged. Use `mkapusnik-apps/commons/tag@v1`; the previous `.github/actions/tag` path is not retained.

## User scenario

Use this action when a workflow needs to create or force-update a tag using a bare tag name. Supply `message` for an annotated tag. Set `create-only` to `'true'` when an existing tag must cause failure instead of an update.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `tag` | Yes | None | Tag name to create or update, without the `refs/tags/` prefix. |
| `commit_sha` | No | Current workflow SHA | Commit SHA to tag. If omitted or blank, the action uses `context.sha`. |
| `message` | No | Empty string | Empty means a lightweight tag. Any non-empty string, including whitespace-only text, creates an annotated tag. The message is passed unchanged, including leading and trailing whitespace and newlines. |
| `create-only` | No | `'false'` | `'true'` fails if the tag exists, even at the same target. Comparison ignores case and surrounding whitespace. Other values keep the default create-or-update behavior. |
| `token` | No | `${{ github.token }}` | GitHub token used for ref operations. Use a PAT or GitHub App token when downstream workflow triggering or cross-permission behavior requires it. |

## Outputs

This action declares no public outputs.

## Permissions

The token needs `contents: write` in the current repository. The default `GITHUB_TOKEN` can update tags in the current repository when workflow permissions allow it. Use a PAT or GitHub App token if the workflow needs behavior that the default token cannot provide, such as triggering downstream workflows that ignore `GITHUB_TOKEN`-authored events.

## Success behavior

- The action first looks up the exact `tags/<tag>` ref in the current repository.
- If the tag exists and `create-only` is enabled, the action fails before any mutation.
- With an empty `message`, the ref points directly to `commit_sha` or `context.sha` as a lightweight tag.
- With a non-empty `message`, the action creates a Git tag object with that message, object type `commit`, and the target commit SHA. The ref points to the returned tag-object SHA, not directly to the commit. GitHub supplies the tagger identity.
- If the tag exists and `create-only` is disabled, the action force-updates its ref without first attempting ref creation.
- If and only if the lookup returns `404 Not Found`, the action creates `refs/tags/<tag>`. This also applies in create-only mode.
- Logs identify whether the action is creating or updating the tag without including the token.

## Example

```yaml
permissions:
  contents: write

steps:
  - uses: mkapusnik-apps/commons/tag@v1
    with:
      tag: v2.0.0
      commit_sha: ${{ github.sha }}
      create-only: 'true'
      message: |-
        Release v2.0.0

        Shared automation update.
```

Use YAML block scalar controls such as `|-` or `|+` to select trailing-newline handling. The action does not trim the resulting input.

## No-op behavior

The action does not detect or report no-op updates. With `create-only` disabled, an existing lightweight tag at the requested SHA can still be updated successfully. A non-empty message creates a tag object even if the commit and message match an existing annotation. With `create-only` enabled, any existing tag causes failure. There is no `changed` output.

## Failure behavior

The action fails when `tag` is empty, create-only mode finds an existing tag, the token cannot read or mutate the tag, the commit SHA is invalid or inaccessible, or GitHub rejects an API request. Lookup failures other than the expected exact-ref `404` are reported as lookup failures and do not trigger creation. Annotation, ref creation, and ref update failures identify the failed operation and do not fall back to another mutation. Validation is intentionally minimal to preserve the legacy behavior.

## Notable edge cases

- This action only targets the current repository from the workflow context; it has no `repository` input.
- With `create-only` disabled, an existing tag is force-updated. Its type can change between lightweight and annotated according to `message`.
- Create-only mode never updates or deletes a ref. If another caller creates the tag after lookup, ref creation fails without overwriting that tag.
- Annotation creation and ref mutation are separate API requests. If ref mutation fails, an unreferenced tag object can remain; the action does not remove it or retry.
- Race-condition detection, retries, and recovery are not provided. If the ref changes between lookup and mutation, the resulting create or update failure remains visible.
- It does not validate the tag name beyond checking that it is non-empty before calling GitHub.
- It does not expose `previous_sha`, `new_sha`, or `changed`.
