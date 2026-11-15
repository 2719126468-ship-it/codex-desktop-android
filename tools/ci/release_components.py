"""Transfer verified release inputs between disposable jobs and reusable caches.

Only completed, public build outputs belong here. No compiler cache, SDK,
keystore, phone profile or arbitrary workspace directory is ever exported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile

import manual_release as release

FORMAT = "codex.release-component.v1"
NAMES = ("base", "mesa", "engine", "native", "client", "image")
RECIPES = {
    "base": ("tools/install/build_rootfs.py", "tools/install/verify_rootfs.py"),
    "mesa": ("tools/gpu/prepare-build.sh", "tools/gpu/build-mesa.sh", "tools/gpu/package-build.sh",
             "tools/gpu/mesa-*.patch", "tools/gpu/vulkan-clear-probe.c", "tools/gpu/glx-clear-probe.c",
             "tools/gpu/build-timestamp-probe.sh", "tools/gpu/vulkan-timestamp-probe.c",
             "tools/gpu/zink-partial-resolve-probe.c"),
    "engine": ("tools/executor/build-gnu-engine.py", "tools/executor/check-gnu-engine-elf.py",
               "tools/executor/collect-gnu-rootfs-libraries.py", "tools/executor/stage-gnu-engine-assets.py",
               "tools/recovery/restore-engine.py", "tools/ci/manual_release.py"),
    "native": ("config/android/native-baseline.json",),
}
IMAGE_FIELDS = ("desktopVersion", "baseSha256", "gpuSha256", "engineVersionOutput", "rustCompiler")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def keys(value, root=None):
    root = release.ROOT if root is None else Path(root)
    result = {}
    for name, patterns in RECIPES.items():
        paths = sorted({p for pattern in patterns for p in root.glob(pattern)})
        if not paths or any(not list(root.glob(pattern)) for pattern in patterns):
            raise ValueError("Missing component build recipe: " + name)
        recipe = {p.relative_to(root).as_posix(): release.digest(p) for p in paths}
        identity = {"format": FORMAT, "target": "ubuntu-24.04/aarch64-linux-gnu", "recipe": recipe}
        if name == "engine":
            identity.update(engine=value["engine"], rustToolchain=value["rustToolchain"])
        result[name] = hashlib.sha256(canonical(identity)).hexdigest()
    return result


def directory(name):
    if name not in NAMES:
        raise ValueError("Unknown release component")
    return release.WORK / "components" / name


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("A release component must contain self-contained regular files")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("Nonregular release component file")
        name = path.relative_to(root).as_posix()
        if name != "component.json":
            result[name] = {"sha256": release.digest(path), "bytes": path.stat().st_size}
    return result


def inspect(name, expected_key=None):
    root = directory(name)
    record = json.loads((root / "component.json").read_text())
    if record.get("format") != FORMAT or record.get("component") != name:
        raise ValueError("Different component identity")
    if expected_key is not None and record.get("key") != expected_key:
        raise ValueError("Component cache does not match the selected build inputs")
    if not record.get("files") or inventory(root) != record["files"]:
        raise ValueError("Release component files differ from their completed inventory")
    return record


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    # Hardlinks keep multi-GB image/archive transfers within a job cheap. Both
    # sides are immutable public inputs; artifact downloads use regular files.
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


def pack(name, key):
    value = release.state()
    root = directory(name)
    root.mkdir(parents=True, exist_ok=False)
    metadata = {}
    if name == "base":
        source = Path(value["baseArchive"])
        copy(source, root / "rootfs.tar.gz")
        copy(source.parent / "debian-13-arm64-provenance.tar.gz", root / "provenance.tar.gz")
        copy(source.parent / "manifest.json", root / "base-manifest.json")
        metadata = {"baseSha256": value["baseSha256"]}
    elif name == "mesa":
        copy(Path(value["gpuArchive"]), root / "mesa.tar.gz")
        metadata = {"gpuSha256": value["gpuSha256"]}
    elif name == "engine":
        state = json.loads(Path(value["engineBuildState"]).read_text())
        if not state["buildCompleted"] or not state["packageCompleted"] or state["buildExitCode"] != 0:
            raise ValueError("Only a completed engine build can be reused")
        copy(Path(state["package"]), root / "engine.tar.gz")
        copy(Path(state["source"]) / "codex-rs/Cargo.toml", root / "Cargo.toml")
        release.save(root / "producer-state.json", state)
        metadata = {"engine": value["engine"], "rustToolchain": value["rustToolchain"],
                    "rustCompiler": value["rustCompiler"], "engineVersionOutput": value["engineVersionOutput"],
                    "packageSha256": state["packageSha256"]}
    elif name == "native":
        copy(release.WORK / "native-baseline.apk", root / "native-baseline.apk")
        metadata = {"nativeBaseline": value["nativeBaseline"]}
    elif name == "client":
        for path in (release.WORK / "official-client").iterdir():
            if not path.is_file() or path.is_symlink():
                raise ValueError("Unexpected official client input")
            copy(path, root / "official-client" / path.name)
        metadata = {"desktopVersion": value["desktopVersion"], "desktopSelector": value["desktopSelector"]}
    elif name == "image":
        for path in (release.WORK / "phone-image/assets/phone-runtime").iterdir():
            copy(path, root / "assets/phone-runtime" / path.name)
        metadata = {field: value[field] for field in IMAGE_FIELDS}
        metadata.update(engine=value["engine"], components=value["components"])
    key = key or hashlib.sha256(canonical(metadata)).hexdigest()
    record = {"format": FORMAT, "component": name, "key": key, "metadata": metadata,
              "producer": {"sourceCommit": value["sourceCommit"], "runId": os.environ.get("GITHUB_RUN_ID")},
              "files": inventory(root)}
    release.save(root / "component.json", record)
    inspect(name, key)


def unpack(name, expected_key=None):
    record = inspect(name, expected_key)
    root, metadata, value = directory(name), record["metadata"], release.state()
    if name == "base":
        if metadata["baseSha256"] != record["files"]["rootfs.tar.gz"]["sha256"]:
            raise ValueError("Base archive identity differs")
        manifest = json.loads((root / "base-manifest.json").read_text())
        if manifest["rootfs"]["sha256"] != metadata["baseSha256"]:
            raise ValueError("Base provenance identity differs")
        value.update(baseArchive=str(root / "rootfs.tar.gz"), baseSha256=metadata["baseSha256"])
        value.pop("baseBuildDirectory", None)
    elif name == "mesa":
        if metadata["gpuSha256"] != record["files"]["mesa.tar.gz"]["sha256"]:
            raise ValueError("Mesa archive identity differs")
        value.update(gpuArchive=str(root / "mesa.tar.gz"), gpuSha256=metadata["gpuSha256"])
    elif name == "engine":
        prior = value.get("components", {}).get("engine")
        if prior and prior["sha256"] != release.digest(root / "component.json"):
            raise ValueError("APK and image must use the same engine component")
        if metadata["engine"] != value["engine"] or metadata["rustToolchain"] != value["rustToolchain"]:
            raise ValueError("Engine component differs from the selected version/patch/compiler selector")
        if metadata["packageSha256"] != record["files"]["engine.tar.gz"]["sha256"]:
            raise ValueError("Engine package identity differs")
        build = release.WORK / "imported-engine"
        package = build / "package"
        package.mkdir(parents=True, exist_ok=False)
        with tarfile.open(root / "engine.tar.gz") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            if len(names) != len(set(names)):
                raise ValueError("Duplicate engine package path")
            for member in members:
                path = PurePosixPath(member.name)
                if not member.isfile() or path.is_absolute() or ".." in path.parts or "\\" in member.name:
                    raise ValueError("Unexpected engine package member")
            descriptor = json.load(archive.extractfile("manifest.json"))
            if (descriptor["sourceBase"] != value["engine"]["base"]
                    or descriptor["patchSha256"] != value["engine"]["sha256"]
                    or descriptor["target"] != release.TARGET):
                raise ValueError("Engine package was built from different sources")
            if set(names) != {item["path"] for item in descriptor["files"]} | {"manifest.json"}:
                raise ValueError("Engine package contains unindexed files")
            archive.extractall(package, filter="data")
        for item in descriptor["files"]:
            path = package / item["path"]
            if release.digest(path) != item["sha256"] or path.stat().st_size != item["bytes"]:
                raise ValueError("Engine package inventory differs")
        source = build / "source/codex-rs"
        source.mkdir(parents=True)
        copy(root / "Cargo.toml", source / "Cargo.toml")
        original = json.loads((root / "producer-state.json").read_text())
        local = dict(original, source=str(source.parent), build=str(build), package=str(root / "engine.tar.gz"),
                     sourceMode="imported-release-component", importedComponentSha256=release.digest(root / "component.json"))
        state = build / "build-state.json"
        release.save(state, local)
        release.command("imported-engine-assets", [release.sys.executable, "-B",
            release.ROOT / "tools/executor/stage-gnu-engine-assets.py", "--state", state,
            "--output", release.WORK / "gnu-assets"])
        value.update(engineBuildState=str(state), rustCompiler=metadata["rustCompiler"],
                     engineVersionOutput=metadata["engineVersionOutput"])
    elif name == "native":
        if metadata["nativeBaseline"] != value["nativeBaseline"]:
            raise ValueError("Different native baseline selected")
        if record["files"]["native-baseline.apk"]["sha256"] != value["nativeBaseline"]["sha256"]:
            raise ValueError("Native baseline digest differs")
        copy(root / "native-baseline.apk", release.WORK / "native-baseline.apk")
    elif name == "client":
        if metadata["desktopSelector"] != value["desktopSelector"]:
            raise ValueError("Different desktop selector")
        shutil.copytree(root / "official-client", release.WORK / "official-client")
        value["desktopVersion"] = metadata["desktopVersion"]
    elif name == "image":
        if metadata["engine"] != value["engine"]:
            raise ValueError("Image contains a different backend")
        destination = release.WORK / "phone-image/assets/phone-runtime"
        destination.mkdir(parents=True, exist_ok=False)
        for path in (root / "assets/phone-runtime").iterdir():
            copy(path, destination / path.name)
        value.update({field: metadata[field] for field in IMAGE_FIELDS})
        value["components"] = metadata["components"]
    value.setdefault("components", {})[name] = {"key": record["key"],
        "sha256": release.digest(root / "component.json"), "producer": record["producer"]}
    release.save(release.WORK / "plan.json", value)


def build(name, key):
    release.prepare_workspace()
    if name == "engine":
        unpack("base", keys(release.state())["base"])
    {"base": release.base, "mesa": release.gpu, "engine": release.engine,
     "native": release.acquire_native_baseline}[name]()
    pack(name, key)


def outputs(values):
    for name, value in values.items():
        print(f"{name}={value}")
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
            for name, value in values.items():
                stream.write(f"{name}={value}\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("keys", "probe", "pack", "unpack", "build"))
    parser.add_argument("component", nargs="?", choices=NAMES)
    parser.add_argument("--key")
    args = parser.parse_args()
    if args.action == "keys":
        outputs({name + "_key": key for name, key in keys(release.state()).items()})
        return
    if not args.component:
        parser.error("Select a component")
    key = args.key or (keys(release.state()).get(args.component))
    if args.action == "probe":
        if not directory(args.component).exists():
            outputs({"ready": "false"})
        else:
            inspect(args.component, key)
            outputs({"ready": "true", "digest": release.digest(directory(args.component) / "component.json")})
    elif args.action == "pack":
        pack(args.component, key)
    elif args.action == "unpack":
        unpack(args.component, key)
    elif args.action == "build":
        build(args.component, key)


if __name__ == "__main__":
    main()
