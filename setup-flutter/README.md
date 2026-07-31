# Setup Flutter for CI

Install the stable Flutter SDK with `subosito/flutter-action@v2`, enable its SDK and Pub caches under the runner temporary directory, and configure the Flutter CLI for non-interactive CI use.

The action has no inputs or outputs. It expects a GitHub-hosted or compatible runner with Bash and Git available.

## Remote usage

Use the floating v1 tag to receive the latest compatible v1 release:

```yaml
steps:
  - name: Set up Flutter
    uses: mkapusnik-apps/commons/setup-flutter@v1
```

Do not use a moving branch such as `master` for production workflows. Pinning `mkapusnik-apps/commons/setup-flutter` to a reviewed full commit SHA is stricter than `v1` because later compatible releases cannot change the resolved implementation without a corresponding pin update.

The action intentionally retains the nested `subosito/flutter-action@v2` reference from its original local implementation.
