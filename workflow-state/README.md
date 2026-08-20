# Set Workflow State

Enable or disable a GitHub Actions workflow with the GitHub REST API. The action accepts a workflow file name, a `.github/workflows/...` path, or a numeric workflow ID when supported by the API.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `workflow` | Yes | None | Workflow file name, `.github/workflows/...` path, or numeric workflow ID. |
| `state` | Yes | None | Desired state. Supported aliases are `enable`, `enabled`, `active`, `disable`, `disabled`, and `disabled_manually`. |
| `repository` | No | Current workflow repository | Target repository in `owner/repo` form. |
| `token` | Yes | None | Token authorized to enable or disable workflows in the target repository. |

## Outputs

| Output | Description |
| --- | --- |
| `changed` | `true` when the workflow state changed; otherwise `false`. |
| `previous_state` | Workflow state before the action ran. |
| `new_state` | Workflow state after a successful run. |
| `workflow_id` | Numeric workflow ID returned by GitHub. |
| `workflow_path` | Workflow path returned by GitHub. |

## Permissions

The token needs `actions: write` in the target repository. The default `GITHUB_TOKEN` can update workflows in the current repository when workflow permissions allow it. Cross-repository workflow updates usually require a fine-grained PAT or GitHub App token with access to the target repository.

## Examples

Disable a scheduled nightly workflow:

```yaml
permissions:
  actions: write

steps:
  - name: Disable nightly workflow
    uses: mkapusnik-apps/commons/workflow-state@v1
    with:
      workflow: nightly.yml
      state: disabled
      token: ${{ github.token }}
```

Enable a workflow by path after a promotion succeeds:

```yaml
- name: Enable production deployment
  uses: mkapusnik-apps/commons/workflow-state@v1
  with:
    workflow: .github/workflows/deploy-production.yml
    state: enabled
    token: ${{ secrets.RELEASE_TOKEN }}
```

The action avoids API state changes when the workflow is already enabled or already disabled.

For external consumers, use the floating `v1` tag for compatible v1 updates or pin a reviewed immutable commit SHA for stricter reproducibility. Do not use a moving branch.
