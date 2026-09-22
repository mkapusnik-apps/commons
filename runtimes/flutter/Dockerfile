# syntax=docker/dockerfile:1
ARG BASE_IMAGE=ubuntu:24.04
FROM ${BASE_IMAGE} AS sdk
ARG REFRESH_ID
ARG SOURCE_REVISION
LABEL org.opencontainers.image.source="https://github.com/mkapusnik-apps/commons" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      io.commons.flutter.publication="${REFRESH_ID}"
# REFRESH_ID changes on every run/attempt, including unchanged Flutter releases.
COPY sanitize-sdk-keys.py /usr/local/lib/flutter-runtime/
RUN test -n "$REFRESH_ID" && apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git unzip xz-utils zip bash python3 jq \
      libglu1-mesa libgtk-3-0 libstdc++6 clang cmake ninja-build pkg-config \
    && python3 /usr/local/lib/flutter-runtime/sanitize-sdk-keys.py system \
    && rm -rf /var/lib/apt/lists/*
COPY --from=resolution resolved.json /usr/local/share/flutter-runtime/resolved.json
COPY install.sh metadata.py sanitize-template-key.py prepare-sdk-git.py /usr/local/lib/flutter-runtime/
ENV FLUTTER_ROOT=/opt/flutter \
    PATH=/opt/flutter/bin:/opt/flutter/bin/cache/dart-sdk/bin:$PATH \
    HOME=/home/runtime \
    PUB_CACHE=/cache/pub \
    GRADLE_USER_HOME=/cache/gradle \
    CI=true
RUN git config --system --add safe.directory /opt/flutter \
    && mkdir -p /home/runtime /cache/pub /cache/gradle /workspace \
    && bash /usr/local/lib/flutter-runtime/install.sh flutter \
    && chmod -R a+rwX /opt/flutter /home/runtime /cache /workspace
WORKDIR /workspace

FROM sdk AS lightweight
RUN python3 /usr/local/lib/flutter-runtime/metadata.py lightweight
USER 10001:10001
CMD ["flutter", "--version"]

FROM sdk AS full
COPY cache-engine.py /usr/local/lib/flutter-runtime/
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    ANDROID_HOME=/opt/android-sdk \
    ANDROID_SDK_ROOT=/opt/android-sdk \
    PATH=/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:$PATH
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-21-jdk-headless \
    && python3 /usr/local/lib/flutter-runtime/sanitize-sdk-keys.py system \
    && rm -rf /var/lib/apt/lists/* \
    && bash /usr/local/lib/flutter-runtime/install.sh android \
    && python3 /usr/local/lib/flutter-runtime/cache-engine.py \
    && chmod -R a+rwX /opt/flutter /opt/android-sdk /home/runtime /cache \
    && python3 /usr/local/lib/flutter-runtime/metadata.py full
# Flutter's Gradle plugin uses this URI for its engine Maven repository.
# All supported SDK artifacts are already cached; in-container upgrades are unsupported.
ENV FLUTTER_STORAGE_BASE_URL=file:///opt/flutter-storage
USER 10001:10001
CMD ["flutter", "--version"]
