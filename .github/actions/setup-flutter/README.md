# Setup Flutter for CI

Install the stable Flutter SDK with `subosito/flutter-action@v2`, enable its SDK and Pub caches under the runner temporary directory, and configure the Flutter CLI for non-interactive CI use.

The action has no inputs or outputs. It expects a GitHub-hosted or compatible runner with Bash and Git available.

## Remote usage

Reference the action by its repository path and pin Commons to the immutable full commit SHA containing the version you reviewed:

```yaml
steps:
  - name: Set up Flutter
    uses: mkapusnik/commons/.github/actions/setup-flutter@<40-character-commons-commit-sha>
```

Do not use a moving branch such as `master` for production workflows. A full commit SHA prevents later Commons updates from changing the action implementation without a corresponding pin update.

The action intentionally retains the nested `subosito/flutter-action@v2` reference from its original local implementation.
