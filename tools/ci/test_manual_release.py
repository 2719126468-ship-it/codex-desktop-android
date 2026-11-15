"""Release selection, dispatch boundaries and publication admission; no network/device."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_STORED

import manual_release as release

SPEC = importlib.util.spec_from_file_location("release_candidate", release.ROOT / "tools/runtime/build-production-candidate.py")
candidate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(candidate)
engine_builder = release.module("release_engine_builder", "tools/executor/build-gnu-engine.py")


class RustEnvironmentTests(unittest.TestCase):
    def test_first_build_initializes_missing_cache_homes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cargo, rustup = root / "cache/cargo", root / "cache/rustup"
            with patch.dict(os.environ, CARGO_HOME=str(cargo), RUSTUP_HOME=str(rustup)):
                env = release.rust_environment("stable")
            self.assertTrue(cargo.resolve(strict=True).is_dir())
            self.assertTrue(rustup.resolve(strict=True).is_dir())
            self.assertEqual(env["RUSTUP_TOOLCHAIN"], "stable")
            self.assertEqual(env["CARGO_HOME"], str(cargo))

    def test_existing_cache_contents_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cargo, rustup = root / "cargo", root / "rustup"
            cargo.mkdir()
            cached = cargo / "retained-package"
            cached.write_bytes(b"existing package")
            with patch.dict(os.environ, CARGO_HOME=str(cargo), RUSTUP_HOME=str(rustup)):
                release.rust_environment("1.99.1")
            self.assertEqual(cached.read_bytes(), b"existing package")


class NativeBaselineTests(unittest.TestCase):
    def test_cached_baseline_is_rechecked_and_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            apk = work / "native-baseline.apk"
            apk.write_bytes(b"reviewed APK input")
            selected = {"nativeBaseline": {"url": "https://example.com/input.apk", "sha256": release.digest(apk)}}
            with patch.object(release, "WORK", work), patch.object(release, "state", return_value=selected), \
                    patch.object(release, "fetch") as fetch:
                self.assertEqual(release.acquire_native_baseline(), apk)
                fetch.assert_not_called()
                apk.write_bytes(b"tampered APK input")
                with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
                    release.acquire_native_baseline()
                fetch.assert_not_called()


class EngineManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        source = self.root / "source"
        source.mkdir()
        (source / "example.rs").write_text("fn main() {}")
        deps = self.root / "deps/openssl"
        deps.mkdir(parents=True)
        (deps / "example.h").write_text("#define EXAMPLE 1")
        patch_file = self.evidence / "engine.patch"
        patch_file.write_text("a selected integration patch")
        recovery = {"base": "e" * 40, "sha256": release.digest(patch_file)}
        release.save(self.evidence / "recovery-manifest.json", recovery)
        self.state = {"schema": "codex.gnu-engine-build.v1", "sourceBase": recovery["base"],
            "patchSha256": recovery["sha256"], "evidence": str(self.evidence), "source": str(source),
            "dependencies": str(deps.parent), "builderSha256": release.digest(Path(engine_builder.__file__))}
        for name, key, contents in (
            ("SOURCES.json", "sourceManifestSha256", engine_builder.files(source)),
            ("DEPENDENCIES.json", "dependencyManifestSha256", engine_builder.files(deps)),
            ("DEPENDENCY-INPUTS.json", "dependencyInputsSha256", {}),
            ("DEPENDENCY-CHECKS.json", "dependencyChecksSha256", {})):
            path = self.evidence / name
            release.save(path, contents)
            self.state[key] = release.digest(path)
        for key in ("v8Archive", "v8Binding"):
            path = self.root / key
            path.write_bytes(b"a pinned V8 input")
            self.state[key] = str(path)
            self.state[key + "Sha256"] = release.digest(path)

    def test_builder_accepts_a_manifest_selected_base_without_a_hidden_commit_constant(self):
        self.assertEqual(engine_builder.validate(self.state), self.evidence)

    def test_selected_base_must_match_its_preserved_manifest(self):
        self.state["sourceBase"] = "f" * 40
        with self.assertRaisesRegex(RuntimeError, "build identity"):
            engine_builder.validate(self.state)

    def test_changed_integration_patch_is_rejected(self):
        (self.evidence / "engine.patch").write_text("a different patch")
        with self.assertRaisesRegex(RuntimeError, "build identity"):
            engine_builder.validate(self.state)


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {"tag": "rust-v1.2.3", "base": "a" * 40, "patch": "engine.patch", "sha256": "b" * 64}

    def test_supported_uses_one_manifest_without_an_additional_version_pin(self):
        self.assertEqual(release.engine_selection("supported", self.manifest, None), self.manifest)

    def test_explicit_future_version_records_its_resolved_commit(self):
        seen = []
        def resolve(tag):
            seen.append(tag)
            return "c" * 40
        selected = release.engine_selection("9.8.7", self.manifest, resolve)
        self.assertEqual(seen, ["rust-v9.8.7"])
        self.assertEqual(selected["base"], "c" * 40)
        self.assertEqual(selected["tag"], "rust-v9.8.7")
        self.assertEqual(selected["sha256"], self.manifest["sha256"])
        self.assertEqual(self.manifest["base"], "a" * 40)

    def test_latest_is_resolved_and_frozen_before_building(self):
        def resolve(value):
            return "rust-v9.8.7" if value == "latest" else "c" * 40
        selected = release.engine_selection("latest", self.manifest, resolve)
        self.assertEqual((selected["tag"], selected["base"]), ("rust-v9.8.7", "c" * 40))

    def test_unresolvable_version_never_falls_back_to_an_old_backend(self):
        with self.assertRaisesRegex(ValueError, "one commit"):
            release.engine_selection("9.8.7", self.manifest, lambda _: "")

    def test_shell_expressions_and_arbitrary_refs_are_rejected(self):
        for value in ("9.8.7;echo pwn", "$(id)", "main", "--upload-pack=x", "9.8.7\nother"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                release.engine_selection(value, self.manifest, lambda _: "c" * 40)

    def test_desktop_selector_requires_an_indexed_version(self):
        index = b"Package: chatgpt\nArchitecture: arm64\nVersion: 9.8.7\nFilename: pool/chatgpt.deb\n"
        self.assertEqual(release.select_client(index, "9.8.7")["version"], "9.8.7")
        with self.assertRaisesRegex(ValueError, "signed official"):
            release.select_client(index, "1.2.3")

    def test_desktop_filename_cannot_escape_the_official_repository(self):
        for name in ("../other.deb", "https://example.com/client.deb", "/tmp/client.deb", "pool\\client.deb"):
            index = f"Package: chatgpt\nArchitecture: arm64\nVersion: 9.8.7\nFilename: {name}\n".encode()
            with self.subTest(name=name), self.assertRaises(ValueError):
                release.select_client(index, "latest")


class FullImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        patched = patch.object(candidate, "ROOT", self.root)
        patched.start()
        self.addCleanup(patched.stop)
        self.phone = self.root / "phone/phone-runtime"
        self.phone.mkdir(parents=True)
        (self.phone / "codex-phone-rootfs.tar.gz").write_bytes(b"archive bytes" * 1024)
        inventory = b'{"format":"codex.phone-image.v1","files":[]}'
        (self.phone / "inventory.json").write_bytes(inventory)
        self.release = {"format": "codex.phone-image.v1", "archive": "codex-phone-rootfs.tar.gz",
            "accountIncluded": False, "keyringIncluded": False, "inventoryBytes": len(inventory),
            "inventorySha256": hashlib.sha256(inventory).hexdigest(),
            "spec": {"compressedBytes": (self.phone / "codex-phone-rootfs.tar.gz").stat().st_size,
                     "sha256": candidate.digest_file(self.phone / "codex-phone-rootfs.tar.gz")}}
        self.write_release()
        self.args = argparse.Namespace(phone_image_assets=self.phone.parent)

    def write_release(self):
        (self.phone / "release.json").write_text(json.dumps(self.release))

    def test_actual_apk_carries_the_exact_selected_image(self):
        auxiliary = candidate.auxiliary_inputs(self.args)
        apk = self.root / "full.apk"
        with ZipFile(apk, "w", compression=ZIP_STORED) as zipped:
            for path in self.phone.iterdir():
                zipped.write(path, "assets/phone-runtime/" + path.name)
        candidate.verify_auxiliary_apk(apk, auxiliary)
        # A different archive with the same filename must be rejected.
        with ZipFile(apk, "w") as zipped:
            for path in self.phone.iterdir():
                zipped.writestr("assets/phone-runtime/" + path.name,
                    b"tampered" if path.name.endswith("tar.gz") else path.read_bytes())
        with self.assertRaisesRegex(ValueError, "Packaged phone image"):
            candidate.verify_auxiliary_apk(apk, auxiliary)

    def test_changed_archive_is_rejected_before_gradle(self):
        (self.phone / "codex-phone-rootfs.tar.gz").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "trusted descriptor"):
            candidate.auxiliary_inputs(self.args)

    def test_changed_inventory_is_rejected_before_gradle(self):
        (self.phone / "inventory.json").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "trusted descriptor"):
            candidate.auxiliary_inputs(self.args)

    def test_account_keyring_and_uninventoried_inputs_are_rejected(self):
        for field in ("accountIncluded", "keyringIncluded"):
            self.release[field] = True
            self.write_release()
            with self.assertRaisesRegex(ValueError, "trusted descriptor"):
                candidate.auxiliary_inputs(self.args)
            self.release[field] = False
        self.write_release()
        (self.phone / "auth.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "only"):
            candidate.auxiliary_inputs(self.args)

    def test_android_version_fields_do_not_accept_shell_or_invalid_codes(self):
        for code in (0, -1, 2100000001):
            with self.assertRaises(ValueError):
                candidate.auxiliary_inputs(argparse.Namespace(version_code=code))
        for name in ("bad\nname", "$(id)", "name with spaces"):
            with self.assertRaises(ValueError):
                candidate.auxiliary_inputs(argparse.Namespace(version_name=name))


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        (self.work / "release").mkdir()
        self.description = "A configured release note"
        self.value = {"releaseTag": "v123", "sourceCommit": "c" * 40, "apk": "full.apk",
            "apkBytes": 1234, "apkSha256": "a" * 64, "description": self.description,
            "desktopVersion": "9.8.7", "engine": {"tag": "rust-v9.8.7"}}
        (self.work / "release/build-info.json").write_text(json.dumps(self.value))
        self.env = patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_STEP_SUMMARY": str(self.work / "step-summary.md")})
        self.env.start()
        self.addCleanup(self.env.stop)
        patched = patch.object(release, "WORK", self.work)
        patched.start()
        self.addCleanup(patched.stop)

    def metadata(self, digest="a" * 64):
        return {"id": 123, "tag_name": "v123", "draft": True,
                "assets": [{"name": "full.apk", "size": 1234, "digest": "sha256:" + digest}]}

    def test_publication_is_refused_for_an_automatic_event(self):
        with patch.dict(os.environ, GITHUB_EVENT_NAME="push"), patch.object(release, "command") as command:
            with self.assertRaisesRegex(RuntimeError, "explicitly dispatched"):
                release.publish()
            command.assert_not_called()

    def test_existing_release_is_preserved(self):
        with patch.object(release.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
            with self.assertRaises(FileExistsError):
                release.publish()

    def test_bad_upload_digest_never_publishes_the_draft(self):
        with patch.object(release.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)), \
                patch.object(release, "run", return_value=json.dumps([self.metadata("b" * 64)])), \
                patch.object(release, "command") as command:
            with self.assertRaisesRegex(ValueError, "remains draft"):
                release.publish()
            self.assertNotIn("release-publish", [call.args[0] for call in command.call_args_list])

    def test_verified_upload_publishes_with_configured_notes(self):
        result = {"draft": False, "body": self.description, "html_url": "https://github.com/owner/repo/releases/tag/v123"}
        with patch.object(release.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)), \
                patch.object(release, "run", return_value=json.dumps([self.metadata()])), \
                patch.object(release, "command", side_effect=lambda label, argv: json.dumps(result) if label == "release-publish" else "") as command:
            release.publish()
            published = next(call.args[1] for call in command.call_args_list if call.args[0] == "release-publish")
            self.assertIn("repos/owner/repo/releases/123", published)
            self.assertEqual(json.loads((self.work / "publish-release.json").read_text()),
                             {"draft": False, "body": self.description})
            self.assertNotIn("--generate-notes", published)
            summary = (self.work / "step-summary.md").read_text()
            self.assertIn("Desktop: 9.8.7; backend: rust-v9.8.7", summary)

    def test_missing_draft_never_publishes_via_a_by_tag_lookup(self):
        with patch.object(release.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)), \
                patch.object(release, "run", return_value="[]"), patch.object(release, "command") as command:
            with self.assertRaisesRegex(ValueError, "identify the new draft"):
                release.publish()
            self.assertNotIn("release-publish", [call.args[0] for call in command.call_args_list])


if __name__ == "__main__":
    unittest.main()
