# Flutter runtime evidence ledger

## Status and provenance

This ledger records review-readiness evidence, not product or final operational
acceptance. The PR remains draft pending product and exact-head verification.
There is no merge or production-execution authorization. Apply the separate gates
in the [specification](flutter.md#review-readiness-and-operational-acceptance).

- Implementation: [`75e01aa0c67a2549dff5473323634fb41eed75b4`](https://github.com/mkapusnik-apps/commons/commit/75e01aa0c67a2549dff5473323634fb41eed75b4).
- Specification gate baseline: [`e48bd8f93989fcab03e5b3a07afb2ea0b0bf568b`](https://github.com/mkapusnik-apps/commons/commit/e48bd8f93989fcab03e5b3a07afb2ea0b0bf568b).
- Hosted source run: [35687086776, attempt 1](https://github.com/mkapusnik-apps/commons/actions/runs/35687086776).
- Publication: `run-35687086776-1`; repository `ghcr.io/mkapusnik-apps/commons/flutter`; Linux AMD64.
- [PR #55](https://github.com/mkapusnik-apps/commons/pull/55) targets `master`.
- Subsequent gate/ledger edits are documentation-only; they do not relabel the
  images as built from a newer documentation checkpoint.

The team supplied the hosted outcomes and measurements below. During integration,
the independent layer report was read and its hash verified. The devops hosted
`REPORT.md` and historical local raw evidence were unavailable in this session;
their accepted summaries are attributed, not represented as newly inspected logs.
No missing artifact was fabricated and no verification was rerun for this ledger.

## Public candidate pair

| Variant | Unique publication reference | Immutable digest reference |
| --- | --- | --- |
| Lightweight | `ghcr.io/mkapusnik-apps/commons/flutter:run-35687086776-1-lightweight` | `ghcr.io/mkapusnik-apps/commons/flutter@sha256:559e3dc24d55307ba545a57cedeb4388e11257cd8f2e4b512becade548a79581` |
| Full | `ghcr.io/mkapusnik-apps/commons/flutter:run-35687086776-1-full` | `ghcr.io/mkapusnik-apps/commons/flutter@sha256:3bb1f7d6b58c69b7cb3547156acb2382cd3a0ded0e0d8f575884b03bfc5aee03` |

Use digest references for immutable identity; unique tags are not registry-enforced
immutable tags. Anonymous pulls of this pair passed. These are **candidate** pulls,
not proof that production `:lightweight` and `:full` floating references are available.
Local-build image IDs are not substituted for these public digests.

## Recorded review and qualification outcomes

| Evidence | Recorded outcome and scope |
| --- | --- |
| Source review | Reviewer passed implementation `75e01aa`; prior source blockers were closed. |
| Developer behavioral tests | 113 tests passed, including real isolated Git metadata/index/transport checks and fail-closed sanitation/archive tests. |
| Fresh local routine qualification | Both audits and all five workloads passed at `75e01aa`; 1,348.52 s total. No historical production results were reused in that run. |
| Non-root workloads | UID/GID `12345:23456`, pristine containers and cold writable project caches. Formatting, analysis, code generation, unit/widget tests, native NDK/CMake compilation, and APK/AAB ABI checks passed. |
| Toolchain readiness | No toolchain acquisition observed. Inventories stayed at 1,231 lightweight and 46,656 full files with unchanged hashes. Pub/Maven/Gradle dependency traffic was recorded separately. |
| SDK Git retention | Local before/after workload counts: 3,104 trees, one commit, zero blobs. Exact published-image independent inspection also passed zero-blob, official release/origin, and transport-policy checks; removed-blob access failed with exit 128 and transport blocked. |
| Hosted validation | Supplied devops evidence records both audits and all five workloads passed, mapped through `pair.env`, `published-images.json`, and the validation summary to the public pair. |
| Independent QA | Local behavioral/non-root checks passed. Exact-public-pair filesystem/Git checks and the published-layer follow-up passed; the former layer-export blocker is closed. |

The five workload cases are lightweight; full with generated Flutter defaults;
SDK34 ARM64 debug APK; SDK35 x86_64 release APK; and SDK36 ARM32/ARM64/x86_64 release
AAB. Both AAB cases verify Flutter and compiled native readiness libraries for all
three ABIs. Detailed supported tools, writable paths, Git restrictions, sanitation,
and remaining dependency downloads are in the [operations guide](../../runtimes/flutter/README.md).
These images do not promise in-container SDK upgrades or dependency-free arbitrary builds.

### Measurements and cache limits

| Measurement | Reported value | Interpretation |
| --- | ---: | --- |
| Hosted lightweight build | 202 s | Supplied hosted build duration. |
| Hosted full build | 271 s | Supplied hosted build duration. |
| Hosted qualification | Approximately 950 s | Both audits and five workloads; not image-pull time. |
| Local fresh qualification | 1,348.52 s | Includes audits, five workloads, evidence/Git observations and cleanup. |
| Local workload startup | 0.248–0.288 s | Container start to Python worker, with image already local. |
| Anonymous lightweight pull | 548.902 s | Supplied public-pull measurement. |
| Anonymous full pull | 208.021 s | Shared layers were already present; not an independent cold pull. |
| Lightweight descriptor bytes | 1,700,627,512 | Reported descriptor total, not measured wire traffic. |
| Full descriptor bytes | 3,933,942,980 | Reported descriptor total, not measured wire traffic. |

These observations are **not a cold-pull benchmark**. Keep image retrieval costs
separate from SDK preparation and project dependency/check execution. No numeric
performance threshold or broader comparative performance claim is inferred.

## Independent published-layer assessment

The verified tester report covers the exact manifests above: eight ordered layers
for lightweight and nine for full, **ten unique layers** overall. It verified all 17
entries in the export checksum manifest, original layer order and configuration DiffID order, then
read the original gzip layers without conversion or extraction. Devops' verified
decompressed DiffIDs were reused.

All ten layers were traversed: **122,648 entries**, **45,012 bounded content files**,
and **zero findings**. Prior CMake PFX, Flutter keystore/PEM/image-list, known Pub
fixtures and their four preload-archive families were absent. Targeted credential
names and private PEM blocks were not found. One SDK Git pack was present; its
internal objects were not re-enumerated in this layer-only pass. The preceding
exact-public-image zero-blob inspection was explicitly reused for that component.

This is all-layer traversal with targeted filenames and content inspection up to
2 MiB, **not exhaustive proof that arbitrary binaries, encodings, unrelated nested
archives, or every credential type are secret-free**. Twelve oversized content
files were excluded from content scanning; their filenames were still checked:

<details>
<summary>Oversized content exclusions (12)</summary>

- `usr/lib/llvm-18/lib/clang/18/include/arm_neon.h`
- `usr/lib/x86_64-linux-gnu/perl/5.38.2/CORE/charclass_invlists.h`
- `usr/share/mime/packages/freedesktop.org.xml`
- `cache/pub/hosted/pub.dev/analyzer-10.1.0/test/src/dart/analysis/driver_test.dart`
- `opt/flutter/bin/cache/dart-sdk/bin/resources/devtools/assets/packages/perfetto_ui_compiled/dist/v34.0-16f63abe3/frontend_bundle.js`
- `opt/flutter/bin/cache/dart-sdk/bin/resources/devtools/main.dart.js`
- `opt/flutter/bin/cache/flutter_web_sdk/kernel/amd-canvaskit/dart_sdk.js`
- `opt/flutter/bin/cache/flutter_web_sdk/kernel/ddcLibraryBundle-canvaskit/dart_sdk.js`
- `opt/android-sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/lib/clang/19/include/arm_neon.h`
- `opt/android-sdk/platforms/android-34/data/api-versions.xml`
- `opt/android-sdk/platforms/android-35/data/api-versions.xml`
- `opt/android-sdk/platforms/android-36/data/api-versions.xml`

</details>

## Bounded negative rehearsal

The supplied controlled absent-candidate rehearsal failed before publication.
Unique candidate tags were unchanged; production floating-reference observations
were HTTP 404. This supports the bounded rejection path described in **FR-GATE-03**.
It is **not** a successful test of preserving existing working production references,
continued availability of an existing production pair, or partial-promotion recovery.
No destructive production-reference mutation is required or authorized by this record.

## Pending operational acceptance

Review readiness and operational acceptance remain separate. Product/exact-head
verification and an explicit ready transition are still required; no merge is
authorized. The following remain pending after separately authorized default-branch
registration/execution, or an approved isolated hosted rehearsal of the deployed path:

| Criterion | Required evidence | Owner |
| --- | --- | --- |
| FR-AC-01 | Anonymous pulls from both advertised production floating references, mapped to one validated immutable publication pair. | Devops/operator produces; tester verifies. |
| FR-AC-02 | Actual scheduled and manual refresh runs; a refresh with the same naturally resolved latest-stable Flutter revision that still rebuilds and publishes both variants. Record event/ref/source, resolution, build/validation results, pair digests and timings. Do not pin Flutter to manufacture the condition. | Devops/operator produces; tester verifies. |
| FR-AC-07 | Controlled failure starting with existing working validated references, unchanged before/after references and continued pulls; hosted promotion outcomes and partial-promotion recovery. Any isolated rehearsal must document correspondence to the deployed publication path and must not disrupt consumer references. | Devops/operator designs and runs with authorization; tester independently assesses. |

Product/team determines acceptance after these records satisfy the specification.
The absence of default-branch-only observations alone does not block review readiness
(FR-GATE-05), but it does not turn them into passes. Promotion across the two floating
references remains nontransactional; consumers requiring a matching pair use the
two digests from one successful publication. Container publication is independent
of shared GitHub Action version tags.

## Evidence anchors and retention

| Record | SHA-256 | Availability/provenance at integration |
| --- | --- | --- |
| `INDEPENDENT-LAYER-QA.md` | `2349744cbb33144aac5180863903e13a99f3c237c960d972f043e0e96e2f0385` | Read and hash-verified from the supplied registry-export evidence. This ledger preserves its result and limitations. |
| Devops hosted `REPORT.md` | `a49238441f0ff2cdf8a1514346e2aa76cff85cfe74d618d64d414b75ab602bec` | Supplied identity; file unavailable in this integration session. Hosted summaries are attributed to the authoritative team/devops handoff and linked run. |
| Local `FINAL-SHA256SUMS` | `0e3fa63fb275b9441790f57de4e5823afdf5f352eddf29fc414796cf65fd97bd` | Historical accepted routine-evidence identity; original local files were unavailable here. Results were not regenerated or substituted. |
| Registry export `SHA256SUMS` | `157a3badccebe90b35d248bcb375b47807cb3aab98f8732d620ab0407903e181` | Verification of all 17 entries is attested by the independent report, not rerun by this ledger integration. |
| Registry export `VERIFIED.json` | `de72505da68dd33458d753613a48cf7238819c62edb16fe7f57129244141a3fb` | Identity and manifest/DiffID mapping attested by the independent report. |

Raw logs, OCI blobs and temporary verification programs are not committed. Keep
owner-held evidence available through exact-head, product, hosted and QA consumers.
Developer owns ledger/report integration and developer-created temporary evidence;
devops separately owns registry-export cleanup. Do not remove another owner's export
or rebuild an accepted artifact merely for handoff. Changed image/blob identities
require affected revalidation; documentation-only descendants retain the original
implementation and artifact provenance rather than rewriting it.
