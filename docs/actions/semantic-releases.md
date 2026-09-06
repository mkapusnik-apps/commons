# Shared Action Releases

## Purpose

Consumers need immutable releases and convenient compatible references.
The repository publishes patch releases automatically.
An operator publishes a new major when compatibility requires it.

## Published content

`.github/semantic-release/actions.json` is the canonical release scope.
Each `actionDirectories` entry identifies one exposed root-level action.
Every file and Git object mode below those directories is published content.

`sharedPaths` identifies repository runtime dependencies shared by published actions.
The list is empty because no current action loads a shared repository runtime dependency.

The publisher compares the union of the scope at the latest release and the scope at the target.
This comparison detects additions, removals, content changes, and mode changes.
It does not include workflows, release automation, declarations, or documentation outside an action directory.

## Automatic patches

Every push to `master` starts the automatic publisher.
The publisher finds the highest published stable `vMAJOR.MINOR.PATCH` release.
It compares scoped Git tree entries at that release and at the pushed revision.
The commits do not need an ancestry relationship.

Identical scoped content produces a successful no-op.
Changed scoped content produces exactly `vMAJOR.MINOR.(PATCH+1)`.
The release and immutable tag identify the pushed revision.
The compatible floating `vMAJOR` tag moves to that revision.

The publisher does not infer API changes.
Pull requests do not include release declarations.
An incompatible change must use the manual major workflow after merge.
The automatic patch still applies when that merge changes scoped content.
The manual major then creates a new compatibility line at current `master`.

## Manual majors

An operator dispatches `Publish Major Release` from current `master`.
The operator supplies the full current `master` SHA.
The confirmation must be `PUBLISH NEXT MAJOR AT <target_sha>`.

The workflow derives `N+1` from the highest published stable major `N`.
It publishes immutable `v(N+1).0.0` at the target.
It creates `v(N+1).0` as a fixed reference to that initial release.
It creates `v(N+1)` as the floating compatible reference for the new major.

The operator cannot select an arbitrary version.
The workflow does not use a GitHub Environment.
Publishing a new major does not move an earlier floating major.

## Compatibility references

- `vMAJOR.MINOR.PATCH` semantic tags are immutable.
- `vN.0` identifies the initial release of major `vN` and never moves.
- `vN` moves forward to the highest published release in major `vN`.
- A full commit SHA gives consumers an immutable source reference.
- Consumers must not use `master` as a production version.

The existing `v1.0` tag remains fixed at `v1.0.0`.
Automatic v1 patches move only `v1`.

## Safety and retry behavior

Patch and major publications share one concurrency group.
GitHub may replace a pending manual-major run when a newer automatic run enters that group.
The operator must re-dispatch the manual workflow against current `master` when this happens.
The publisher creates immutable and fixed tags without force.
It updates a floating major with a lease from a recognized earlier release.
It rejects backward moves and unknown floating targets.

The publisher creates a draft release before it moves the floating major.
It publishes the draft only after all required tags identify the target.

The automatic publisher accepts one exact incomplete next-patch tag.
The partial target must contain a scoped change from the latest stable release.
The GitHub release must be absent or draft.
The floating major must identify the latest stable release or the partial target.

If current `master` supersedes the partial target, its run completes the partial release first.
It does not move the immutable tag.
It then compares the recovered target tree directly with current `master`.
An additional scoped change produces the following patch.
No additional scoped change produces no second release.
If the partial release became published before failure, the next run verifies it and continues from it.

A retry of the superseded run may complete its exact partial release.
It cannot start a release from a stale revision.
Unknown, conflicting, multiple, or non-patch partial states fail closed.
The manual major workflow does not recover an automatic partial release.

## History reset transition

The latest stable release is currently `v1.0.3`.
Tree comparison does not require `v1.0.3` to be an ancestor of current `master`.
Current `master` has an unreleased `setup-flutter/action.yml` change.
The first `master` push running the new publisher therefore publishes the complete scoped target as `v1.0.4`, even when the activating commit changes only release automation.
