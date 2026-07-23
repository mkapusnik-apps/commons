# Set Workflow State

## Purpose

`Set Workflow State` enables or disables a GitHub Actions workflow in a target repository by calling the GitHub REST API.

## User scenario

Use this action when lifecycle automation controls whether another workflow is available, such as enabling production deployment after a staging promotion or disabling scheduled work until a required tag is present.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `workflow` | Yes | None | Workflow file name, `.github/workflows/...` path, or numeric workflow ID. |
| `state` | Yes | None | Desired state. Supported aliases are `enable`, `enabled`, `active`, `disable`, `disabled`, and `disabled_manually`; hyphenated aliases are normalized to underscores. |
| `repository` | No | Current workflow repository | Target repository in `owner/repo` form. |
| `token` | Yes | None | GitHub token authorized to enable or disable workflows in the target repository. |

## Outputs

| Output | Description |
| --- | --- |
| `changed` | `true` when the workflow state changed; otherwise `false`. |
| `previous_state` | Workflow state before the action ran. |
| `new_state` | Workflow state after a successful run. |
| `workflow_id` | Numeric workflow ID returned by GitHub. |
| `workflow_path` | Workflow path returned by GitHub. |

## Permissions

The token needs `actions: write` in the target repository. The default `GITHUB_TOKEN` can update workflows in the current repository when workflow permissions allow it. Cross-repository workflow updates usually require a fine-grained PAT or GitHub App token with write access to actions in the target repository.

## Success behavior

- Enabling a disabled workflow calls GitHub's enable workflow endpoint, reports `changed=true`, and sets `new_state=active`.
- Disabling an enabled workflow calls GitHub's disable workflow endpoint, reports `changed=true`, and sets `new_state=disabled_manually`.
- The action returns the workflow ID and path from the workflow GitHub found before changing state.

## No-op behavior

If the workflow is already enabled and the desired state is enabled, or already disabled and the desired state is disabled, the action makes no state-change API call, reports `changed=false`, and preserves the observed `previous_state` as `new_state`.

## Failure behavior

The action fails before changing workflow state when required inputs are empty, `repository` is not in `owner/repo` form, or `state` is not one of the supported aliases.

It also fails when GitHub cannot find or read the workflow, the token lacks permission, repository access is denied, or the enable/disable API call fails. API errors include the status and documentation URL when GitHub provides them.

## Notable edge cases

- The `workflow` input strips a leading `.github/workflows/` prefix, so both `release.yml` and `.github/workflows/release.yml` target the same workflow file.
- Any workflow state that starts with `disabled` is treated as disabled for no-op detection.
- External consumers should pin the action to a release tag or immutable commit SHA.
