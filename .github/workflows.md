# Repository Workflow

This repository uses `master` as the canonical base branch for pull requests.

## CI validation

`Validate GitHub Actions` runs on pull requests targeting `master` or `develop`.
It validates all local `action.yml` and `action.yaml` metadata files, plus
workflow YAML files under `.github/workflows/`.

The check requires no repository secrets and only `contents: read` permission. It
fails on invalid YAML, duplicate YAML mapping keys, missing basic action metadata
such as `name`, `description`, and `runs`, or malformed `inputs`, `outputs`, and
`runs` sections.
