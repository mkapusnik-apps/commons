# Shared Flutter runtime images

## Purpose and support

Shared prebuilt runtimes let consumers verify Flutter applications without first building a project-specific toolchain image.

- **FR-SUPPORT-01:** The images must support Linux AMD64 execution.
- **FR-SUPPORT-02:** The lightweight image must support Dart and Flutter formatting, analysis, code generation, and unit and widget tests.
- **FR-SUPPORT-03:** The lightweight image must provide its supported workloads without installation of the complete Android build toolchain.
- **FR-SUPPORT-04:** The full image must provide all lightweight workloads and Flutter Android APK and AAB builds.
- **FR-SUPPORT-05:** Both images must support execution with an arbitrary non-root UID when the consumer supplies the documented writable SDK and cache locations.
- **FR-SUPPORT-06:** The images must not contain credentials or project-specific state.

The Android support set includes JDK 21, SDK platforms 34, 35, and 36, Build Tools 35.0.0 and 36.0.0, NDK 28.2.13676358, and CMake 3.22.1. Android command-line tools and platform-tools are also required. The support set describes supported consumer requirements, not a claim that every combination of tool versions is compatible.

- **FR-ANDROID-01:** The full image must provide the Android support set and the Flutter Android artifacts required by supported builds.
- **FR-ANDROID-02:** Each refresh must evaluate the Android tool set against the selected Flutter release and supported consumers' SDK, build-tools, NDK, CMake, JDK, and Gradle requirements.
- **FR-ANDROID-03:** The tool selection policy must retain multiple required versions when this prevents toolchain downloads for supported consumers.
- **FR-ANDROID-04:** Consumers must not need to change their SDK targets to use the documented support set.
- **FR-ANDROID-05:** A refresh must not promote candidates that cannot satisfy the documented support set with the selected Flutter release.

## Toolchain readiness and provenance

- **FR-READY-01:** Image construction must complete toolchain installation, required Flutter artifact caching, and applicable noninteractive setup before publication.
- **FR-READY-02:** A fresh lightweight container must run its supported workloads without downloading missing Flutter SDK artifacts.
- **FR-READY-03:** A fresh full container must build supported APK and AAB artifacts without downloading missing Android SDK, platform, build-tools, NDK, CMake, or Flutter engine components covered by the support set.
- **FR-READY-04:** Consumer documentation must distinguish project-specific Pub, Maven, and Gradle dependency downloads from toolchain downloads.
- **FR-BASE-01:** The images must use the most authoritative suitable upstream base available.
- **FR-BASE-02:** The base selection must prefer a suitable upstream-maintained official Flutter image when one is available.
- **FR-BASE-03:** If no suitable official Flutter image is available, the base selection must prefer an official operating-system image with Flutter from its official upstream distribution.
- **FR-BASE-04:** Consumer documentation must identify the selected base and explain its provenance and selection rationale.
- **FR-BASE-05:** Consumer documentation must not describe a third-party Flutter image as official.
- **FR-BASE-06:** Image preparation must avoid upgrading a stale, fully provisioned Flutter image when that duplicates SDK preparation and cached artifacts.

Readiness takes priority over minimum image size. These images do not guarantee dependency-free cold builds for arbitrary applications.

## Refresh and publication

- **FR-RELEASE-01:** Publication automation must provide one scheduled refresh per week and an operator-triggered manual refresh.
- **FR-RELEASE-02:** Each refresh must resolve the latest stable Flutter release available at build time without a fixed Flutter version in repository configuration.
- **FR-RELEASE-03:** Both variants in a publication must use the same resolved Flutter release.
- **FR-RELEASE-04:** Each refresh must rebuild and publish both variants even when the stable Flutter release has not changed.
- **FR-RELEASE-05:** Each published variant must expose the resolved Flutter version, Dart version, Flutter revision, and included toolchain versions for diagnostics.
- **FR-RELEASE-06:** Recorded versions must not prevent automatic upgrades during later refreshes.
- **FR-RELEASE-07:** Consumers must have documented public GHCR floating references for the lightweight and full variants.
- **FR-RELEASE-08:** Each publication must provide immutable references or digests that identify both variants as members of the same build.
- **FR-RELEASE-09:** Both candidates must pass validation before either advertised floating reference advances.
- **FR-RELEASE-10:** A failed candidate build or validation must leave existing working floating references unchanged.
- **FR-RELEASE-11:** A failed refresh must leave the last successful published variants available.
- **FR-RELEASE-12:** Refresh failures must appear in normal CI results.
- **FR-RELEASE-13:** Consumer documentation must explain that floating-reference promotion is not transactional across the two variants.
- **FR-RELEASE-14:** Consumer documentation must explain how consumers select a matching immutable pair when floating references temporarily identify different publications.
- **FR-RELEASE-15:** Operator documentation must describe recovery from partial promotion without advertising an unvalidated candidate.

The matching-version guarantee applies to a publication pair. It does not promise that two independent floating-reference pulls always observe that pair during promotion. Container publication is separate from the [shared action release contract](../actions/semantic-releases.md).

## Consumer documentation

- **FR-DOCS-01:** Consumer documentation must provide pull and run examples for each variant and its intended workloads.
- **FR-DOCS-02:** Consumer documentation must identify the supported architecture, weekly update policy, registry references, included tool versions, and Android tool selection policy.
- **FR-DOCS-03:** Consumer documentation must describe required writable locations and cache mounts for supported non-root execution.
- **FR-DOCS-04:** Consumer documentation must identify remaining first-run downloads and the limits of the supported workloads.

## Acceptance criteria

Each criterion below verifies the linked requirements; it does not define a separate behavior contract.

| Criterion | Requirements | Required observation |
| --- | --- | --- |
| FR-AC-01 | FR-SUPPORT-01, FR-RELEASE-07, FR-RELEASE-08, FR-DOCS-01 | Both AMD64 variants are published and can be pulled from the documented registry references; pull/run examples identify their workloads and immutable publication pair. |
| FR-AC-02 | FR-RELEASE-01 through FR-RELEASE-06 | Hosted refresh results show dynamic stable resolution, matching Flutter/Dart versions and revision, and toolchain metadata for both variants; the weekly schedule and manual trigger are available, and an unchanged Flutter release does not skip rebuilding either variant. |
| FR-AC-03 | FR-SUPPORT-02, FR-SUPPORT-03, FR-READY-01, FR-READY-02 | A fresh lightweight container completes representative formatting, analysis, code generation, and unit/widget checks without Android installation or missing Flutter SDK artifact downloads. |
| FR-AC-04 | FR-SUPPORT-04, FR-ANDROID-01 through FR-ANDROID-05, FR-READY-01, FR-READY-03, FR-READY-04 | Fresh full-container checks produce APK and AAB artifacts; the workload coverage identifies the supported consumer requirements exercised, the included tool set, and any downloads, with project dependencies reported separately. |
| FR-AC-05 | FR-SUPPORT-05, FR-SUPPORT-06, FR-DOCS-03 | Representative checks succeed under an arbitrary non-root UID with documented writable locations and mounts; an image-content assessment finds no embedded credentials or project-specific state. |
| FR-AC-06 | FR-BASE-01 through FR-BASE-06, FR-DOCS-02, FR-DOCS-04 | Documentation and build provenance identify the base, official Flutter source, selection rationale, update policy, architecture, Android tool policy, included versions, and remaining first-run downloads. |
| FR-AC-07 | FR-RELEASE-09 through FR-RELEASE-15 | Controlled failure results show that a failed candidate build or check leaves working floating references unchanged and previous variants available; promotion results and recovery documentation identify nontransactional behavior and never advertise an unvalidated candidate. |

### Review readiness and operational acceptance

Review readiness and final operational acceptance are separate gates. Review readiness does not authorize merge or production publication.

- **FR-GATE-01:** Review readiness must include validated, publicly pullable immutable candidates for both variants, with evidence tied to the implementation checkpoint and image digests.
- **FR-GATE-02:** Review readiness must include the applicable workload, non-root, documentation, provenance, and measurement evidence for FR-AC-03 through FR-AC-06 and FR-EVIDENCE-01 through FR-EVIDENCE-03.
- **FR-GATE-03:** Review readiness must include a controlled isolated rehearsal of the publication validation gate, with the failure condition and reference state recorded before and after the attempt.
- **FR-GATE-04:** Review readiness must identify unobserved operational criteria as pending, with an evidence plan for completion after default-branch registration.
- **FR-GATE-05:** Missing default-branch-only observations must not, by themselves, block review readiness.
- **FR-GATE-06:** Final operational acceptance must satisfy all FR-AC criteria with evidence for the deployed publication behavior.

For FR-GATE-03, an absent-candidate rejection that leaves isolated references unchanged can demonstrate the bounded rejection path. It does not demonstrate preservation of existing working production floating references or recovery from partial promotion. A rehearsal must not require mutation of working production references.

The following observations remain pending until operational evidence is available:

| Criterion | Operational evidence still required |
| --- | --- |
| FR-AC-01 | Public pulls from both advertised production floating references and identification of their immutable publication pair. |
| FR-AC-02 | Hosted scheduled and manual refresh results, including a refresh that rebuilds both variants when the resolved Flutter release is unchanged. |
| FR-AC-07 | Failure evidence that starts with existing working references and shows their preservation and continued availability; hosted promotion outcomes and documented partial-promotion recovery. |

An authorized isolated hosted rehearsal of the deployed publication behavior may supply failure and partial-promotion evidence without disrupting consumer references. Such evidence must identify the behavior exercised and its correspondence to the deployed publication path. Absent production references or a successful candidate build alone cannot satisfy these operational observations. This gate distinction does not require a destructive production failure or change the nontransactional promotion contract.

### Evidence and measurements

- **FR-EVIDENCE-01:** Verification must record image build time and representative fresh-container startup and check times.
- **FR-EVIDENCE-02:** Verification must report image-pull cost separately from preparation and execution inside the container.
- **FR-EVIDENCE-03:** Verification must identify runtime toolchain downloads separately from project dependency downloads.

These measurements establish observable preparation cost; they do not impose a numeric performance threshold. Credential-free synthetic projects may represent supported workloads without copying private consumer projects. Shared image refreshes do not require rebuilding images for every application change.

For final acceptance, evidence must identify the immutable implementation checkpoint, image digests, workload and tool versions, execution UID and mounts, cache conditions, observations, and applicable acceptance criterion. Hosted publication evidence must include consumer pull results and promotion outcomes. Evidence for failure behavior must identify the failure condition and reference state before and after the attempt.

## Boundaries

The shared runtime offering includes image definitions, publication automation, consumer documentation, and focused image checks. It does not require consumer runtime-manifest migrations, emulator provisioning, device-farm provisioning, other architectures, or a change to shared GitHub Action version tags. It does not promise that arbitrary applications build without dependency downloads.
