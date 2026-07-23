# Create or Update Pull Request

## Purpose

`Create or Update Pull Request` opens a pull request for a head/base pair or updates the existing open pull request for that same pair. It can optionally request GitHub auto-merge.

## User scenario

Use this action for recurring automation, such as a promotion workflow that repeatedly updates the same release pull request instead of opening a new pull request on every run.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `head` | Yes | None | Head branch name or `owner:branch` reference used to find an existing open pull request. |
| `base` | Yes | None | Base branch name for the pull request. |
| `title` | Yes | None | Pull request title to set on create or update. |
| `body` | No | Empty string | Pull request body to set on create or update. Multi-line Markdown is supported. |
| `auto_merge` | No | `true` | Enables the auto-merge step only when the string value is exactly `true`. |
| `merge_method` | No | `merge` | Auto-merge method. Supported values are `merge` and `squash`. |
| `token` | Yes | None | GitHub token used for pull request operations. |

## Outputs

| Output | Description |
| --- | --- |
| `pull_request_number` | Created or updated pull request number. |
| `pull_request_url` | Created or updated pull request URL. |

The implementation also uses an internal `pull_request_id` step output to enable auto-merge; it is not declared as a public action output.

## Permissions

The token needs `pull-requests: write` to create or update pull requests in the current repository. Auto-merge requires the repository to allow auto-merge, the pull request to be eligible for auto-merge, and the token to have permission to enable it. Workflows often also grant `contents: read` so the job can inspect repository contents before calling the action.

## Success behavior

- If an open pull request already exists for the requested `head` and `base`, the action updates its title and body, then returns its number and URL.
- If no matching open pull request exists, the action creates one, then returns its number and URL.
- When `auto_merge` is exactly `true`, the action validates `merge_method` and calls GitHub's GraphQL auto-merge mutation.

## No-op behavior

The action does not explicitly detect identical title or body content. Updating an existing pull request with the same values is treated as a successful update.

If `auto_merge` is any value other than exactly `true`, the auto-merge step is skipped.

## Failure behavior

The action fails before create or update when `head`, `base`, or `title` is empty. It fails during GitHub API calls when the token lacks permission, the head branch does not exist, branch protection or repository settings reject the operation, or auto-merge cannot be enabled.

When auto-merge runs, any `merge_method` value other than `merge` or `squash` fails the action.

## Notable edge cases

- Existing pull request lookup uses `owner:branch` when `head` does not already contain an owner. New pull request creation sends the branch name portion to GitHub, so the create path is intended for branches in the current repository.
- The action does not create, update, or push the head branch; another workflow step must prepare the branch before this action runs.
- Auto-merge is enabled after the pull request is created or updated. A failure in the auto-merge step leaves the pull request created or updated.
- External consumers should pin the action to a release tag or immutable commit SHA.
