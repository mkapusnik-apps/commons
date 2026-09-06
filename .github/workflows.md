# Repository Workflows

This repository uses `master` as the canonical branch.

## Action metadata validation

`Validate GitHub Actions (Pull Request)` runs when a pull request to `master` changes `*/action.yml`.
It validates YAML syntax.

`Validate GitHub Actions (Push)` runs when a push to `master` changes `*/action.yml`.
It validates action metadata against the pinned SchemaStore schema.

Both workflows have `contents: read` permission.
They require no secret and publish no artifact.

If validation fails, inspect the named `action.yml` file.
Workflow-only changes require static review because they do not start these workflows.

## Release scope

`.github/semantic-release/actions.json` defines the exact published content scope.
`actionDirectories` lists the root-level exposed action directories.
All files and Git object modes below each listed directory affect published behavior or metadata.
`sharedPaths` lists runtime files or directories used by more than one published action.
It is currently empty because the actions have no shared repository runtime dependency.

The scope file must list items in lexical order.
Each action directory must contain `action.yml`.
Add a shared runtime dependency to `sharedPaths` before an action uses it.

Pull requests do not require a release declaration.
The workflows do not infer API changes or major versions.
The automatic publisher does not suppress a patch for an incompatible change.

## Automatic patch publication

`Publish Semantic Release` runs after every push to `master`.
It has `contents: write` permission.
It requires no secret, Environment, or artifact.

The publisher finds the highest stable `vMAJOR.MINOR.PATCH` GitHub release.
It reads the Git trees for that tag and the pushed revision.
It compares only the union of the release and target scopes.
It does not compare commit ancestry.

If the release and target scoped content is identical, the workflow succeeds without a release.
If scoped content differs, the workflow publishes `vMAJOR.MINOR.(PATCH+1)` at the pushed revision.
It then moves `vMAJOR` forward to that revision.
It never moves `vMAJOR.MINOR`.

The tree comparison tolerates the 2026 history reset.
It also detects added or removed actions through the union of both scope versions.

## Manual major publication

`Publish Major Release` uses `workflow_dispatch` only.
The operator must dispatch the workflow from current `master`.
The operator must enter the full current `master` SHA as `target_sha`.
The operator must enter `PUBLISH NEXT MAJOR AT <target_sha>` as `confirmation`.

The workflow derives the next major from the highest stable semantic release.
The operator cannot select a version.
It publishes `v(N+1).0.0` at the verified target.
It creates fixed `v(N+1).0` and floating `v(N+1)` tags at the same revision.
Each fixed `vN.0` tag identifies the first release of major `vN` and never moves.
Earlier floating major tags do not move.

The workflow has `contents: write` permission.
It requires no secret, Environment, or artifact.

A new manual publication starts only when `target_sha` is current `master`.
The workflow checks the confirmation before it reads or changes release state.

## Concurrency and retries

Both publishers use the `semantic-release-publication` concurrency group.
One publisher runs at a time.
GitHub may replace an older pending run with a newer pending run.
The newest pending run evaluates the complete scoped tree difference from the latest release.
It therefore publishes the cumulative scoped tree when an older pending run is replaced.
A newer automatic run may also replace a pending manual-major run.
The operator must re-dispatch the manual workflow against current `master` when this happens.

The publisher creates immutable tags without force.
It moves a floating major only from a recognized older release and uses a Git lease.
It rejects immutable conflicts, unknown partial states, unknown floating targets, and backward floating moves.

An automatic run accepts one exact incomplete next-patch tag.
The tag must contain a scoped change from the latest stable release.
Its release must be absent or draft.
Its floating major must identify either the latest stable release or the partial target.

A current `master` run completes that partial release before it evaluates its own target.
It then compares the completed partial target directly with current `master`.
It publishes the following patch only when current `master` has an additional scoped change.
If publication already succeeded, the run verifies that release and uses it as the comparison baseline.

A retry for the superseded target may complete only that exact partial release.
It cannot create a new immutable tag when the target is not current `master`.
Manual major publication remains blocked until an automatic partial release is complete.

### Manual major recovery

Rerun the original manual workflow when `master` advances after a partial major publication.
The rerun retains the authorized target SHA and confirmation from the original dispatch.
A new dispatch cannot select the stale target.

The stale rerun derives the same next major from the latest completed release.
It requires exactly one incomplete immutable tag for that version and target.
The matching fixed tag can be absent or can identify that target.
The draft can be absent or can remain a non-prerelease draft.
The new floating major can be absent or can identify that target.

Resources must follow the order immutable, fixed, draft, and floating.
The rerun creates only missing later resources.
It never rewrites an existing immutable or fixed tag.
It creates the new floating major without force when that tag is missing.
It accepts an existing floating major only at the authorized target.

The automatic workflow does not complete a partial manual major.
Existing GitHub state does not store sufficient dispatch authorization for that action.
An arbitrary next-major tag is not authorization.

After the manual rerun succeeds, rerun the automatic workflow for current `master`.
It uses `v(N+1).0.0` as its completed baseline.
It publishes `v(N+1).0.1` only when current `master` has an additional scoped change.

To retry, rerun the failed workflow.
Do not create tags or releases manually.
Resolve an unknown or conflicting partial state before another publication.
