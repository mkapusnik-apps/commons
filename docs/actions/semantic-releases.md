# Automatic Semantic Releases

## Purpose

Consumers of the shared actions need immutable versions for reproducibility and floating major versions for compatible updates. The initial stable release bootstraps those references from canonical `master`; afterward, each qualifying push to `master` publishes one ordered semantic version without manual release scheduling.

## Qualifying publication

- A push whose target is `refs/heads/master` qualifies for publication.
- One push is one publication unit, including when the push contains multiple commits.
- Tag events, release events, pushes to other branches, and manual scheduling do not create another publication.
- Reprocessing the same pushed head revision resumes or confirms its existing publication; it does not allocate another version.
- Closely spaced qualifying pushes are published in order. A later push must not overtake an earlier unpublished push.
- Classification covers all repository changes since the latest completed immutable release in the pushed revision's `master` history. It does not require the push event's exact previous revision to have its own release. This ensures that activation gaps and previous failed publications cannot cause changes to be omitted.

## Initial stable bootstrap

The activation baseline is canonical `master` commit `1a26ddc0defdd944902e58f1e428548a4ceca90e`. Create `v1`, `v1.0`, and `v1.0.0` at exactly that revision, then publish a stable, non-draft GitHub release for `v1.0.0` at the same revision before enabling the automation. This bootstrap identifies the existing reviewed shared-action implementation; it does not claim that the issue #28 automation is active at the bootstrap revision.

The first automated publication uses this completed baseline even when commits between the baseline and the first qualifying pushed head have no immutable release. It publishes the pushed head once and classifies the complete baseline-to-head change set.

The three initial references have distinct compatibility contracts:

- `v1.0.0` is the immutable semantic-version tag and must never move.
- `v1.0` is a fixed minor-series reference for the initial stable release and must never move.
- `v1` is the floating major reference and moves forward to the latest successfully published compatible v1 release.

## 2026 history reset bridge

The repository history reset created root commit `43b3c2c240d706eddb4801d637c108502d49f279`. Its tree is identical to historical tip `7e4573b0f9e0d81262d4a0435b2dbfa735181452`. Both commits use tree `003b409091678825a815b966442919c8a38ef35d`.

The one-time bootstrap publishes patch release `v1.0.4` at the verified current `master` revision. It bridges the completed `v1.0.3` release at `17556b1efbed0bceffc8d3246bbc06fb8cbaef71` into the reset history. It does not change historical immutable releases or fixed `v1.0`.

The workflow requires the protected `release-baseline-reset-2026` Environment, which must require an independent reviewer, prevent self-review, and allow deployments only from `master`. An operator must supply the full current `master` SHA and the fixed confirmation phrase. The workflow determines the version from the expiring authorization manifest.

The bootstrap validates all release resources before each change. It accepts only the initial state, one of its ordered partial states, or the complete state. A retry resumes an exact partial state. A conflict stops all later changes.

The authorization expires at `2026-09-26T23:59:59Z`. After expiry, the workflow can complete an exact partial publication but cannot start a new publication. The published release body contains the authorization and workflow audit metadata.

Remove the temporary bootstrap workflow after `v1.0.4` is complete. Retain the manifest as the authorization record.

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

The fixed bootstrap reference `v1.0` is not part of later automatic publications and remains at `v1.0.0`.

## Retry, conflict, and failure behavior

- Retrying the same revision is idempotent, including after only part of its publication completed.
- Existing publication resources for that revision are reused or completed where safe, without allocating a later version.
- A retry resumes the same version when the immutable tag or floating major tag already moved to the revision but the GitHub release was not published. It completes the missing release instead of treating that partial version as the predecessor for a new allocation.
- A partial publication is not a completed predecessor for any later revision. Later qualifying revisions remain blocked until the earlier publication is completed or its conflict is resolved.
- If an expected immutable version already identifies a different revision, publication fails as a conflict and does not move that tag.
- A floating-tag update uses the observed ref SHA as an atomic lease. A concurrent change rejects the update instead of overwriting the new ref.
- A completed-revision no-op must be a forward push to the latest completed publication. An older published revision remains invalid.
- A run must not report successful publication while the immutable tag, release, and applicable floating tag are inconsistent.
- Failures identify the affected revision and publication outcome clearly enough for a retry; a retry must not silently change the previously determined classification.
- Overlapping publications must not create duplicate, skipped, reversed, or conflicting versions.

## Out of scope

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
- **HP-28-AC-06:** Classification considers the complete change set since the latest completed immutable release in the pushed head's `master` history and follows major-before-minor-before-patch precedence; the event's exact previous revision need not have a release.
- **HP-28-AC-07:** A completed publication's immutable tag, GitHub release, and applicable floating major tag all identify the pushed head revision.
- **HP-28-AC-08:** Existing immutable tags never move, and publishing a new major does not move floating tags for earlier majors.
- **HP-28-AC-09:** Reprocessing a revision, including after a partial failure, completes or confirms the same version without creating another version or changing its classification. This includes a failure after the floating major tag moved but before the GitHub release was published.
- **HP-28-AC-10:** Closely spaced qualifying pushes publish in order without duplicate, skipped, reversed, or conflicting versions.
- **HP-28-AC-11:** API-change and affected-action classification are deterministic and version-controlled; absent, invalid, or ambiguous required classification blocks publication.
- **HP-28-AC-12:** Publication failures visibly identify the affected revision and failed outcome, do not report an inconsistent publication as successful, and allow a safe retry.
- **HP-28-AC-13:** Contributor documentation explains the qualifying event, version precedence, public API boundary, affected-action counting, declaration requirement, and retry behavior.
- **HP-28-AC-14:** Before automation is enabled, the bootstrap creates `v1`, `v1.0`, and `v1.0.0` at canonical `master` SHA `1a26ddc0defdd944902e58f1e428548a4ceca90e`.
- **HP-28-AC-15:** `v1.0.0` is immutable, `v1.0` remains fixed at the initial stable release, and only `v1` moves forward to later compatible v1 publications.
- **HP-28-AC-16:** The bootstrap publishes a stable, non-draft GitHub release for `v1.0.0` whose tag identifies the captured canonical `master` SHA.
- **HP-28-AC-17:** When unreleased commits exist between the bootstrap and the first qualifying pushed head, the first automated publication succeeds from the bootstrap baseline and publishes one correctly classified version for that head.
- **HP-28-AC-18:** A partial publication is never used as the predecessor of a later pushed revision; sequential and concurrent pushes wait for each earlier publication to complete rather than absorbing, skipping, or reversing it.
- **HP-28-AC-19:** The history reset bootstrap publishes only `v1.0.4` at the verified current `master` SHA after it validates the exact tree bridge and prior release state.
- **HP-28-AC-20:** The history reset bootstrap is idempotent, rejects conflicting partial states, preserves historical immutable tags and fixed `v1.0`, and records audit metadata.
- **HP-28-AC-21:** Expiry blocks a new bootstrap publication but permits completion of an exact partial `v1.0.4` publication.
