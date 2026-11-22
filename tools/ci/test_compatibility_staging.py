import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile


SCRIPT = Path(__file__).with_name("stage-compatibility-apk.py")
SPEC = importlib.util.spec_from_file_location("compatibility_staging", SCRIPT)
staging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(staging)


class CompatibilityStagingTests(unittest.TestCase):
    def make_apk(self, path, *, extra=()):
        native = {
            "libcodex_shizuku_transport.so": "transport-bytes",
            "libcodex_bionic_cwd.so": "cwd-bytes",
            "libcodex_test_executor.so": "executor-bytes",
        }
        deployment = {name: hashlib.sha256(value.encode()).hexdigest() for name, value in native.items()}
        phone_inventory = b'{"files":[]}'
        phone_release = {"format": "codex.phone-image.v1", "inventorySha256": hashlib.sha256(phone_inventory).hexdigest(),
                         "inventoryBytes": len(phone_inventory), "accountIncluded": False, "keyringIncluded": False,
                         "client": {"version": "test"}}
        payloads = {
            "assets/codex-executor-deployment.json": json.dumps({"nativeLibraries": deployment}).encode(),
            "assets/codex-executor-manifest.json": b"[]",
            "assets/codex-executor-evidence.json": b"{}",
            "assets/codex-executor-qualification.json": b"{}",
            "assets/codex-app-launch-build.json": b"{}",
            "assets/codex-python-runtime.json": b"{}",
            "assets/gnu-engine/manifest.json": json.dumps({
                "schema": "codex.gnu-engine.payload.v1", "target": "aarch64-unknown-linux-gnu",
                "files": [{"name": "codex-native"}, {"name": "codex-code-mode-host"}],
            }).encode(),
            "assets/desktop-client/manifest.json": json.dumps({
                "schema": "codex.desktop.payload.v1", "architecture": "arm64", "version": "test",
            }).encode(),
            "assets/phone-runtime/release.json": json.dumps(phone_release).encode(),
            "assets/phone-runtime/inventory.json": phone_inventory,
            "assets/codex-executor/probe.py": b"probe = True\n",
            "assets/bionic-python/lib/python3.14/os.py": b"# runtime\n",
        }
        libs = {"libproot.so", "libproot-loader.so", "libproot-loader32.so", "libtalloc.so",
                "libandroid-shmem.so", "libXlorie.so", *native}
        payloads.update({"lib/arm64-v8a/" + name: b"ELF fixture" for name in libs})
        for name, content in native.items():
            payloads["lib/arm64-v8a/" + name] = content.encode()
        payloads.update(extra)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, content in payloads.items():
                archive.writestr(name, content)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_stages_pinned_arm64_runtime_without_external_archives(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apk = root / "v80.apk"
            digest = self.make_apk(apk)
            with patch.object(staging, "V80_APK_SHA256", digest):
                report = staging.stage(apk, root / "stage")
            self.assertEqual(report["executor_libraries"], 1)
            self.assertTrue((root / "stage/executor/assets/codex-executor/probe.py").is_file())
            self.assertTrue((root / "stage/executor/assets/bionic-python/lib/python3.14/os.py").is_file())
            self.assertTrue((root / "stage/executor/jniLibs/arm64-v8a/libcodex_test_executor.so").is_file())
            manifest = json.loads((root / "stage/transport-inputs.json").read_text())
            self.assertEqual(manifest["schema"], "codex.v80-transport-inputs.v1")
            self.assertEqual(manifest["sourceApkSha256"], digest)
            self.assertEqual(set(manifest["libraries"]), staging.TRANSPORT)
            self.assertFalse((root / "stage/executor/assets/phone-runtime/codex-phone-rootfs.tar.gz").exists())

    def test_refuses_unexpected_android_abi(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apk = root / "v80.apk"
            digest = self.make_apk(apk, extra={"lib/armeabi-v7a/libunexpected.so": b"ELF"})
            with patch.object(staging, "V80_APK_SHA256", digest):
                with self.assertRaisesRegex(ValueError, "only its verified arm64-v8a"):
                    staging.stage(apk, root / "stage")

    def test_rejects_wrong_release_digest_before_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apk = root / "v80.apk"
            self.make_apk(apk)
            with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
                staging.stage(apk, root / "stage")
            self.assertFalse((root / "stage").exists())


if __name__ == "__main__":
    unittest.main()
