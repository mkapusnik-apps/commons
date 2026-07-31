# Repository Workflow

This repository uses `master` as the canonical base branch for pull requests.

## CI validation

`Validate GitHub Actions` is limited to standalone action metadata matching
`.github/actions/**/action.yml`. Changes outside that path, including changes
under `.github/workflows/`, do not trigger this workflow and are not included
in its validation scope.

Pull requests targeting `master` run YAML syntax validation only. The
`GrantBirki/json-yaml-validate@v5` action parses the matching metadata files and
fails when their YAML is invalid. It does not apply the action metadata schema
on pull requests.

Pushes to `master` run schema validation only. The workflow uses
`dsanders11/json-schema-validate-action` 2.1.0, pinned to commit
`f04ef3bca791388d2bd9ff3a50b27d1b2572158e`, to validate each matching YAML file
against SchemaStore's `github-action.json`. The schema is pinned to SchemaStore
commit `d9d98e69894ebd7a50965dc58d61951e9d7f23a7` so validation does not change when
the upstream schema changes.

The workflow requires no repository secrets, has only `contents: read`
permission, and publishes no artifacts. If a pull request check fails, inspect
the YAML syntax reported for the named action metadata file. If the push check
fails, inspect the schema validation path and compare the metadata with GitHub's
action metadata syntax. Workflow-only changes require separate static review
because they intentionally do not trigger this action-metadata workflow.
