FROM ubuntu:24.04

ARG FLUTTER_URL
ARG FLUTTER_SHA256
ARG FLUTTER_VERSION
ARG FLUTTER_REVISION
ARG SOURCE_REVISION
LABEL org.opencontainers.image.source="https://github.com/mkapusnik-apps/commons" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.version="${FLUTTER_VERSION}" \
      io.commons.flutter.revision="${FLUTTER_REVISION}" \
      io.commons.flutter.variant="slim"

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git unzip xz-utils zip bash \
      libglu1-mesa libgtk-3-0 libstdc++6 clang cmake ninja-build pkg-config \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 flutter \
    && useradd --uid 10001 --gid flutter --create-home flutter

ENV FLUTTER_ROOT=/opt/flutter \
    PATH=/opt/flutter/bin:/opt/flutter/bin/cache/dart-sdk/bin:$PATH \
    HOME=/home/flutter \
    PUB_CACHE=/cache/pub \
    GRADLE_USER_HOME=/cache/gradle \
    CI=true
RUN curl --fail --location "$FLUTTER_URL" --output /tmp/flutter.tar.xz \
    && printf '%s  /tmp/flutter.tar.xz\n' "$FLUTTER_SHA256" | sha256sum --check \
    && tar --no-same-owner -xJf /tmp/flutter.tar.xz -C /opt \
    && rm /tmp/flutter.tar.xz \
    && mkdir -p /cache/pub /cache/gradle /workspace \
    && chown -R flutter:flutter /opt/flutter /cache /workspace

USER 10001:10001
WORKDIR /workspace
RUN flutter config --no-analytics --no-cli-animations \
    && flutter precache --linux --no-android --no-ios --no-web --no-macos --no-windows --no-fuchsia \
    && flutter --version \
    && chmod -R g+rwX /opt/flutter /home/flutter /cache /workspace
CMD ["flutter", "--version"]
