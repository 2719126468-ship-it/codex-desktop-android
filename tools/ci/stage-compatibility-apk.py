"""Stage pinned, non-runtime inputs for the API 27 ARM64 CI APK build."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile


V80_APK_SHA256 = "9d9101e1a80bdaf492c02e5abc71b550cb9658aa83782e410d76cef400d12e6b"
RUNTIME = {
    "libproot.so", "libproot-loader.so", "libproot-loader32.so", "libtalloc.so",
    "libandroid-shmem.so",
}
TRANSPORT = {"libcodex_shizuku_transport.so", "libcodex_bionic_cwd.so"}
REQUIRED_ASSETS = {
    "assets/codex-executor-deployment.json",
    "assets/codex-executor-manifest.json",
    "assets/codex-executor-evidence.json",
    "assets/codex-executor-qualification.json",
    "assets/codex-app-launch-build.json",
    "assets/codex-python-runtime.json",
    "assets/gnu-engine/manifest.json",
    "assets/desktop-client/manifest.json",
    "assets/phone-runtime/release.json",
    "assets/phone-runtime/inventory.json",
}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_member(info):
    name = info.filename
    path = PurePosixPath(name)
    if ("\\" in name or path.is_absolute() or not path.parts
            or any(part in {"", ".", ".."} for part in path.parts)):
        raise ValueError("Unsafe APK entry: " + name)
    if stat.S_ISLNK(info.external_attr >> 16):
        raise ValueError("Symlink APK entry is not accepted: " + name)


def copy_entry(archive, name, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(name) as source, destination.open("xb") as output:
        while block := source.read(1024 * 1024):
            output.write(block)


def selected_asset(name):
    if name in REQUIRED_ASSETS:
        return True
    if name.startswith(("assets/codex-executor/", "assets/codex-executor-", "assets/bionic-python/")):
        return True
    return False


def stage(apk, output):
    if digest(apk) != V80_APK_SHA256:
        raise ValueError("The v80 source APK SHA-256 differs from the pinned release asset")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    roots = {
        "assets": output / "executor/assets",
        "x11": output / "x11/arm64-v8a",
        "transport": output / "transport/arm64-v8a",
        "executor_jni": output / "executor/jniLibs/arm64-v8a",
    }
    for path in (*roots.values(), output / "debug-jni", output / "debug-assets"):
        path.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(apk) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("The pinned APK contains duplicate ZIP entries")
        by_name = {info.filename: info for info in infos}
        for info in infos:
            validate_member(info)
        missing = REQUIRED_ASSETS - set(names)
        if missing:
            raise ValueError("The v80 APK is missing required external-environment assets: " + str(sorted(missing)))

        libraries = {name.removeprefix("lib/arm64-v8a/") for name in names
                     if name.startswith("lib/arm64-v8a/") and not name.endswith("/")}
        abis = {PurePosixPath(name).parts[1] for name in names
                if name.startswith("lib/") and len(PurePosixPath(name).parts) > 2}
        if abis != {"arm64-v8a"}:
            raise ValueError("The pinned v80 APK must contain only its verified arm64-v8a native payload")
        required_runtime = RUNTIME | {"libXlorie.so"} | TRANSPORT
        if not required_runtime.issubset(libraries):
            raise ValueError("The v80 APK is missing runtime JNI: " + str(sorted(required_runtime - libraries)))

        deployment = json.loads(archive.read("assets/codex-executor-deployment.json"))
        native = deployment.get("nativeLibraries")
        if not isinstance(native, dict) or not TRANSPORT.issubset(native):
            raise ValueError("The v80 executor deployment has an unexpected native inventory")
        executor_libraries = set(native) - TRANSPORT
        if not executor_libraries or any(not re.fullmatch(r"lib[A-Za-z0-9_.-]+\.so", name)
                                         for name in executor_libraries):
            raise ValueError("The v80 executor native inventory contains invalid library names")

        for name in (*TRANSPORT, *executor_libraries):
            entry = "lib/arm64-v8a/" + name
            if entry not in by_name:
                raise ValueError("The v80 APK is missing executor JNI: " + name)
            data = archive.read(entry)
            expected = native[name] if name in native else None
            if expected is not None and hashlib.sha256(data).hexdigest() != expected:
                raise ValueError("The v80 executor JNI hash differs from its deployment: " + name)

        phone_release = json.loads(archive.read("assets/phone-runtime/release.json"))
        phone_inventory = archive.read("assets/phone-runtime/inventory.json")
        if (phone_release.get("format") != "codex.phone-image.v1"
                or phone_release.get("inventorySha256") != hashlib.sha256(phone_inventory).hexdigest()
                or phone_release.get("inventoryBytes") != len(phone_inventory)
                or phone_release.get("accountIncluded") is not False
                or phone_release.get("keyringIncluded") is not False):
            raise ValueError("The v80 phone environment descriptors do not match")
        desktop = json.loads(archive.read("assets/desktop-client/manifest.json"))
        if (desktop.get("schema") != "codex.desktop.payload.v1" or desktop.get("architecture") != "arm64"
                or desktop.get("version") != phone_release.get("client", {}).get("version")):
            raise ValueError("The v80 desktop and phone environment descriptors do not match")
        gnu = json.loads(archive.read("assets/gnu-engine/manifest.json"))
        gnu_files = gnu.get("files", [])
        if (gnu.get("schema") != "codex.gnu-engine.payload.v1"
                or gnu.get("target") != "aarch64-unknown-linux-gnu" or len(gnu_files) != 2
                or {row.get("name") for row in gnu_files} != {"codex-native", "codex-code-mode-host"}):
            raise ValueError("The v80 GNU engine descriptor is invalid")

        transport_manifest = {
            "schema": "codex.v80-transport-inputs.v1",
            "sourceApkSha256": V80_APK_SHA256,
            "libraries": {name: native[name] for name in sorted(TRANSPORT)},
        }
        with (output / "transport-inputs.json").open("x", encoding="utf-8") as stream:
            json.dump(transport_manifest, stream, sort_keys=True, indent=2)
            stream.write("\n")

        for name in names:
            if not name.startswith("assets/") or name.endswith("/"):
                continue
            if name.startswith(("assets/phone-runtime/", "assets/desktop-client/", "assets/gnu-engine/")):
                if name not in REQUIRED_ASSETS:
                    raise ValueError("The split APK unexpectedly embeds an environment archive: " + name)
            if selected_asset(name):
                copy_entry(archive, name, roots["assets"] / PurePosixPath(name).relative_to("assets"))

        for name in executor_libraries:
            copy_entry(archive, "lib/arm64-v8a/" + name, roots["executor_jni"] / name)
        for name in TRANSPORT:
            copy_entry(archive, "lib/arm64-v8a/" + name, roots["transport"] / name)
        copy_entry(archive, "lib/arm64-v8a/libXlorie.so", roots["x11"] / "libXlorie.so")

    return {"sha256": V80_APK_SHA256, "assets": len([n for n in names if selected_asset(n)]),
            "executor_libraries": len(executor_libraries), "x11": "libXlorie.so",
            "transport_libraries": sorted(TRANSPORT), "transport_manifest": "transport-inputs.json",
            "runtime": "built separately for API 27"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(stage(args.apk, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
