# Automatic Semantic Releases

## Purpose

Consumers of the shared actions need immutable versions for reproducibility and floating major versions for compatible updates. After the initial `v1.0.0` release exists, each qualifying push to `master` publishes one ordered semantic version without manual release scheduling.

## Qualifying publication

- A push whose target is `refs/heads/master` qualifies for publication.
- One push is one publication unit, including when the push contains multiple commits.
- Tag events, release events, pushes to other branches, and manual scheduling do not create another publication.
- Reprocessing the same pushed head revision resumes or confirms its existing publication; it does not allocate another version.
- Closely spaced qualifying pushes are published in order. A later push must not overtake an earlier unpublished push.
- Classification covers all repository changes since the preceding successfully published immutable version. This ensures that a previous failed publication cannot cause changes to be omitted.

Creating the initial `v1.0.0`, including its `v1` floating tag, is a prerequisite and is not part of this capability.

## Version classification

Starting from the preceding immutable version `vX.Y.Z`, evaluate the following rules in order and use the first match:

1. **Major:** if the public API of any published shared action changes, publish `v(X+1).0.0`.
2. **Minor:** otherwise, if changes affect two or more distinct published shared-action directories, publish `vX.(Y+1).0`.
3. **Patch:** otherwise, publish `vX.Y.(Z+1)`.

Consequently, a non-API change in exactly one action directory is a patch, as is a change outside all action directories. Multiple files in one action directory still count as one affected action. A major change takes precedence regardless of how many action directories are affected.

The version-controlled shared-action catalog defines which directories count as published actions. Classification uses the complete change set for the publication, not commit-message wording or the number of commits.

## Public API classification

The public API includes:

- consumer-facing action paths;
- inputs and outputs, including requiredness and defaults;
- supported consumer-visible runtime contract;
- documented externally observable behavior, outcomes, and failure behavior.

Removing or renaming an action, or changing its consumer path, is an API change. Any other change that alters this public contract is also an API change.

API and affected-action classification must be deterministic, version-controlled, and reproducible for the same repository change. When a behavioral API change cannot be identified unambiguously from the changed contract, the change must carry a validated, machine-readable classification. Missing, invalid, or contradictory classification must block publication rather than silently select a lower version.

## Completed publication

A publication is complete only when all of the following identify the pushed head revision:

- a newly allocated immutable `vMAJOR.MINOR.PATCH` tag;
- the GitHub release corresponding to that immutable tag;
- the floating `vMAJOR` tag for the newly published major.

An immutable semantic-version tag is never moved, reused, or allocated to another revision. A floating major tag moves to the latest successfully published revision in its own major. Publishing a new major creates or updates that major's floating tag without moving floating tags for earlier majors.

## Retry, conflict, and failure behavior

- Retrying the same revision is idempotent, including after only part of its publication completed.
- Existing publication resources for that revision are reused or completed where safe.
- If an expected immutable version already identifies a different revision, publication fails as a conflict and does not move that tag.
- A run must not report successful publication while the immutable tag, release, and applicable floating tag are inconsistent.
- Failures identify the affected revision and publication outcome clearly enough for a retry; a retry must not silently change the previously determined classification.
- Overlapping publications must not create duplicate, skipped, reversed, or conflicting versions.

## Out of scope

- Creating the initial `v1.0.0` release and `v1` floating tag.
- Updating downstream repositories to consume a newly published version.
- Pre-release channels, manual release scheduling, or manual version selection.
- Defining release-note content beyond creating the corresponding GitHub release.
- Changing the behavior or public interface of an individual shared action as part of release automation.

## Acceptance criteria

- **HP-28-AC-01:** Each qualifying push to `master` produces exactly one publication for its pushed head revision; a multi-commit push still produces only one publication, and non-qualifying events produce none.
- **HP-28-AC-02:** From `vX.Y.Z`, an API change produces `v(X+1).0.0`, including when the same change affects multiple action directories.
- **HP-28-AC-03:** From `vX.Y.Z`, non-API changes affecting at least two distinct published action directories produce `vX.(Y+1).0`.
- **HP-28-AC-04:** From `vX.Y.Z`, a non-API change affecting exactly one published action directory produces `vX.Y.(Z+1)`.
- **HP-28-AC-05:** From `vX.Y.Z`, a change affecting no published action directory produces `vX.Y.(Z+1)`.
- **HP-28-AC-06:** Classification considers the complete change set since the preceding successful immutable publication and follows major-before-minor-before-patch precedence.
- **HP-28-AC-07:** A completed publication's immutable tag, GitHub release, and applicable floating major tag all identify the pushed head revision.
- **HP-28-AC-08:** Existing immutable tags never move, and publishing a new major does not move floating tags for earlier majors.
- **HP-28-AC-09:** Reprocessing a revision, including after a partial failure, completes or confirms the same version without creating another version or changing its classification.
- **HP-28-AC-10:** Closely spaced qualifying pushes publish in order without duplicate, skipped, reversed, or conflicting versions.
- **HP-28-AC-11:** API-change and affected-action classification are deterministic and version-controlled; absent, invalid, or ambiguous required classification blocks publication.
- **HP-28-AC-12:** Publication failures visibly identify the affected revision and failed outcome, do not report an inconsistent publication as successful, and allow a safe retry.
- **HP-28-AC-13:** Contributor documentation explains the qualifying event, version precedence, public API boundary, affected-action counting, declaration requirement, and retry behavior.
