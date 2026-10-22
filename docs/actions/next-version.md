# Next Version

## Purpose

`Next Version` calculates the next candidate version name and code from the caller's checked-out Git tags and a production baseline. It reads local Git state only: no GitHub API calls, writes, fetches, version reservations, or automatic recovery. It does not edit `pubspec.yaml` or any other caller file.

The composite wrapper loads `calculate.cjs` from its own `github.action_path` and runs Git in `GITHUB_WORKSPACE`, not in the shared action directory. There is no repository-path or token input.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `baseline-tag` | Yes | None | Production marker tag whose commit must identify exactly one positive-integer numeric version tag. Supply a bare tag name. |
| `fallback-tag` | No | Empty | Initial positive-integer numeric tag, used only when the baseline marker does not exist. It must already exist when needed. |
| `annotation-prefix` | Yes | None | Literal, nonempty, single-line annotation prefix without surrounding whitespace, followed in the tag subject by a space and `X.Y.Z`. |
| `source-sha` | No | Empty | Source commit to reject if it already has any positive-integer numeric tag. Omit for forecasts. |

Names such as `play-production`, the code `411`, and the prefix `Play version` are examples, not built-in policy. The caller owns its marker, initial baseline, and literal prefix.

## Outputs

| Output | Description |
| --- | --- |
| `name` | Next candidate version name as an `X.Y.Z` string. |
| `code` | Next positive integer version code as a string. |

Outputs are published only after successful calculation; a failed calculation publishes neither output.

## Calculation and failure behavior

1. Select the highest positive-integer numeric tag using Git version ordering. Ignore nonnumeric names, zero, and names with leading zeroes. Numeric history must already exist; the action does not generate the first code.
2. If supplied, resolve `source-sha` to a commit and reject it when any numeric tag already points at that commit, including an older code. An invalid source fails rather than disabling the guard.
3. Resolve the production marker, or the supplied numeric fallback only if that marker is absent. The resolved commit must have exactly one numeric tag. An existing but unreadable or ambiguous marker never triggers fallback.
4. Read the baseline and highest-code tag subjects. Both used numeric tags must be annotated tags with the literal subject `<annotation-prefix> X.Y.Z`. Missing, lightweight, or malformed used annotations fail; irrelevant malformed historical annotations are ignored.
5. Target the baseline major and next minor. If the highest-code candidate is already in that series, increment its patch; otherwise start at patch zero. Increment the highest numeric code by one. A candidate with a higher major or a minor ahead of the target fails for manual resolution rather than scanning for an older replacement.

For example, baseline `2.2.16` and latest candidate `2.3.9` at code `426` produce name `2.3.10` and code `427`. When baseline and latest are both `2.3.1`, the next name is `2.4.0`.

Before adoption, the release owner must confirm that the highest numeric code carries the highest historical candidate version name. The action relies on that history invariant rather than auditing all older annotations.

## Caller setup and permissions

- Check out the caller repository into `GITHUB_WORKSPACE` with complete tags and history before invoking the action. Ensure the local snapshot is current; calculation does not fetch.
- Git must be installed. The `actions/github-script@v9` wrapper uses Node 24 and requires a compatible Actions runner, at least version `2.327.1`. No `npm install` is needed.
- Calculation requires no GitHub API access or write token. Same-repository checkout commonly grants `contents: read`; checkout authentication is separate from calculation. Credentials need not persist in the checkout.
- The caller owns sequential release operation, uploads, and tag creation. Calculate before building/uploading, upload before recording the numeric tag, and serialize operations so competing callers cannot publish the same candidate. This action does not enforce concurrency or reserve a version.
- A pre-upload retry can recalculate from refreshed history. If the source is already tagged, recover the original candidate manually without rebuilding or uploading. Post-upload recovery is also caller-owned; this action does not determine upload state.

## Example

Use the shared reference only after a Commons release containing this action has been published and the floating `v1` tag has moved to it. Consumer migration follows that release.

```yaml
permissions:
  contents: read

steps:
  - uses: actions/checkout@v7
    with:
      fetch-depth: 0
      fetch-tags: true
      persist-credentials: false
  - name: Calculate candidate version
    id: version
    uses: mkapusnik-apps/commons/next-version@v1
    with:
      baseline-tag: play-production
      fallback-tag: '411'
      annotation-prefix: Play version
      source-sha: ${{ github.sha }}
```

Omit `source-sha` for a forecast; this does not reserve the returned version. A caller with Flutter already configured can consume the outputs as build flags without changing `pubspec.yaml`:

```yaml
  - name: Build candidate
    env:
      VERSION_NAME: ${{ steps.version.outputs.name }}
      VERSION_CODE: ${{ steps.version.outputs.code }}
    run: flutter build appbundle --build-name="$VERSION_NAME" --build-number="$VERSION_CODE"
```

## Local tests

From the Commons repository root, using Node 24 and Git without installing dependencies:

```sh
node --test next-version/calculate.test.cjs
```

The suite covers arithmetic, temporary Git histories, read-only behavior, validation failures, output publication, and the actual composite wrapper relocated outside the caller checkout. These local checks do not require live credentials or hosted workflow execution.
