# Flutter runtimes

See the [specification](../../docs/runtimes/flutter.md) for scope and acceptance.
Both images support Linux AMD64 and use an ordinary non-root user.

| Public GHCR reference | Intended use |
| --- | --- |
| `ghcr.io/mkapusnik-apps/commons/flutter:slim` | Dart/Flutter formatting, analysis, code generation, unit and widget tests |
| `ghcr.io/mkapusnik-apps/commons/flutter:full` | Slim tools plus Flutter Android APK/AAB builds |

## Contents

Slim uses the Docker Official Image `ubuntu:24.04` and the official Flutter Linux
archive. Each workflow resolves the latest stable x64 release once from the
[official index](https://storage.googleapis.com/flutter_infra_release/releases/releases_linux.json).
The Dockerfile verifies the archive SHA-256. Full inherits the slim image built in
the same job, so both variants use the same Flutter and bundled Dart release.

Full adds OpenJDK 21, Android command-line tools 23.0 (bootstrap archive 16111833),
platform-tools, SDK platforms 34/35/36, Build Tools 35.0.0/36.0.0,
NDK 28.2.13676358, and CMake 3.22.1. Google's bootstrap checksum is recorded beside
its revision in `full.Dockerfile`. Update those two values together when changing
the bootstrap. The explicit Android inventory is maintained in that Dockerfile;
it is not inferred from private Flutter APIs or consumer repositories. The SDK
manager installs current available revisions of the selected packages.

Construction accepts the authorized Android licenses and uses native Flutter
precache commands. Native caches reduce preparation, but do not guarantee zero
downloads or certify every application/tool-version combination. Pub/Maven/Gradle
project dependencies, cache misses, and tools outside the inventory can download
during use. Emulators, device provisioning, and other host architectures are not
included. Select a new image to refresh the shared toolchain.

Official upstream distributions remain intact, including public test fixtures and
public test keys. These are not operational credentials and must not be used for
real signing. The builds do not copy a consumer project, authentication directories,
or operator/application secrets into the images. Registry login occurs only in the
publication workflow, after both builds, not inside either Dockerfile.

## Pull and run

```sh
docker pull --platform linux/amd64 ghcr.io/mkapusnik-apps/commons/flutter:slim
docker pull --platform linux/amd64 ghcr.io/mkapusnik-apps/commons/flutter:full

# From a Flutter project; arrange writable mounts as described below.
docker run --rm --platform linux/amd64 \
  --mount "type=bind,src=$PWD,dst=/workspace" \
  ghcr.io/mkapusnik-apps/commons/flutter:slim \
  bash -c 'flutter pub get && flutter analyze && flutter test'

docker run --rm --platform linux/amd64 \
  --mount "type=bind,src=$PWD,dst=/workspace" \
  ghcr.io/mkapusnik-apps/commons/flutter:full flutter build apk --debug
```

Use `flutter build appbundle` with the project's own signing configuration for an
AAB. Supply project credentials at runtime only; never add them to an image build.

The default UID/GID is `10001:10001`. Writable locations are `/opt/flutter`,
`/home/flutter`, `/cache/pub`, `/cache/gradle`, `/workspace`, and, in full,
`/opt/android-sdk`. Mount only workspace and dependency caches for ordinary use;
empty mounts over the SDKs hide their preinstalled contents.

Make bind mounts writable by the execution UID or GID 10001. An additional numeric
UID can use `--user <uid>:10001` with writable HOME/cache/workspace mounts and
`--env GIT_CONFIG_COUNT=1 --env GIT_CONFIG_KEY_0=safe.directory
--env GIT_CONFIG_VALUE_0=/opt/flutter`. The image's prepared SDK/cache paths are
group-writable. Arbitrary UID/GID combinations and shared writable caches between
untrusted users are not supported. Use a writable disposable container filesystem.

For diagnostics, run these commands in the corresponding image:

```text
flutter --version --machine
dart --version
java -version                         # full
sdkmanager --version                  # full
sdkmanager --list_installed           # full
```

The image labels also expose the selected Flutter version/revision and Commons
source revision. Native commands report the actual installed tool versions.

## Build locally

Use the default Docker-driver builder, not an isolated `docker-container` builder.
Resolve once and build both images without publishing:

```sh
release=$(curl -fsSL https://storage.googleapis.com/flutter_infra_release/releases/releases_linux.json |
  jq -ce '. as $index | .releases[] |
    select(.hash == $index.current_release.stable and .channel == "stable" and
      (.dart_sdk_arch // "x64") == "x64") |
    . + {url: ($index.base_url + "/" + .archive)}')

docker build --builder default --platform linux/amd64 --pull --no-cache \
  --file runtimes/flutter/slim.Dockerfile --tag commons-flutter:slim \
  --build-arg FLUTTER_URL="$(jq -r .url <<< "$release")" \
  --build-arg FLUTTER_SHA256="$(jq -r .sha256 <<< "$release")" \
  --build-arg FLUTTER_VERSION="$(jq -r .version <<< "$release")" \
  --build-arg FLUTTER_REVISION="$(jq -r .hash <<< "$release")" \
  --build-arg SOURCE_REVISION="<source-checkpoint>" runtimes/flutter

docker build --builder default --platform linux/amd64 --no-cache \
  --file runtimes/flutter/full.Dockerfile --tag commons-flutter:full \
  --build-arg SLIM_IMAGE=commons-flutter:slim runtimes/flutter
```

The example uses Bash and jq. Do not add `--pull` to the full build: its parent is
the local slim image from this run, not a registry floating reference.

## Publication

The PR workflow only builds both images, with read-only repository permission.
There is no PR registry login, publication, or application test matrix.

The separate publisher runs Mondays at 04:23 UTC and on manual dispatch selecting
`master`. It rebuilds both images with `--no-cache`, and refreshes the Ubuntu base
with `--pull`, even if Flutter is unchanged. Only after both builds succeed does
it log in with the workflow's `GITHUB_TOKEN` (`packages: write`). It pushes both
unique references, then the floating `slim` and `full` references. Its job summary
records the unique references and digest pair. Container tags are independent of
the repository's shared GitHub Action release tags.

Unique references have the form `run-<run-id>-<attempt>-slim` and
`run-<run-id>-<attempt>-full`. Tags are mutable registry references; use the two
`ghcr.io/mkapusnik-apps/commons/flutter@sha256:...` references from one successful
run's summary for an immutable matching pair. Previous unique references are not
automatically deleted. A failed build changes no published references.

Floating updates are not transactional: a registry failure can leave two different
publications advertised. Use the previous successful digest pair if necessary and
dispatch a fresh master publication. There is no automated rollback. Workflow
failures remain visible through normal job results.

The publisher must be registered on the default branch for scheduled/manual use.
An operator must allow GHCR package publication and ensure the package is public
for anonymous pulls. Build sanity does not itself prove publication availability.
