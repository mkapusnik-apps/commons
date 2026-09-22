# Candidate qualification

Run from a clean Commons checkpoint after building both local image targets with
`SOURCE_REVISION` equal to that checkpoint or a verified production-identical ancestor:

```sh
bash runtimes/flutter/validate.sh LIGHTWEIGHT_LOCAL_REF FULL_LOCAL_REF EVIDENCE_DIRECTORY
```

The hook requires Python 3.11+ and Docker. It never pulls, pushes, retags, or deletes
candidate images. It pins container execution to inspected image IDs, rejects
different image source/publication pairs, and checks that input references are
unchanged on exit. Failures return nonzero and retain partial evidence. Each call
uses a new evidence subdirectory so stale successful results cannot mask failure.
The caller owns retained evidence and image cleanup; the hook removes its own
temporary containers and named volumes, including on ordinary failures and SIGTERM.
After an uncatchable termination, remove only resources bearing that invocation's
`commons-flutter-check-` names recorded in Docker and its evidence.

For validator-only follow-up commits, retain the original image labels and IDs.
The hook requires both image source labels to identify the same full commit SHA,
verifies it is an ancestor of the clean validation checkpoint, and compares Git
objects and modes under `runtimes/flutter` and `.github/workflows/flutter-runtimes.yml`.
Only `runtimes/flutter/validation/` is excluded. Changes to the Dockerfile, installers,
resolver, package inventory, wrapper, other runtime paths or publication workflow
reject reuse. Evidence records both revisions, scope, equal production entries,
and their SHA-256. This is tree equality verification, not a revision bypass or
relabeling operation. Full local history for the image source must be available.

## Genuine workload coverage

Each workload starts in a fresh container as UID/GID `12345:23456`, with fresh
named volumes at the documented workspace, HOME, Pub, and Gradle locations. SDKs
remain on the writable container layer. An offline root initializer grants write
access to empty volumes (copy-up disabled); it does not access SDKs or host paths.
The pristine-image audit runs as root with networking disabled so it can inspect
root-owned credential locations; all actual workload commands run non-root.

All five workload containers run real formatting, analysis, `build_runner` JSON
serializer generation, a generated-serializer unit test, and a Flutter widget test.
The full-image matrix additionally exercises:

| Case | Platform / Build Tools | AGP / Gradle | Native tooling | Artifact |
| --- | --- | --- | --- | --- |
| defaults | Resolved Flutter template defaults | Generated Flutter template | Flutter default NDK, CMake 3.22.1 | Release AAB, ARM32/ARM64/x86_64 |
| sdk34 | 34 / 35.0.0 | 8.11.1 / 8.14 | NDK 28.2.13676358, CMake 3.22.1 | Debug ARM64 APK |
| sdk35 | 35 / 35.0.0 | 8.13.2 / 9.4.1 | NDK 28.2.13676358, CMake 3.22.1 | Release x86_64 APK |
| sdk36 | 36 / 36.0.0 | 8.13.2 / 9.4.1 | NDK 28.2.13676358, CMake 3.22.1 | Release AAB, ARM32/ARM64/x86_64 |

The retained consumer combinations preserve their listed AGP/Gradle and Android
tool choices, and use the Kotlin plugin version from the selected Flutter release's
generated template. The hook requires exactly one literal template Kotlin version,
fails on an unsupported template layout, and records that version and the final
settings file in evidence. It does not pin the fixture to an obsolete Kotlin version
or bypass Flutter dependency checks. These are qualification
inputs, not an assertion of compatibility: incompatible combinations fail the
gate and require an explicit support decision, not a skipped check. A tiny C
library forces real NDK/CMake compilation. APK/AAB contents must include that
library and the Flutter engine for every requested ABI. Synthetic debug signing
keys are generated only inside disposable workload containers and are not exported.
The generated application uses no private source, secrets, or consumer identifiers.

## Downloads and evidence

Missing lightweight Flutter artifacts cannot download: Flutter storage is set to
an unreachable loopback endpoint. Full uses the image's file-backed engine
repository and checks its recorded hashes, including x86_64 release artifacts.
Android automatic SDK installation is disabled in the synthetic Gradle projects.
SHA-256 inventories before/after cover Flutter engine and Dart SDK contents, the
Android SDK, and the local engine Maven repository. Changed/new/missing tooling
fails the hook. Android root dotfile bookkeeping is excluded, not package contents.
Logs independently reject recognized tool acquisition events and separately record
Pub, Maven, and Gradle distribution dependency activity. Command echoes, installed
package inventory, and static storage-source notices are not acquisition events.
Kotlin Maven dependencies named `kotlin-build-tools-*` are not Android SDK Build
Tools; actual SDK acquisition descriptions and official tool URLs still fail.
This is not a packet capture;
unknown log messages alone are not proof of network absence. Download controls,
artifact comparisons, and logs must be assessed together.

Evidence contains source/workload hashes, image IDs and available digests,
UID/mounts/cache conditions, metadata, command timings/logs, resolved Pub lockfiles,
Android build configuration, artifact hashes/ABIs, and before/after inventories.
Container elapsed time includes setup/checks; worker and individual command times
are separate. Build time belongs to the builder's evidence. Image-pull time is
explicitly not measured by this local-only hook; hosted anonymous pull evidence
must measure it separately. APK/AAB binaries are inspected and hashed, not retained.
Content assessment covers credential/key candidates under `/root`, `/home`, `/cache`,
`/workspace`, `/tmp`, `/opt`, `/usr`, `/etc`, and `/var`, plus image environment names
and unexpected workspace state. SDK sources, system CMake templates, and Android
CMake/NDK installations are included; virtual filesystems are not scanned. Individual
certificate/key links are resolved with deduplication by inode and equivalent
inspection class, without recursive directory-link traversal. Source aliases never
suppress binary-store/key checks; oversized source aliases are not marked inspected.
Credential-name findings remain per path even when another alias was accepted.
Read errors fail the gate instead of silently hiding paths.

The audit detects PKCS#12 private-key bags, Java private/secret-key entries, PEM
private keys and DER private-key files. Certificate-only PKCS#12/Java trust stores,
X.509 certificates, and public-key files are not credentials merely because their
filename has a store/key suffix. Opaque or malformed candidate key stores fail
closed. Inspection never exports key bytes: evidence records only paths, reasons,
and file hashes, including on failure. There is no public-test-key exemption.
Common source/configuration files (including Dart, Python, JavaScript, Kotlin,
C/C++, JSON and YAML) up to 2 MiB are also scanned for embedded private-key PEM
blocks, including multiline literals and escaped newlines. Matching header/footer
and payload are required, so parser header constants and public certificates are
not mistaken for keys. Evidence records the extension scope, size bound, scanned
count and oversized-source count. Key/store candidates are not excluded by this
source-size bound. This is not exhaustive detection of arbitrary encoded secrets,
oversized source, encrypted archives, or files retained only in earlier image layers.

Retained SDK Git metadata is checked separately: exact resolved release tag/commit,
`stable` branch and remote-tracking ref, official origin, shallow history, and a
release-tree-equivalent index are required. Repository-local transport policies
must deny both generic and HTTPS transport. Local object enumeration includes
unreachable objects and rejects **any blob** without printing object contents.
The audit itself additionally blocks transport while inspecting metadata. This
validates version-detection metadata, not support for SDK checkout or upgrades.

Preload archive acceptance is narrowly scoped to the confirmed asset paths in
`flutter_template_images`, `http_multi_server`, `shelf`, and `googleapis_auth`.
It never extracts files. Retained confirmed assets fail; changed content at those
paths requires review rather than an exemption. Other package families and clean
later archives with no confirmed member are not falsely flagged. Compressed input
is bounded to 32 MiB, expanded member sizes to 128 MiB, 20,000 members, and a 2 MiB
confirmed asset. Exceeding a bound or encountering a malformed/link asset fails
closed. This is not a general encrypted/nested-archive scanner; independent image
layer assessment is still separate. Findings are preserved in failed audit evidence.

The shell hook is fail-closed, but does not itself implement publication. Negative
local tests exercise actual validator control flow and nonzero subprocess outcomes.
They do **not** prove GitHub job gating or registry reference safety. Controlled
build/check failures, before/after registry observations, partial-promotion recovery,
and public pulls remain operator and independent QA evidence under FR-AC-07.

## Fast local behavioral tests

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s runtimes/flutter/validation -p 'test_*.py' -v
```

These cover resolver selection/retention/failure, pair and image identity, missing
tools, download classification, artifact changes, ABI inspection, nonzero workload
exits, and fail-closed cleanup/reference preservation with explicit Docker-boundary
fakes. They are not substitutes for real candidate qualification.

Content-audit tests also require OpenSSL. Run them inside an existing runtime image
if the host lacks it; they fail rather than skip when it is unavailable. They
generate disposable local key/certificate fixtures without networking or outputting
private material, and verify both the reported SDK/system misses and normal trust
stores. No genuine consumer credentials are used.

Git preparation tests use real isolated repositories with a local filtered
transport. They verify exact release metadata/index, absence of reachable and
unreachable blobs, rejection of ignored filters, and blocked missing-blob retrieval
over file/HTTPS while unrelated consumer repositories still work. Pub/preload
sanitation tests use synthetic archives and isolated upstream responses.
