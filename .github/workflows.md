# Repository Workflow

This repository uses `master` as the canonical base branch for pull requests.

## CI validation

The action metadata validation is split by trigger into `Validate GitHub Actions
(Pull Request)` and `Validate GitHub Actions (Push)`. Both workflows are limited
to standalone action metadata matching `.github/actions/**/action.yml`. Changes
outside that path, including changes under `.github/workflows/`, do not trigger
either workflow and are not included in their validation scope.

Pull requests targeting `master` run YAML syntax validation only. The
`GrantBirki/json-yaml-validate@v5` action parses the matching metadata files and
fails when their YAML is invalid. It does not apply the action metadata schema
on pull requests. Gitignore processing is disabled so an explicitly matched
metadata file cannot be skipped by `.gitignore`, and multiple YAML documents
remain allowed.

Each job first requires at least one regular file to match the metadata glob.
This is a fail-closed scope guard: version 5 of the validator falls back to
recursively discovering YAML from `base_dir` when its explicit `files` input has
no matches. Without the guard, deleting all standalone action metadata could
make either action inspect unrelated YAML, including workflow files.

Pushes to `master` run schema validation only. The push workflow also uses
`GrantBirki/json-yaml-validate@v5`, treating the matching YAML files as JSON and
validating them with the draft-07 SchemaStore `github-action.json` schema.
`actions/checkout@v7` checks out that schema locally from immutable SchemaStore
commit `d9d98e69894ebd7a50965dc58d61951e9d7f23a7`, so validation does not change
when the upstream schema changes. This replaces
`dsanders11/json-schema-validate-action`: that action does not publish a stable
major tag, so it cannot satisfy the repository's `owner/action@vN` convention.
Gitignore processing is disabled and multiple YAML documents remain allowed.
AJV strict mode is disabled because its strict type checks reject constructs in
the pinned draft-07 schema before metadata validation can run; the schema itself
remains fully applied to each YAML document.

The workflows require no repository secrets, have only `contents: read`
permission, and publish no artifacts. If a pull request check fails, inspect the
YAML syntax reported for the named action metadata file. If the push check
fails, inspect the schema validation path and compare the metadata with GitHub's
action metadata syntax. Workflow-only changes require separate static review
because they intentionally do not trigger these action-metadata workflows.
