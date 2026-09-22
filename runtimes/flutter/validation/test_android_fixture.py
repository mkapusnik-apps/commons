"""Synthetic Android fixture configuration follows the selected SDK's Kotlin."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import worker


class AndroidFixtureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.android = self.project / "android"
        (self.android / "app").mkdir(parents=True)
        (self.android / "gradle/wrapper").mkdir(parents=True)
        (self.android / "gradle.properties").write_text("org.gradle.jvmargs=-Xmx2G\n")
        (self.android / "app/build.gradle.kts").write_text("android {\n    compileSdk = flutter.compileSdkVersion\n}\n")
        self.settings = self.android / "settings.gradle.kts"
        self.template = '''plugins {
    id("com.android.application") version "9.1.0" apply false
    id("org.jetbrains.kotlin.android") version "2.4.0" apply false
}
'''
        self.settings.write_text(self.template)
        patcher = patch.object(worker, "PROJECT", self.project)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_sdk34_retains_supported_tools_but_uses_selected_template_kotlin(self):
        self.assertEqual(worker.configure_android("sdk34"), "2.4.0")
        settings = self.settings.read_text()
        self.assertIn('version "2.4.0"', settings)
        self.assertNotIn('version "2.1.0"', settings)
        self.assertIn('version "8.11.1"', settings)
        self.assertNotIn("@KOTLIN@", settings)
        build = (self.android / "app/build.gradle.kts").read_text()
        for expected in ('compileSdk = 34', 'targetSdk = 34', 'buildToolsVersion = "35.0.0"',
                         'ndkVersion = "28.2.13676358"', 'version = "3.22.1"'):
            self.assertIn(expected, build)
        self.assertIn("gradle-8.14-bin.zip", (self.android / "gradle/wrapper/gradle-wrapper.properties").read_text())
        self.assertIn("android.builder.sdkDownload=false", (self.android / "gradle.properties").read_text())
        self.assertIn("add_library(readiness SHARED", (self.android / "app/src/main/cpp/CMakeLists.txt").read_text())

    def test_new_template_version_is_used_without_changing_fixed_fixture(self):
        self.settings.write_text(self.template.replace('"2.4.0"', '"2.5.1"'))
        self.assertEqual(worker.configure_android("sdk35"), "2.5.1")
        self.assertIn('version "2.5.1"', self.settings.read_text())
        self.assertIn('version "8.13.2"', self.settings.read_text())
        self.assertIn("gradle-9.4.1-bin.zip", (self.android / "gradle/wrapper/gradle-wrapper.properties").read_text())

    def test_sdk36_preserves_platform_and_build_tools(self):
        worker.configure_android("sdk36")
        build = (self.android / "app/build.gradle.kts").read_text()
        self.assertIn("compileSdk = 36", build)
        self.assertIn('buildToolsVersion = "36.0.0"', build)

    def test_default_template_settings_are_not_rewritten(self):
        self.assertEqual(worker.configure_android("defaults"), "2.4.0")
        self.assertEqual(self.settings.read_text(), self.template)
        self.assertIn("flutter.compileSdkVersion", (self.android / "app/build.gradle.kts").read_text())

    def test_missing_duplicate_and_nonliteral_versions_fail_closed(self):
        for template in ("plugins {}", self.template + self.template,
                         self.template.replace('"2.4.0"', 'kotlinVersion'),
                         self.template.replace('"2.4.0"', '"$kotlinVersion"')):
            with self.subTest(template=template):
                self.settings.write_text(template)
                with self.assertRaisesRegex(ValueError, "one literal Kotlin version"):
                    worker.configure_android("sdk34")
                self.assertEqual(self.settings.read_text(), template)

    def test_generated_spacing_is_supported(self):
        template = 'id( "org.jetbrains.kotlin.android" )\n    version\n    "2.4.0" apply false'
        self.assertEqual(worker.template_kotlin_version(template), "2.4.0")


if __name__ == "__main__":
    unittest.main()
