ARG SLIM_IMAGE=commons-flutter:slim
FROM ${SLIM_IMAGE}

LABEL io.commons.flutter.variant="full"
# Official Google bootstrap archive; update the revision and checksum together.
ARG ANDROID_COMMAND_LINE_TOOLS=16111833
ARG ANDROID_COMMAND_LINE_TOOLS_SHA1=e025545c62a8e64c7559119566a569fb1dec5f60
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    ANDROID_HOME=/opt/android-sdk \
    ANDROID_SDK_ROOT=/opt/android-sdk \
    PATH=/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:$PATH

USER root
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-21-jdk-headless \
    && rm -rf /var/lib/apt/lists/* \
    && curl --fail --location \
      "https://dl.google.com/android/repository/commandlinetools-linux-${ANDROID_COMMAND_LINE_TOOLS}_latest.zip" \
      --output /tmp/android.zip \
    && printf '%s  /tmp/android.zip\n' "$ANDROID_COMMAND_LINE_TOOLS_SHA1" | sha1sum --check \
    && mkdir -p "$ANDROID_HOME/cmdline-tools" \
    && unzip -q /tmp/android.zip -d "$ANDROID_HOME/cmdline-tools" \
    && mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest" \
    && rm /tmp/android.zip \
    && chown -R flutter:flutter "$ANDROID_HOME"

USER 10001:10001
# The pipeline returns sdkmanager's status, not yes's expected SIGPIPE.
RUN yes | sdkmanager --sdk_root="$ANDROID_HOME" --licenses >/dev/null \
    && sdkmanager --sdk_root="$ANDROID_HOME" --install \
      "platform-tools" \
      "platforms;android-34" "platforms;android-35" "platforms;android-36" \
      "build-tools;35.0.0" "build-tools;36.0.0" \
      "ndk;28.2.13676358" "cmake;3.22.1" \
    && flutter config --android-sdk "$ANDROID_HOME" --jdk-dir "$JAVA_HOME" \
    && flutter precache --android --no-ios --no-web --no-macos --no-windows --no-fuchsia \
    && flutter --version && java -version && sdkmanager --version \
    && chmod -R g+rwX /opt/flutter "$ANDROID_HOME" /home/flutter /cache /workspace
CMD ["flutter", "--version"]
