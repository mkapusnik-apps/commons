# Setup Flutter for CI

## Purpose

`Setup Flutter for CI` installs the stable Flutter SDK through `subosito/flutter-action@v2`, enables SDK and Pub caching in the runner temporary directory, and configures the Flutter CLI for non-interactive CI use.

## User scenario

Use this action when a Flutter workflow needs the repository-standard stable toolchain and cache configuration before dependency installation, analysis, formatting, tests, or builds.

## Inputs and outputs

The action has no inputs and declares no outputs.

## Runtime requirements

The runner must provide Bash and Git. The action installs Flutter, marks the Flutter SDK as a safe Git directory, disables analytics, and disables CLI animations. It retains the nested `subosito/flutter-action@v2` dependency and its existing stable-channel cache behavior.

## Example

```yaml
steps:
  - name: Set up Flutter
    uses: mkapusnik-apps/commons/setup-flutter@v1
```

Use the floating `v1` tag for compatible v1 updates. Pin `mkapusnik-apps/commons/setup-flutter` to a reviewed full commit SHA when stricter immutable resolution is required; do not use a moving branch such as `master`.

## Failure behavior

The action fails when the nested Flutter setup action cannot install or restore the SDK, when the runner lacks Bash or Git, or when Flutter CLI configuration fails.
