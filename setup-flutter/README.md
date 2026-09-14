# Setup Flutter for CI

Install the repository-standard Java, Android, and stable Flutter toolchains. Enable Flutter SDK and Pub caches under the runner temporary directory. Configure Flutter for non-interactive CI use.

The action installs `platform-tools`, `platforms;android-36`, and `build-tools;36.0.0`. It can install additional Android SDK packages in the same setup operation.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `additional-android-packages` | No | Empty | Additional Android SDK package identifiers. Separate multiple identifiers with whitespace. |

The action has no outputs. It expects a GitHub-hosted or compatible runner with Bash and Git available.

## Remote usage

Use the floating v1 tag to receive the latest compatible v1 release:

```yaml
steps:
  - name: Set up Flutter
    uses: mkapusnik-apps/commons/setup-flutter@v1
    with:
      additional-android-packages: >-
        platforms;android-34 build-tools;35.0.0 ndk;28.2.13676358
```

Omit `additional-android-packages` or leave it empty to install only the standard package set.

Do not use a moving branch such as `master` for production workflows. Pinning `mkapusnik-apps/commons/setup-flutter` to a reviewed full commit SHA is stricter than `v1` because later compatible releases cannot change the resolved implementation without a corresponding pin update.

The action installs requested packages without a separate Android SDK setup action.
