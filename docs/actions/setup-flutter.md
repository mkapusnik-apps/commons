# Setup Flutter for CI

## Purpose

`Setup Flutter for CI` installs the repository-standard Java, Android, and stable Flutter toolchains. It also configures Flutter for non-interactive CI use.

## User scenario

Use this action when a Flutter workflow needs the repository-standard toolchain. A consumer can also request Android SDK packages that its project requires.

## Inputs and outputs

The action declares no outputs.

| Input | Required | Default | Behavior |
| --- | --- | --- | --- |
| `additional-android-packages` | No | Empty | Installs additional Android SDK package identifiers. Separate multiple identifiers with whitespace. |

## Android SDK packages

- **SF-ANDROID-PACKAGES-01:** The action must install `platform-tools`, `platforms;android-36`, and `build-tools;36.0.0` for each consumer.
- **SF-ANDROID-PACKAGES-02:** A consumer may request one or more additional Android SDK packages with `additional-android-packages`.
- **SF-ANDROID-PACKAGES-03:** The action must add requested packages to the standard package set.
- **SF-ANDROID-PACKAGES-04:** The action must install the standard package set and requested packages in one Android SDK setup operation.
- **SF-ANDROID-PACKAGES-05:** If `additional-android-packages` is empty or omitted, the action must install only the standard package set.

## Runtime requirements

The runner must provide Bash and Git. The action installs Temurin Java 21 and the Android SDK packages. It also installs stable Flutter.

The action enables Flutter SDK and Pub caching in the runner temporary directory. It marks the Flutter SDK as a safe Git directory. It disables analytics and CLI animations.

## Example

```yaml
steps:
  - name: Set up Flutter
    uses: mkapusnik-apps/commons/setup-flutter@v1
    with:
      additional-android-packages: >-
        platforms;android-34 build-tools;35.0.0 ndk;28.2.13676358
```

Use the floating `v1` tag for compatible v1 updates. Pin `mkapusnik-apps/commons/setup-flutter` to a reviewed full commit SHA when stricter immutable resolution is required; do not use a moving branch such as `master`.

## Failure behavior

The action fails if a toolchain setup operation fails. It also fails if the runner lacks Bash or Git or if Flutter CLI configuration fails.

## Acceptance criteria

- **SF-ANDROID-PACKAGES-AC-01:** If the input is omitted, the action installs the standard package set without a consumer workflow change.
- **SF-ANDROID-PACKAGES-AC-02:** The input accepts one additional Android SDK package identifier.
- **SF-ANDROID-PACKAGES-AC-03:** The input accepts multiple additional Android SDK package identifiers.
- **SF-ANDROID-PACKAGES-AC-04:** Requested packages do not replace any package in the standard package set.
- **SF-ANDROID-PACKAGES-AC-05:** The action installs standard and requested packages in one Android SDK setup operation.
- **SF-ANDROID-PACKAGES-AC-06:** A consumer can request `platforms;android-34`, `build-tools;35.0.0`, and `ndk;28.2.13676358` in one action use.
- **SF-ANDROID-PACKAGES-AC-07:** A consumer does not need a separate Android SDK setup action to install requested packages.
