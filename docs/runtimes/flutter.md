# Shared Flutter runtime images

## Purpose and supported use

Provide two shared Flutter images with minimal configuration: `slim` for Linux Flutter development tools and `full` for Android builds. Standard upstream distributions and native tool caching are sufficient; this offering does not certify application workloads or offline execution.

- **FR-SUPPORT-01:** Both images must support Linux AMD64 execution.
- **FR-SUPPORT-02:** The slim image must provide the tools and host libraries for Dart and Flutter formatting, analysis, code generation, and unit and widget tests.
- **FR-SUPPORT-03:** The slim image must not require the complete Android build toolchain.
- **FR-SUPPORT-04:** The full image must provide the slim capabilities and the toolchain for Flutter Android APK and AAB builds.
- **FR-SUPPORT-07:** Both images must use an ordinary non-root user by default.
- **FR-SUPPORT-08:** The default image user must have writable SDK and cache locations.
- **FR-SUPPORT-09:** The images must not embed operator secrets, application secrets, or private consumer project state.

Known public upstream test fixtures are not operational secrets. They may remain in official distributions, including public test keys. There is no claim that every image layer is free of all private-key-shaped content. Additional numeric UIDs require the documented ownership or group convention; arbitrary UID/GID combinations are not guaranteed.

## Image contents and preparation

The full image's Android inventory is JDK 21, command-line tools, platform-tools, SDK platforms 34/35/36, Build Tools 35.0.0/36.0.0, NDK 28.2.13676358, and CMake 3.22.1. This inventory does not certify every combination of project dependencies and tool versions.

- **FR-ANDROID-01:** The full image must install the documented Android inventory and pre-cache Flutter Android artifacts with native tool commands.
- **FR-ANDROID-04:** Consumers must not need to change their SDK targets to use the documented inventory.
- **FR-READY-01:** Image construction must perform native toolchain installation, Flutter pre-caching, and applicable noninteractive setup.
- **FR-READY-04:** Consumer documentation must distinguish toolchain downloads from project-specific Pub, Maven, and Gradle dependency downloads.
- **FR-BASE-01:** The images must use an authoritative suitable upstream base.
- **FR-BASE-04:** Consumer documentation must identify the base and the official Flutter distribution source.
- **FR-BASE-05:** Consumer documentation must not describe a third-party Flutter image as official.

Native caches reduce preparation work but do not guarantee zero downloads. Project dependencies, cache misses, and tools outside the documented inventory may require downloads. Image size is secondary to ordinary toolchain readiness.

## Approved delivery constraints

The following constraints record the approved request; implementation details beyond these constraints remain with the implementation roles.

- **FR-DELIVERY-01:** Each variant must have its own standard Dockerfile.
- **FR-DELIVERY-02:** The full build must derive from the slim image built in the same run.
- **FR-DELIVERY-03:** Pull requests must use a separate build-only workflow that does not publish images.
- **FR-DELIVERY-04:** Weekly and manual publication must use a separate workflow that builds from `master`.
- **FR-DELIVERY-05:** The workflows must not combine pull-request and publication behavior through per-job event conditions.

## Refresh and publication

- **FR-RELEASE-01:** Publication automation must provide one scheduled refresh per week and an operator-triggered manual refresh.
- **FR-RELEASE-02:** Each refresh must resolve the latest stable Flutter release once without a fixed Flutter release in repository configuration.
- **FR-RELEASE-03:** Both variants in a publication must use the same resolved Flutter release.
- **FR-RELEASE-04:** Each refresh must rebuild and publish both variants even when the stable Flutter release has not changed.
- **FR-RELEASE-05:** Each published variant must expose the resolved Flutter version, Dart version, Flutter revision, and included toolchain versions for diagnostics.
- **FR-RELEASE-06:** Recorded versions must not prevent automatic upgrades during later refreshes.
- **FR-RELEASE-07:** Consumers must have documented public GHCR floating references named `slim` and `full`.
- **FR-RELEASE-08:** Each publication must provide digests that identify both variants as members of the same build.
- **FR-RELEASE-16:** Both image builds must succeed before the publication workflow publishes either variant's unique build reference or floating reference.
- **FR-RELEASE-17:** A failed image build must leave existing published references unchanged.
- **FR-RELEASE-11:** A failed refresh must leave the last successful published variants available.
- **FR-RELEASE-12:** Refresh failures must appear in normal CI results.
- **FR-RELEASE-13:** Consumer documentation must explain that floating-reference publication is not transactional across the two variants.
- **FR-RELEASE-14:** Consumer documentation must explain how to select a matching digest pair when floating references identify different publications.

Unique build references identify each run; digest references provide immutable identity. A partial publication may update only one floating reference. Automated rollback, publication failure injection, and a custom promotion framework are not required. Container publication remains separate from shared GitHub Action version tags.

## Documentation

- **FR-DOCS-01:** Consumer documentation must provide pull and run examples for both variants and their intended workloads.
- **FR-DOCS-02:** Consumer documentation must identify AMD64 support, the weekly update policy, registry references, included tool versions, and the Android inventory policy.
- **FR-DOCS-03:** Consumer documentation must describe writable locations and the ownership or group convention for additional numeric UIDs.
- **FR-DOCS-04:** Consumer documentation must identify possible first-run downloads and the limits of the supported use.

## Acceptance and review readiness

| Criterion | Evidence sufficient for the criterion |
| --- | --- |
| **FR-AC-08** | Successful PR Docker builds of slim and full, tied to the reviewed source checkpoint, establish the required build sanity check. |
| **FR-AC-09** | Source and documentation review confirms the two Dockerfiles, full inheritance from the same-run slim image, separate workflows, no PR publication, default non-root user, native installation/pre-caching, Android inventory, and exclusion of operator/application secrets and private project state. |
| **FR-AC-10** | Source and documentation review confirms weekly/manual master publication, one dynamic stable resolution, rebuilding both variants without a version-change condition, build-before-publish ordering, references, metadata, and nontransactional publication limits. |
| **FR-AC-11** | An authorized successful publication records both variants' unique and floating references and digests; ordinary public pulls confirm registry availability. |

- **FR-GATE-07:** Review readiness must require FR-AC-08 through FR-AC-10 only.
- **FR-GATE-08:** PR runtime sanity must require only successful Docker builds of both images.
- **FR-GATE-09:** Publication availability under FR-AC-11 must remain pending until an authorized publication occurs.

No application test matrix, internal implementation tests, independent layer scan, arbitrary-UID certification, zero-download audit, performance benchmark, or failure-injection rehearsal is required. Source review is sufficient for schedule wiring and unchanged-version rebuild behavior; observed scheduled execution and repeated refreshes are not acceptance prerequisites. Review readiness does not authorize merge or production execution.

## Non-goals

This offering does not require consumer manifest migration, emulator or device-farm provisioning, additional architectures, legacy `lightweight` aliases, custom SDK sanitizers, modified Git object stores, a private Flutter engine mirror, or a bespoke runtime validation framework.
