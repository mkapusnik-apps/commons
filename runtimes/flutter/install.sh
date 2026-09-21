#!/usr/bin/env bash
set -euo pipefail
selection=/usr/local/share/flutter-runtime/resolved.json

case "$1" in
  flutter)
    curl --fail --location "$(jq -r .flutter_archive_url "$selection")" --output /tmp/flutter.tar.xz
    printf '%s  /tmp/flutter.tar.xz\n' "$(jq -r .flutter.sha256 "$selection")" | sha256sum --check
    tar -xJf /tmp/flutter.tar.xz -C /opt
    rm /tmp/flutter.tar.xz
    flutter config --no-analytics --no-cli-animations
    # Universal artifacts and the Linux host engine support flutter_tester.
    flutter precache --linux --no-android --no-ios --no-web --no-macos --no-windows --no-fuchsia
    ;;
  android)
    curl --fail --location "$(jq -r .android_command_line_tools_url "$selection")" --output /tmp/android.zip
    printf '%s  /tmp/android.zip\n' "$(jq -r .android_command_line_tools_sha1 "$selection")" | sha1sum --check
    mkdir -p "$ANDROID_HOME/cmdline-tools"
    unzip -q /tmp/android.zip -d "$ANDROID_HOME/cmdline-tools"
    mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest"
    rm /tmp/android.zip
    # Ignore only yes's expected SIGPIPE; sdkmanager's own status remains fatal.
    set +o pipefail
    yes | sdkmanager --sdk_root="$ANDROID_HOME" --licenses >/dev/null
    set -o pipefail
    mapfile -t packages < <(jq -r '.android_packages[]' "$selection")
    sdkmanager --sdk_root="$ANDROID_HOME" --install "${packages[@]}"
    flutter config --android-sdk "$ANDROID_HOME" --jdk-dir "$JAVA_HOME"
    flutter precache --android --no-ios --no-web --no-macos --no-windows --no-fuchsia
    ;;
  *) exit 2 ;;
esac

# Remove the verified out-of-scope signing asset before this installation layer ends.
python3 /usr/local/lib/flutter-runtime/sanitize-template-key.py
