# Reusable Git Ref and Workflow State Actions

Status: implemented for GitHub issue #2.

Consumer-facing documentation for the current reusable actions lives in the [actions catalog](README.md). This page remains as historical product context for the original generic ref and workflow-state work.

## Product goal

Provide reusable GitHub Actions helpers for repository lifecycle workflows that need to move Git refs and enable or disable workflows without copying project-specific scripts between repositories.

These helpers should be safe to call repeatedly, clearly report what changed, and preserve the existing tag-specific action for current consumers.

## Generic Git ref action

### User-facing behavior

The generic Git ref action creates or updates a full Git ref in a target repository. It supports lifecycle refs such as `refs/tags/nightly` and `refs/heads/nightly`, and it is not limited to tags.

The action must not require callers to check out the repository or run local Git commands for the normal create/update path.

### Inputs

| Input | Required | Default | Expected behavior |
| --- | --- | --- | --- |
| `repository` | No | Current workflow repository | Target repository in `owner/name` form. |
| `ref` | Yes | None | Full ref name, such as `refs/tags/nightly` or `refs/heads/nightly`. Short names are rejected to avoid ambiguity. |
| `commit_sha` | No | Current workflow SHA | Commit SHA that the ref should point to. The action defaults to `github.sha` for compatibility with simple current-commit promotion workflows. |
| `token` | Yes | None | Token authorized to create or update refs in the target repository. |
| `force` | No | `true` | Allows moving an existing ref when the hosting service requires a forced update. When `false`, unsafe or rejected moves fail without changing the ref. |
| `create_if_missing` | No | `true` | Creates the ref when it does not already exist. When `false`, a missing ref fails clearly. |
| `noop_if_unchanged` | No | `true` | Avoids a no-op update when the ref already points at `commit_sha`. |

### Outputs

| Output | Expected value |
| --- | --- |
| `changed` | `true` when the ref target changed or was created; otherwise `false`. |
| `previous_sha` | The SHA the ref pointed to before the action ran, or an empty value when the ref did not exist. |
| `new_sha` | The requested `commit_sha` after a successful run. |
| `ref` | The full ref name that was evaluated. |

### Acceptance criteria

- A caller can create a missing full ref when `create_if_missing` is `true`.
- A caller can update an existing full ref to a different commit SHA.
- A caller can update both tag refs and branch refs using the same action interface.
- A call where the ref already points at `commit_sha` succeeds and reports `changed=false` when `noop_if_unchanged` is `true`.
- A missing ref fails with a clear message when `create_if_missing` is `false`.
- An unsupported or malformed `ref`, empty resolved `commit_sha`, empty `token`, or malformed `repository` fails with a clear validation message before attempting a ref change.
- Ref update failures are surfaced clearly, including authorization failures and rejected non-forced updates.
- The existing `.github/actions/tag` action remains backward-compatible for current inputs and behavior.

## Workflow state action

### User-facing behavior

The workflow state action enables or disables a GitHub Actions workflow in a target repository by workflow file name or workflow ID.

It supports lifecycle workflows where one automation step controls whether another workflow is available to run, such as enabling production deployment after staging succeeds or disabling a scheduled nightly workflow until a new sanity tag is available.

### Inputs

| Input | Required | Default | Expected behavior |
| --- | --- | --- | --- |
| `workflow` | Yes | None | Workflow file name, `.github/workflows/...` path, or workflow ID, such as `nightly.yml`. |
| `state` | Yes | None | Desired state. Supported aliases are `enable`, `enabled`, `active`, `disable`, `disabled`, and `disabled_manually`. |
| `repository` | No | Current workflow repository | Target repository in `owner/name` form. |
| `token` | Yes | None | Token authorized to update workflow state in the target repository. |

### Outputs

| Output | Expected value |
| --- | --- |
| `changed` | `true` when the workflow state changed; otherwise `false`. |
| `previous_state` | Workflow state before the action ran. |
| `new_state` | Workflow state after a successful run. |
| `workflow_id` | Numeric workflow ID returned by GitHub. |
| `workflow_path` | Workflow path returned by GitHub. |

### Acceptance criteria

- A caller can enable a workflow by file name.
- A caller can disable a workflow by file name.
- A caller can enable or disable a workflow by workflow ID.
- Supported state aliases are documented and behave consistently.
- Unsupported states fail with a clear validation message listing supported values.
- Missing or empty `workflow`, `state`, `token`, or malformed `repository` fails with a clear validation message.
- Authorization failures, missing workflows, and repository access failures are surfaced clearly.

## Documentation and validation checklist

- Each new action has action metadata and a README with at least one copyable workflow example.
- The documentation states the required permissions: `contents: write` for ref updates and `actions: write` for workflow state changes.
- The documentation explains that cross-repository updates may require a PAT or GitHub App token with access to the target repository.
- The documentation recommends pinning shared actions to a release tag or immutable SHA for external consumers.
- The documentation states that updating multiple refs is not atomic and callers should handle partial failure explicitly.
- The pull request for this work references issue #2 without closing syntax, for example `Related to #2`.
