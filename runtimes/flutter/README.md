# Flutter runtime operations

The [approved specification](../../docs/runtimes/flutter.md) defines the product contract.
This guide describes implementation and operation. Image qualification is incomplete
until the developer-owned validation hook and hosted evidence pass.

## Images and workloads

Both images run on Linux AMD64. Use these public GHCR references after the first
successful publication and package visibility setup:

| Reference | Workload |
| --- | --- |
| `ghcr.io/mkapusnik-apps/commons/flutter:lightweight` | Formatting, analysis, code generation, unit and widget tests |
| `ghcr.io/mkapusnik-apps/commons/flutter:full` | Lightweight workloads plus Android APK and AAB builds |

```sh
docker pull --platform linux/amd64 ghcr.io/mkapusnik-apps/commons/flutter:lightweight
docker pull --platform linux/amd64 ghcr.io/mkapusnik-apps/commons/flutter:full
```

From a Flutter project, create cache directories owned by your execution UID:

```sh
mkdir -p .runtime-cache/home .runtime-cache/pub .runtime-cache/gradle
docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/workspace" \
  --mount "type=bind,src=$PWD/.runtime-cache/home,dst=/home/runtime" \
  --mount "type=bind,src=$PWD/.runtime-cache/pub,dst=/cache/pub" \
  ghcr.io/mkapusnik-apps/commons/flutter:lightweight \
  bash -c 'flutter pub get && flutter analyze && flutter test'

docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/workspace" \
  --mount "type=bind,src=$PWD/.runtime-cache/home,dst=/home/runtime" \
  --mount "type=bind,src=$PWD/.runtime-cache/pub,dst=/cache/pub" \
  --mount "type=bind,src=$PWD/.runtime-cache/gradle,dst=/cache/gradle" \
  ghcr.io/mkapusnik-apps/commons/flutter:full flutter build apk --debug
```

Keep `.runtime-cache` out of consumer version control. Adapt the project command
to its existing dependency, code-generation, and signing requirements. For AAB
builds, use `flutter build appbundle` with the project's signing configuration.
Do not place signing keys or service credentials in an image.

The default UID/GID is `10001:10001`. An arbitrary numeric UID/GID is supported.
The workspace, HOME, Pub cache, and Gradle user home must be writable by that UID.
The image makes `/opt/flutter` and, in full, `/opt/android-sdk` writable inside
the disposable container. Do not use a read-only root filesystem. Do not hide
these preloaded SDK directories with empty mounts. SDK persistence is not required.
If you mount SDK directories, first populate them from the exact image and make
them writable by the execution UID. Do not reuse SDK mounts across publications.
Only `/opt/flutter` is configured as a Git safe directory.

Broad SDK write access is for a single trusted workload in a disposable container.
Do not share writable caches or containers between mutually untrusted workloads.

## Source and tool inventory

Installation removes only these verified upstream files containing private keys.
They are test fixtures, an example, or Windows templates outside the supported
Linux/Android workloads. Package libraries and Linux/Android build tools remain.

| Location | Exact file removed | Introducing layer |
| --- | --- | --- |
| System `/usr/share/cmake-*` | `Templates/Windows/Windows_TemporaryKey.pfx` | APT installation |
| Android `/opt/android-sdk/cmake/*/share/cmake-*` | `Templates/Windows/Windows_TemporaryKey.pfx` | Android installation |
| Flutter SDK | `engine/src/flutter/testing/android/native_activity/debug.keystore` | Flutter archive installation |
| Flutter SDK | `packages/flutter_tools/test/data/asset_test/tls_cert/dummy-key.pem` | Flutter archive installation |
| Flutter SDK | `examples/image_list/lib/main.dart` | Flutter archive installation |
| Pub `flutter_template_images` | `templates/app/winuwp.tmpl/runner_uwp/Windows_TemporaryKey.pfx` | Flutter/Android installation |
| Pub `http_multi_server` | `test/http_multi_server_test.dart` | Flutter/Android installation |
| Pub `shelf` | `test/ssl_certs.dart` | Flutter/Android installation |
| Pub `googleapis_auth` | `test/test_utils.dart` | Flutter/Android installation |

Sanitation runs before the introducing RUN layer completes, not in a later cleanup
layer. It checks exact paths, sizes, SHA-256 hashes, and official upstream content.
It rejects substituted paths and unexpected content. The SDK sanitizer compares
Flutter fixtures with the exact resolved revision's public source. CMake copies
must match the known upstream Windows template from the
[3.28.3](https://github.com/Kitware/CMake/blob/v3.28.3/Templates/Windows/Windows_TemporaryKey.pfx)
and [3.22.1](https://github.com/Kitware/CMake/blob/v3.22.1/Templates/Windows/Windows_TemporaryKey.pfx)
sources. Both have SHA-256
`a957fb8c8a3e3e7b1b8d2c58e97e02759b61cd7cbecca409c0763c8d6d9691f4`.

Pub assets must match exact members of the checksum-verified official archive.
The known `flutter_template_images` 5.0.0, `http_multi_server` 3.2.2, `shelf`
1.4.2, and `googleapis_auth` 2.3.2 archives also have fixed provenance checksums
in the sanitizer. The same checks apply to their copies in the SDK's
`.pub-preload-cache`: offending archives are deleted whole, never repacked under
the original package identity. The prepared, sanitized Pub cache remains usable.
Other preload archives remain. Later tool
or package versions may retain the same verified assets or omit them. Changed
content fails for review; Flutter itself is not pinned. The expanded credential
audit covers SDK/system key files and bounded source-file PEM blocks, with no
exemptions for public test keys. It inspects the rebuilt filesystem; separate
layer assessment is still required because removed files may remain in earlier
image layers. See the [validation guide](validation/README.md) for scope and limits.

The original SDK Git packs also contain the removed source fixtures. Within the
archive installation layer, `prepare-sdk-git.py` replaces that history with a
genuine shallow, blobless, no-checkout clone of the official resolved release tag.
It verifies the tag's commit against the release index and rejects any retained
blob objects, including unreachable ones. It preserves the exact upstream
revision, tag, `stable` branch, official remote, and an index populated from the
retained trees. It does not checkout missing files or copy the old object store.

Repository-local `protocol.allow=never` and `protocol.https.allow=never` prevent
the SDK's promisor remote from lazily downloading missing blobs. These policies
are supported by the image's Git 2.43 and do not affect consumer repositories or
Pub Git dependencies. Git operations requiring missing SDK source objects fail;
do not override these policies. Full source history and in-container upgrades
are not supported. Normal version detection uses authentic release metadata and
the prepared version cache. Weekly refreshes still resolve the latest stable
release and build a new image; no fixed Flutter version is introduced.

The `googleapis_auth` preload finding was verified against its
[official 2.3.2 metadata](https://pub.dev/api/packages/googleapis_auth/versions/2.3.2).
Its archive SHA-256 is
`1417d8846663df5e7b77ca56591c5edd442c66ffc9c01ab036e138a21a148e86`.
The 3,661-byte `test/test_utils.dart` member has SHA-256
`f0a9f91be4a427d735d1bfa4a2b1d8490c3c6663a48f02911217be5dddbfe957`
and contains an independently parsed private key. No key bytes are logged.

The base is the Docker Official Image `ubuntu:24.04`, maintained by Canonical.
Each run resolves its current digest. No suitable Flutter-team-maintained public
runtime image was identified during discovery. Flutter comes directly from its
official release archive, checked against the release index SHA-256. Cirrus and
Instrumentisto images are not official Flutter images and are not used here.
Reassess this choice if Flutter publishes a suitable official runtime image.

`resolve.py` reads the official Linux release index once. It selects stable x64,
reads Android defaults from that exact Flutter revision, and resolves Google's
stable Linux command-line tools archive and published checksum. Both image
targets consume the same `resolved.json`. An unavailable release or changed
upstream interface fails the run instead of selecting an older Flutter release.

The full image contains JDK 21 and the packages in `android-packages.txt`:
platforms 34/35/36, Build Tools 35.0.0/36.0.0, NDK 28.2.13676358,
CMake 3.22.1, and platform-tools. It also installs the resolved Flutter default
platform and NDK if different. Multiple required versions remain installed.
Command-line tools and platform-tools refresh through Google's stable repository.
SDK license acceptance is authorized by the repository owner.

The support inventory comes from these consumer requirements:

| Consumer | Android Gradle plugin | Gradle wrapper | Other observed requirements |
| --- | --- | --- | --- |
| Nuke Codes | 8.13.2 | 9.4.1 | JDK 21; platforms 34/35; Build Tools 35; NDK 28.2; CMake 3.22.1 |
| Shift Tac Toe | 8.11.1 | 8.14 | JDK 21; platform 34; Build Tools 35; NDK 28.2 |
| Pinkame | 8.11.1 | 8.14 | Flutter-derived platform and NDK |
| Commons setup | Consumer-selected | Consumer-selected | JDK 21; platform 36; Build Tools 36 |

These are observed configurations, not a promise that every cross-combination
is compatible. Each refresh evaluates the retained support set and the selected
Flutter defaults through the candidate validation hook. Maintainers update the
inventory and workload coverage when consumers change their requirements.
Private repositories are not checked out by this public workflow.

Inspect `/usr/local/share/flutter-runtime/toolchain.json`, `resolved.json`,
`os-packages.txt`, and, in full, `engine-maven.json` for actual included versions
and source checksums. OCI labels record the Commons revision and publication ID.

Flutter host and Android artifacts are cached during construction. The full
image also stores the selected engine's embedding and ARM32/ARM64/x86_64 Maven
artifacts for debug/profile/release. Its `FLUTTER_STORAGE_BASE_URL` points to
`file:///opt/flutter-storage`; Flutter's Gradle plugin uses this local repository.
Do not override that variable or run `flutter upgrade` inside the container.
Select a new image to upgrade the toolchain.

Project Pub packages, Maven dependencies, Android Gradle plugins, and project
Gradle wrapper distributions can still download on a cold build. These are
separate from the image's preloaded Flutter and Android tools. Web/browser tests,
Linux desktop application builds, emulators, other host architectures, and
arbitrary extra native tool versions are outside this initial support promise.

## Publication lifecycle

`Refresh Flutter runtimes` runs each Monday at 04:23 UTC and on manual dispatch
from `master`. A unique run/attempt ID invalidates the tool-installation layers
even if stable Flutter has not changed. The shared SDK layer is reused between
the two targets within that refresh. Container tags do not change Git release tags.

The workflow builds and loads both candidates on one runner, then calls the
validation hook. Only a successful pair can reach registry login and push.
The unique references are:

```text
ghcr.io/mkapusnik-apps/commons/flutter:run-RUN_ID-ATTEMPT-lightweight
ghcr.io/mkapusnik-apps/commons/flutter:run-RUN_ID-ATTEMPT-full
```

The workflow never reuses these references: a rerun has a new attempt number.
GHCR tags are technically mutable; use the digests in the `pair.env` evidence
artifact when immutable identity is required. No automated image deletion is
configured. Keep previous successful versions available.

Both validations and both unique pushes precede floating promotion. A build or
validation failure leaves both floating references unchanged. Registry promotion
of `lightweight` and `full` is not transactional. A failure between tag updates
can leave two validated generations advertised. To require a matching pair,
use both digests from one successful run's `pair.env`, not two floating pulls.

On partial promotion, inspect the original run's successful validation and
`pair.env`. An authorized operator can finish promotion of that exact pair with:

```sh
# Set these to the two verified digest references from the same evidence artifact.
docker buildx imagetools create --prefer-index=false \
  --tag ghcr.io/mkapusnik-apps/commons/flutter:lightweight "$LIGHTWEIGHT_DIGEST"
docker buildx imagetools create --prefer-index=false \
  --tag ghcr.io/mkapusnik-apps/commons/flutter:full "$FULL_DIGEST"
```

Coordinate recovery with the workflow's publication concurrency: do not run
manual tag updates while another publisher runs. Alternatively, dispatch a new
refresh to build and validate a new pair. Do not promote from an incomplete or
failed validation run. If only one unique push completed, neither floating tag
was updated; start a new refresh rather than inferring a complete pair.

## Pre-review and hosted evidence

The permanent workflow also runs for same-repository PRs to `master` when image
or workflow files change. It builds, validates, and publishes unique candidate
tags, but never advances floating tags. This provides hosted candidate/pull
evidence without changing `master` or adding a temporary workflow. Checkout uses
the exact PR head, not the synthetic merge revision. Fork PRs are skipped because
their code must not receive package-write access. Review code before running a
same-repository branch with this permission.

Schedules require the workflow on the default branch. GitHub also requires
default-branch registration for manual workflow dispatch. PR-triggered candidate
publication does not prove the weekly/manual trigger or production floating
promotion. Collect that remaining evidence after merge, or use an explicitly
authorized isolated repository. Do not claim that candidate evidence proves it.

The operator must permit package creation/write for the Commons workflow and
set the GHCR package to public after its first creation. Repository visibility
does not automatically make the package public. Verify anonymous pulls in a clean
Docker authentication context without changing an existing operator context.
No PAT is required in the workflow; it uses its scoped `GITHUB_TOKEN`.

Evidence artifacts contain the resolution, timings, hook outputs, and pushed
pair digests. Docker build summaries also contain build records. Record pull
time/bytes separately from startup, dependencies, tool preparation, and checks.
Include exact Commons and workload revisions, image digests, UID/mounts, and cache
conditions. Do not upload credentials or private consumer source.

PR candidates remain available for review. The initiating operator owns their
eventual registry cleanup and must not delete a retained production pair.
Hosted ephemeral runners own local image/workspace cleanup. Local verification
authors own temporary files, containers, and images created for their checks.

## Developer-owned validation interface

The workflow calls the implemented [candidate qualification hook](validation/README.md):

```text
bash runtimes/flutter/validate.sh LIGHTWEIGHT_LOCAL_REF FULL_LOCAL_REF EVIDENCE_DIRECTORY
```

This hook is the integration point for developer-owned workload coverage. It
must return nonzero on failure. A missing hook fails before registry login or any
push; do not add a success stub, skip switch, or continue-on-error. The two images
already exist in the local Docker daemon. The evidence directory exists.

The guide documents workload coverage, download controls, evidence, and local
tests. Implementing the hook does not qualify the images: successful candidate
qualification, independent QA, and hosted publication evidence remain pending.

The hook owns credential-free workload inputs, temporary containers, and cleanup.
It must leave both image references intact and must not publish or retag them.
Its evidence must identify the exercised support inventory and meet FR-AC-03,
FR-AC-04, FR-AC-05, and FR-EVIDENCE-01 through FR-EVIDENCE-03. In particular:

- Exercise the existing formatting, analysis, code-generation, unit/widget, APK,
  and AAB workloads selected by the developer against fresh containers.
- Check the matching version/revision and the declared tool inventory for the pair.
- Use an arbitrary non-root UID, writable documented mounts, and cold project
  caches. Identify missing tool downloads separately from project dependencies.
- Include x86_64 release engine use and use of the file-backed engine repository.
- Record startup/check durations, UID, mounts, image IDs, workload versions, and
  toolchain observations. Workflow evidence adds registry digests after push.
- Assess image contents for credentials and project-specific state.

This interface does not ask for tests of workflow wiring. Use actionlint and
normal hosted job logs for workflow configuration. Controlled build/validation
failure evidence and before/after registry reference observations are operator
acceptance work under FR-AC-07; never change production tags to unvalidated images.
