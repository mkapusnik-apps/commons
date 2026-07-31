# Repository Workflow

This repository uses `master` as the canonical base branch for pull requests.

## CI validation

The action metadata validation is split by trigger into `Validate GitHub Actions
(Pull Request)` and `Validate GitHub Actions (Push)`. Both workflows are limited
to standalone action metadata matching `*/action.yml` in root-level action directories. Changes
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

## Semantic release declaration validation

`Validate Semantic Release (Pull Request)` runs for every pull request targeting
`master`. Its `Validate release declaration` job compares the pull request base
and head with the same version-controlled classification rules used by the
publisher. It has `contents: read` permission, persists no checkout credential,
and publishes no artifact.

Every pull request must add an append-only JSON file under
`.github/semantic-release/declarations/`. Use a unique lowercase slug for the
filename and this exact schema:

```json
{
  "schema": 1,
  "apiChange": false
}
```

Set `apiChange` to `true` when any changed action has a consumer-facing API
change. The API boundary includes its path, inputs, outputs, requiredness,
defaults, consumer-visible runtime contract, and documented externally
observable behavior or failure behavior. Removing or renaming an action is an
API change. Declarations cannot be edited or deleted after publication. A
missing declaration, an edited or deleted declaration, an invalid schema, or a
range whose declarations are otherwise unusable fails closed. A multi-commit
publication range may contain multiple new declarations; they are all validated
and any `apiChange: true` declaration gives the whole publication major
precedence. A registry change with no `true` declaration also fails closed.
Before delivery, contributors can run the same local classifier against the
pull request base with:

```sh
node .github/scripts/semantic-release.js validate-worktree <base-commit-sha>
```

`.github/semantic-release/actions.json` is the canonical catalog used to count
affected action directories. It must remain sorted and each entry must identify
a root-level directory containing `action.yml`. Multiple files in one registered
directory count once. A non-API change in at least two registered directories is
minor; a non-API change in one or zero is patch; `apiChange: true` is always
major. Update the catalog and declare `apiChange: true` when adding, removing,
renaming, or moving a published action.

## Automatic publication

`Publish Semantic Release` runs only for branch push events targeting `master`.
The `Publish semantic release` job treats the event's pushed head as one
publication unit, so a multi-commit push still allocates one version. Tag,
release, pull-request, other-branch, and scheduled events do not trigger it.
It needs only `contents: write` to create refs and GitHub releases and publishes
no workflow artifact.

The publisher compares the complete repository trees from the preceding
successfully published immutable release to the pushed head. Classification is
major before minor before patch. The bootstrap creates `v1.0.0`, fixed `v1.0`,
floating `v1`, and a stable, non-draft `v1.0.0` GitHub release at the same
canonical `master` revision before this automation is merged. Publication fails
clearly if the successful immutable release or floating-major prerequisite is
missing or inconsistent. Later automatic publications do not move `v1.0`.

Publication uses an immutable version tag, a draft release, and the applicable
floating-major tag. It verifies both refs at the pushed SHA before publishing
the draft, making the published GitHub release the durable completion marker.
Immutable tags are create-only. A floating tag moves only forward within its
own major, so a new major does not move older floating tags.

Runs do not use GitHub Actions concurrency groups because those groups can
replace a pending run and do not guarantee FIFO ordering. Instead, each pushed
revision waits for the exact preceding branch head to have a published immutable
release. This predecessor barrier serializes closely spaced pushes. Concurrent
retries for one revision converge on the same immutable tag and draft release.
A later revision cannot publish until its predecessor's release is complete.

To retry, rerun the failed push workflow from GitHub Actions. Do not create tags
or releases manually for that revision. The rerun reuses a matching immutable
tag or draft release, refuses conflicts, recomputes the same version-controlled
classification, and never moves an immutable tag. Logs and the job summary
include the full revision, classification/publication outcome, and version when
allocated. Common blocking failures are a missing prerequisite release, a
missing or ambiguous declaration, an invalid registry, an immutable-tag
conflict, an unrecognized floating tag, or a predecessor that did not finish
within the wait period.
