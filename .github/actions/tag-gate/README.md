# Lifecycle Tag Gate

Gates lifecycle workflows by checking whether a source lifecycle tag exists and whether a target lifecycle tag already points at the same SHA.
Annotated tags are peeled to the commit SHA they reference before comparison.

Missing tags are normal lifecycle states, not failures:

- Missing `source_tag`: `should_run=false`, `reason=source-missing`.
- Existing `source_tag` with missing `target_tag`: `should_run=true`, `reason=pending`.
- Matching tags: `should_run=false`, `reason=already-current`.
- Existing tags with different SHAs: `should_run=true`, `reason=pending`.

## Inputs

| Name | Required | Default | Description |
| --- | --- | --- | --- |
| `source_tag` | Yes | N/A | Source lifecycle tag name that must exist before the workflow should run. Do not include `refs/tags/`. |
| `target_tag` | Yes | N/A | Target lifecycle tag name that is current when it points at the same SHA as `source_tag`. Do not include `refs/tags/`. |
| `repository` | No | `${{ github.repository }}` | Repository in `owner/repo` form. Used for validation and log messages. |
| `remote` | No | `origin` | Git remote name or URL used to read tags. |

Tag names are validated with Git ref-name rules before they are used.

## Outputs

| Name | Description |
| --- | --- |
| `should_run` | `true` only when `reason=pending`; otherwise `false`. |
| `source_sha` | Commit SHA currently referenced by `source_tag`, or an empty string when `source_tag` is missing. |
| `target_sha` | Commit SHA currently referenced by `target_tag`, or an empty string when `target_tag` is missing. |
| `short_sha` | First 12 characters of `source_sha`, or an empty string when `source_tag` is missing. |
| `reason` | One of `source-missing`, `already-current`, or `pending`. |

## Permissions

This action reads tags with `git ls-remote` and does not require `actions: write`. For same-repository usage with `actions/checkout`, `contents: read` is sufficient.

When using this action from another repository, production consumers should pin `mkapusnik/commons` to a trusted tag or SHA instead of a moving branch ref when practical.

## Example

Cross-repository usage:

```yaml
- id: tag-gate
  uses: mkapusnik/commons/.github/actions/tag-gate@master
  with:
    source_tag: staging
    target_tag: production
    remote: https://github.com/<owner>/<repo>.git
```

The explicit `remote` avoids depending on an `origin` remote created by a prior checkout step.

Same-repository workflow usage:

```yaml
name: Promote lifecycle tag

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - id: tag-gate
        uses: ./.github/actions/tag-gate
        with:
          source_tag: staging
          target_tag: production

      - name: Run promotion
        if: steps.tag-gate.outputs.should_run == 'true'
        run: ./scripts/promote.sh
```
