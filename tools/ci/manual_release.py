"""Manual hosted release stages; never read a phone or a maintainer's profile.

All selected versions and input hashes are frozen before packaging. The native
baseline is binary reuse, while the GNU backend and Linux image are new builds.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "work/manual-release"
REPOSITORY = "https://persistent.oaistatic.com/codex-app-prod/linux/deb/"
SIGNER = "3BFA0E4AE8B8CC16A2D9BA684A3B4A566C4660E4"
TARGET = "aarch64-unknown-linux-gnu"


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def state():
    return json.loads((WORK / "plan.json").read_text(encoding="utf-8"))


def run(argv, *, cwd=ROOT, env=None, input=None):
    return subprocess.check_output(list(map(str, argv)), cwd=cwd, env=env,
                                   input=input, text=True).strip()


def command(label, argv, *, cwd=ROOT, env=None, input=None):
    """Stream logs, retaining failures without printing command environment values."""
    logs = WORK / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    print(f"::group::{label}", flush=True)
    with (logs / (label + ".log")).open("w", encoding="utf-8") as log:
        process = subprocess.Popen(list(map(str, argv)), cwd=cwd, env=env, text=True,
            stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, errors="replace")
        if input is not None:
            process.stdin.write(input)
            process.stdin.close()
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
        code = process.wait()
    print("::endgroup::", flush=True)
    if code:
        raise RuntimeError(f"{label} failed ({code}); see work/manual-release/logs/{label}.log")
    return (logs / (label + ".log")).read_text(encoding="utf-8")


def fetch(url, destination, *, expected=None, limit=2 * 1024**3):
    """HTTPS only; large payloads are hashed as streams and never loaded in RAM."""
    if urllib.parse.urlsplit(url).scheme != "https":
        raise ValueError("Only HTTPS build inputs are allowed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "codex-android-manual-build"})
    count, sha = 0, hashlib.sha256()
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open("xb") as output:
        if urllib.parse.urlsplit(response.url).scheme != "https":
            raise ValueError("Build input redirected away from HTTPS")
        while block := response.read(1024 * 1024):
            count += len(block)
            if count > limit:
                raise ValueError("Build input exceeds its size bound")
            sha.update(block)
            output.write(block)
    if expected is not None and sha.hexdigest() != expected:
        raise ValueError("Build input SHA-256 differs: " + destination.name)
    temporary.rename(destination)
    return {"sha256": sha.hexdigest(), "bytes": count}


def engine_selection(requested, manifest, resolve):
    """A selector is not an implicit compatibility approval for a new release."""
    if requested in ("", "supported"):
        return dict(manifest)
    if requested == "latest":
        requested = resolve("latest")
    if re.fullmatch(r"(?:rust-v)?\d+\.\d+\.\d+(?:[-.][A-Za-z0-9.]+)?", requested) is None:
        raise ValueError("Codex selector must be supported, latest, or an upstream version/tag")
    tag = requested if requested.startswith("rust-v") else "rust-v" + requested
    result = dict(manifest)
    result.update(tag=tag, base=resolve(tag))
    if re.fullmatch(r"[0-9a-f]{40}", result["base"]) is None:
        raise ValueError("Selected Codex tag did not resolve to one commit")
    return result


def prepare_workspace():
    # Base-image and Mesa recipes use sudo. Create their shared parent as the
    # runner first, so later unprivileged engine evidence/V8 caches stay writable.
    for path in (WORK, ROOT / "downloads", ROOT / "downloads/engine-gnu-arm64", ROOT / "downloads/engine-v8"):
        path.mkdir(parents=True, exist_ok=True)
        if not os.access(path, os.W_OK | os.X_OK):
            raise RuntimeError("Build output is not writable by the runner: " + str(path))


def plan():
    if (WORK / "plan.json").exists():
        raise FileExistsError("Retain previous attempts; use a fresh checkout for another manual build")
    prepare_workspace()
    manifest_path = ROOT / "recovery/engine/manifest.json"
    manifest = json.loads(manifest_path.read_text())

    def resolve(value):
        if value == "latest":
            output = run(["git", "ls-remote", "--tags", manifest["upstream"], "refs/tags/rust-v*"])
            tags = {line.split()[1].removeprefix("refs/tags/") for line in output.splitlines()
                    if re.fullmatch(r"[0-9a-f]{40}\s+refs/tags/rust-v\d+\.\d+\.\d+", line)}
            if not tags:
                raise ValueError("Upstream has no stable Codex release tags")
            return max(tags, key=lambda tag: tuple(map(int, tag.removeprefix("rust-v").split("."))))
        output = run(["git", "ls-remote", "--tags", manifest["upstream"],
                      "refs/tags/" + value, "refs/tags/" + value + "^{}"])
        rows = dict(line.split()[::-1] for line in output.splitlines())
        return rows.get("refs/tags/" + value + "^{}", rows.get("refs/tags/" + value, ""))

    selected = engine_selection(os.environ.get("INPUT_ENGINE_REF", "supported").strip(), manifest, resolve)
    patch = manifest_path.parent / manifest["patch"]
    if digest(patch) != manifest["sha256"]:
        raise ValueError("Integration patch differs from the source manifest")
    destination = WORK / "engine-selection"
    destination.mkdir(parents=True)
    shutil.copyfile(patch, destination / patch.name)
    save(destination / "manifest.json", selected)
    desktop = os.environ.get("INPUT_DESKTOP_VERSION", "latest").strip() or "latest"
    if desktop != "latest" and not re.fullmatch(r"[0-9][A-Za-z0-9.+:~\-]*", desktop):
        raise ValueError("Invalid desktop version")
    rust = os.environ.get("INPUT_RUST_TOOLCHAIN", "stable").strip() or "stable"
    if rust != "stable" and not re.fullmatch(r"\d+\.\d+\.\d+", rust):
        raise ValueError("Rust toolchain must be stable or an exact version")
    app = (ROOT / "android/app/build.gradle").read_text(encoding="utf-8")
    source_code = int(re.search(r"codexVersionCode.*getOrElse\((\d+)\)", app)[1])
    supplied_code = os.environ.get("INPUT_VERSION_CODE", "").strip()
    code = int(supplied_code or source_code + int(os.environ.get("GITHUB_RUN_NUMBER", "1")))
    if not source_code < code <= 2100000000:
        raise ValueError("Use a versionCode larger than the current source version")
    tag = os.environ.get("INPUT_RELEASE_TAG", "").strip() or f"v{code}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-]{0,99}", tag):
        raise ValueError("Invalid release tag")
    baseline = json.loads((ROOT / "config/android/native-baseline.json").read_text())
    if (baseline.get("schema") != "codex.ci-native-baseline.v1"
            or not re.fullmatch(r"[0-9a-f]{64}", baseline.get("sha256", ""))
            or not re.fullmatch(r"[0-9a-f]{64}", baseline.get("certificateSha256", ""))):
        raise ValueError("Invalid native baseline descriptor")
    save(WORK / "plan.json", {"engine": selected, "desktopSelector": desktop, "rustToolchain": rust, "versionCode": code,
        "versionName": f"0.2.0-ci.{code}", "releaseTag": tag, "nativeBaseline": baseline,
        "nativeRebuilt": False, "deviceQualified": False,
        "sourceCommit": os.environ.get("GITHUB_SHA") or run(["git", "rev-parse", "HEAD"])})
    outputs = os.environ.get("GITHUB_OUTPUT")
    if outputs:
        with Path(outputs).open("a") as stream:
            stream.write(f"release_tag={tag}\nversion_code={code}\n")
    print(json.dumps(state(), indent=2))


def key_from_package(package, destination):
    """The downloaded key is trusted only after its existing pinned fingerprint matches."""
    raw = subprocess.check_output(["dpkg-deb", "--ctrl-tarfile", str(package)])
    if len(raw) > 8 * 1024**2:
        raise ValueError("Official package control exceeds its bound")
    candidates = []
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for entry in archive:
            if not entry.isfile() or entry.size > 4 * 1024**2:
                continue
            data = archive.extractfile(entry).read()
            candidates += re.findall(br"-----BEGIN PGP PUBLIC KEY BLOCK-----.*?-----END PGP PUBLIC KEY BLOCK-----", data, re.S)
            for encoded in re.findall(br"(?:[A-Za-z0-9+/=]{40,}\s*){3,}", data):
                try:
                    decoded = base64.b64decode(b"".join(encoded.split()), validate=True)
                except ValueError:
                    continue
                if decoded and (decoded[0] & 0x80 or b"-----BEGIN PGP PUBLIC KEY BLOCK-----" in decoded):
                    candidates.append(decoded)
    gpg_home = WORK / "gpg"
    gpg_home.mkdir(mode=0o700, exist_ok=True)
    for candidate in candidates:
        armored = WORK / "repository-key.asc"
        armored.write_bytes(candidate)
        try:
            listing = run(["gpg", "--homedir", gpg_home, "--batch", "--with-colons", "--show-keys", armored])
        except subprocess.CalledProcessError:
            continue
        fingerprints = [line.split(":")[9] for line in listing.splitlines() if line.startswith("fpr:")]
        if fingerprints and fingerprints[0] == SIGNER:
            if b"-----BEGIN PGP PUBLIC KEY BLOCK-----" in candidate:
                subprocess.run(["gpg", "--homedir", str(gpg_home), "--batch", "--yes", "--dearmor",
                                "--output", str(destination), str(armored)], check=True)
            else:
                destination.write_bytes(candidate)
            return
    raise ValueError("Official package does not contain the expected repository signing key")


def select_client(index, selector):
    sys.path.insert(0, str(ROOT / "tools/install"))
    import official_client_package as client
    records = [client.deb822(row) for row in index.split(b"\n\n") if row.strip()]
    records = [row for row in records if row.get("package") == "chatgpt" and row.get("architecture") == "arm64"]
    if selector != "latest":
        records = [row for row in records if row.get("version") == selector]
    if not records:
        raise ValueError("Requested desktop version is not in the signed official ARM64 index")
    selected = records[0]
    for row in records[1:]:
        if subprocess.run(["dpkg", "--compare-versions", row["version"], "gt", selected["version"]]).returncode == 0:
            selected = row
    name = selected["filename"]
    if (PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or "\\" in name
            or ":" in name or str(PurePosixPath(name)) != name):
        raise ValueError("Noncanonical package path in the signed index")
    return selected


def acquire_client():
    value = state()
    upstream = WORK / "official-client"
    upstream.mkdir()
    # The latest package supplies a public key, not executable build scripts.
    # Its payload is admitted only after the signed index authenticates it.
    bootstrap = upstream / "latest.deb"
    fetch(REPOSITORY + "latest/chatgpt_arm64.deb", bootstrap, limit=1024**3)
    key_from_package(bootstrap, upstream / "repository-key.gpg")
    fetch(REPOSITORY + "dists/stable/InRelease", upstream / "InRelease", limit=4 * 1024**2)
    verification = run(["gpgv", "--status-fd", "1", "--keyring", upstream / "repository-key.gpg", upstream / "InRelease"])
    if f"[GNUPG:] VALIDSIG {SIGNER} " not in verification:
        raise ValueError("Unexpected official repository signer")
    fetch(REPOSITORY + "dists/stable/main/binary-arm64/Packages", upstream / "Packages.arm64", limit=16 * 1024**2)
    index = (upstream / "Packages.arm64").read_bytes()
    binding = [hashlib.sha256(index).hexdigest(), str(len(index)), "main/binary-arm64/Packages"]
    signed = (upstream / "InRelease").read_text().split("SHA256:\n", 1)[1].split("SHA512:", 1)[0]
    if not any(line.split() == binding for line in signed.splitlines()):
        raise ValueError("ARM64 index does not match the official repository signature")
    selected = select_client(index, value["desktopSelector"])
    package = upstream / PurePosixPath(selected["filename"]).name
    if digest(bootstrap) == selected["sha256"]:
        bootstrap.rename(package)
    else:
        fetch(urllib.parse.urljoin(REPOSITORY, selected["filename"]), package, expected=selected["sha256"], limit=int(selected["size"]))
        bootstrap.unlink()
    if package.stat().st_size != int(selected["size"]):
        raise ValueError("Official desktop package size differs")
    value["desktopVersion"] = selected["version"]
    save(WORK / "plan.json", value)
    # Reject an unsupported ASAR before the expensive Rust/Mesa builds.
    command("client-extract", ["dpkg-deb", "--extract", package, WORK / "client-check"])
    command("client-adapter", [sys.executable, "-B", ROOT / "tools/runtime/install-workspace-provider.py",
        "--asar", WORK / "client-check/usr/lib/chatgpt/resources/app.asar", "--state", WORK / "client-adapter", "--check"])
    print("Authenticated desktop version: " + selected["version"])


def base():
    output = command("debian-base", ["sudo", "env", "CODEX_APT_FORCE_IPV4=1", sys.executable, "-B",
                                    ROOT / "tools/install/build_rootfs.py", "build"])
    result = json.loads(output.splitlines()[-1])
    value = state()
    value["baseArchive"] = str(Path(result["output"]) / "debian-13-arm64-rootfs.tar.gz")
    value["baseSha256"] = result["sha256"]
    value["baseBuildDirectory"] = result["buildDirectory"]
    save(WORK / "plan.json", value)


def gpu():
    command("mesa", ["sudo", "env", "CODEX_MESA_JOBS=2", "bash", ROOT / "tools/gpu/build-mesa.sh"])
    archives = list((ROOT / "downloads/gpu").glob("codex-mesa-*-arm64.tar.gz"))
    if len(archives) != 1:
        raise ValueError("Expected exactly one Mesa release archive")
    value = state()
    value.update(gpuArchive=str(archives[0]), gpuSha256=digest(archives[0]))
    save(WORK / "plan.json", value)


def rust_environment(toolchain):
    # A cache miss is normal on the first hosted build. rustup creates its own
    # home but does not necessarily create CARGO_HOME before Cargo first runs.
    for key in ("CARGO_HOME", "RUSTUP_HOME"):
        Path(os.environ[key]).expanduser().mkdir(parents=True, exist_ok=True)
    return dict(os.environ, RUSTUP_TOOLCHAIN=toolchain)


def engine():
    selected = WORK / "engine-selection/manifest.json"
    command("restore-engine", [sys.executable, "-B", ROOT / "tools/recovery/restore-engine.py",
        "--manifest", selected, "--destination", WORK / "engine"])
    # Some upstream release tags retain an older rust-toolchain.toml than the
    # MSRV of their locked dependencies. Select this explicitly at dispatch.
    toolchain = state()["rustToolchain"]
    env = rust_environment(toolchain)
    command("rust-toolchain", ["rustup", "toolchain", "install", toolchain, "--profile", "minimal", "--target", TARGET], env=env)
    builder = module("manual_gnu_builder", "tools/executor/build-gnu-engine.py")
    deps = WORK / "engine-deps"
    archive = WORK / "openssl.tar.gz"
    fetch(builder.OPENSSL_SOURCE_URL, archive, expected=builder.OPENSSL_SOURCE_SHA256)
    source = WORK / "openssl-source"
    source.mkdir()
    with tarfile.open(archive) as package:
        package.extractall(source, filter="data")
    source = next(source.iterdir())
    prefix = deps / "openssl"
    command("openssl-configure", ["perl", "./Configure", "linux-aarch64", "no-shared", "no-tests",
        "--cross-compile-prefix=aarch64-linux-gnu-", f"--prefix={prefix}", "--libdir=lib"], cwd=source)
    command("openssl-build", ["make", "-j2"], cwd=source)
    command("openssl-install", ["make", "install_sw"], cwd=source)
    save(deps / "dependencies.json", {"schema": "codex.gnu-engine-dependencies.v1", "target": TARGET,
        "openssl": {"version": builder.OPENSSL_VERSION, "source": {"url": builder.OPENSSL_SOURCE_URL,
            "sha256": digest(archive), "archive": str(archive)}, "configureTarget": "linux-aarch64",
            "compilerTarget": "aarch64-linux-gnu", "archives": {name: digest(prefix / "lib" / name)
                for name in builder.OPENSSL_ARCHIVES}}})
    output = command("engine-prepare", [sys.executable, "-B", ROOT / "tools/executor/build-gnu-engine.py", "prepare",
        "--engine", WORK / "engine", "--recovery-manifest", selected, "--build-root", WORK / "engine-builds",
        "--target-dir", WORK / "engine-target", "--dependencies", deps, "--dependency-manifest", deps / "dependencies.json",
        "--cargo-home", os.environ["CARGO_HOME"], "--rustup-home", os.environ["RUSTUP_HOME"]], env=env)
    build_state = Path(output.splitlines()[-1])
    command("engine-build", [sys.executable, "-B", ROOT / "tools/executor/build-gnu-engine.py", "build",
        "--state", build_state, "--jobs", "2"], env=env)
    built = json.loads(build_state.read_text())
    value = state()
    libraries = WORK / "gnu-libraries"
    command("gnu-libraries", [sys.executable, "-B", ROOT / "tools/executor/collect-gnu-rootfs-libraries.py",
        "--rootfs-archive", value["baseArchive"], "--rootfs-sha256", value["baseSha256"],
        "--binaries", Path(built["build"]) / "unstripped", "--output", libraries])
    command("engine-package", [sys.executable, "-B", ROOT / "tools/executor/build-gnu-engine.py", "package",
        "--state", build_state, "--libraries", libraries], env=env)
    command("engine-assets", [sys.executable, "-B", ROOT / "tools/executor/stage-gnu-engine-assets.py",
        "--state", build_state, "--output", WORK / "gnu-assets"])
    version = run(["qemu-aarch64", "-L", Path(value["baseBuildDirectory"]) / "rootfs",
                   Path(built["build"]) / "package/codex", "--version"], env=env)
    if value["engine"]["tag"].removeprefix("rust-v") not in version:
        raise ValueError("Built backend reports a different version")
    value["engineBuildState"] = str(build_state)
    value["engineVersionOutput"] = version
    value["rustCompiler"] = run(["rustc", "-vV"], env=env)
    save(WORK / "plan.json", value)


def image():
    value = state()
    command("phone-image", ["sudo", sys.executable, "-B", ROOT / "tools/install/build-phone-image.py",
        "--base", value["baseArchive"], "--base-sha256", value["baseSha256"], "--gpu", value["gpuArchive"],
        "--gpu-sha256", value["gpuSha256"], "--engine-state", value["engineBuildState"],
        "--official-input", WORK / "official-client", "--client-version", value["desktopVersion"],
        "--output", WORK / "phone-image", "--embed-archive"])
    command("image-owner", ["sudo", "chown", "-R", f"{os.getuid()}:{os.getgid()}", WORK / "phone-image"])


def acquire_native_baseline():
    value = state()
    baseline = value["nativeBaseline"]
    apk = WORK / "native-baseline.apk"
    if apk.exists():
        if digest(apk) != baseline["sha256"]:
            raise ValueError("Previously downloaded native baseline SHA-256 differs")
    else:
        fetch(baseline["url"], apk, expected=baseline["sha256"])
    print("Native baseline download verified", flush=True)
    return apk


def recover_native():
    baseline = state()["nativeBaseline"]
    apk = acquire_native_baseline()
    sdk = Path(os.environ["ANDROID_HOME"])
    command("recover-native", [sys.executable, "-B", ROOT / "tools/workstation/recover-apk-inputs.py",
        "--apk", apk, "--apk-sha256", baseline["sha256"], "--cert-sha256", baseline["certificateSha256"],
        "--java", Path(os.environ["JAVA_HOME"]) / "bin/java", "--apksigner-jar", sdk / "build-tools/36.0.0/lib/apksigner.jar",
        "--output", WORK / "native"])
    # The new image owns these descriptors. Do not merge a baseline's old image
    # metadata over the selected desktop/backend or package its old fingerprint.
    old = WORK / "native/debug-assets/phone-runtime"
    if old.is_dir() and not old.is_symlink():
        shutil.rmtree(old)


def apk():
    value = state()
    native = WORK / "native"
    builder = ROOT / "tools/runtime/build-production-candidate.py"
    inputs = WORK / "apk-inputs.json"
    sdk = Path(os.environ["ANDROID_HOME"])
    platform = "android-37" if (sdk / "platforms/android-37").exists() else "android-37.0"
    command("apk-inputs", [sys.executable, "-B", builder, "record-inputs", "--package", native / "executor",
        "--runtime-jni", native / "runtime", "--x11-jni", native / "x11", "--transport-jni", native / "transport",
        "--debug-jni", native / "debug-jni", "--debug-assets", native / "debug-assets", "--sdk", sdk,
        "--jdk", os.environ["JAVA_HOME"], "--gradle", shutil.which("gradle"), "--build-tools", "36.0.0",
        "--sdk-platform", platform, "--output", inputs])
    # Only this signing stage sees the encrypted repository secret. Do not use
    # set -x, put passwords in argv, or include the key in any upload directory.
    encoded = os.environ.get("CODEX_KEYSTORE_BASE64", "")
    if not encoded:
        raise ValueError("Configure the CODEX_KEYSTORE_BASE64 repository secret before running a release")
    key = Path(os.environ.get("RUNNER_TEMP", WORK / "private")) / "codex-release.keystore"
    key.parent.mkdir(parents=True, exist_ok=True)
    with key.open("xb") as stream:
        os.chmod(key, 0o600)
        stream.write(base64.b64decode(encoded, validate=True))
    env = dict(os.environ, CODEX_BASELINE_APK=str(WORK / "native-baseline.apk"),
        CODEX_BASELINE_APK_SHA256=value["nativeBaseline"]["sha256"])
    try:
        command("apk-build", [sys.executable, "-B", builder, "build", "--inputs", inputs,
            "--inputs-sha256", digest(inputs), "--candidate", "ci" + str(value["versionCode"]),
            "--output", WORK / "candidate", "--native-update", "--gnu-engine-assets", WORK / "gnu-assets",
            "--engine-manifest", WORK / "engine-selection/manifest.json", "--phone-image-assets", WORK / "phone-image/assets",
            "--signing-keystore", key, "--signing-cert-sha256", value["nativeBaseline"]["certificateSha256"],
            "--reuse-native-apk", WORK / "native-baseline.apk", "--reuse-native-apk-sha256", value["nativeBaseline"]["sha256"],
            "--version-code", str(value["versionCode"]), "--version-name", value["versionName"],
            "--gradle-init-script", ROOT / "tools/ci/reuse-native-baseline.gradle"], env=env)
    finally:
        key.unlink(missing_ok=True)
    report = json.loads((WORK / "candidate/build-report.json").read_text())
    artifact = Path(report["apk"])
    if not report["success"] or artifact.stat().st_size >= 2 * 1024**3:
        raise ValueError("Full APK failed verification or exceeds the Release size limit")
    release = WORK / "release"
    release.mkdir()
    destination = release / f"Codex-Android-{value['releaseTag']}-full.apk"
    shutil.copyfile(artifact, destination)
    value.update(apk=destination.name, apkSha256=digest(destination), apkBytes=destination.stat().st_size,
        firstInstallTested=False,
        description=(ROOT / "config/android/release-notes.txt").read_text(encoding="utf-8").strip())
    save(release / "build-info.json", value)
    (release / "SHA256SUMS").write_text(value["apkSha256"] + "  " + destination.name + "\n")
    print(json.dumps({"apk": destination.name, "sha256": value["apkSha256"], "bytes": value["apkBytes"]}))


def publish():
    value = json.loads((WORK / "release/build-info.json").read_text())
    env = os.environ
    if env.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        raise RuntimeError("Releases can only be published from an explicitly dispatched workflow")
    repository = env["GITHUB_REPOSITORY"]
    tag = value["releaseTag"]
    # Refuse an existing release/tag instead of replacing an APK in place.
    for endpoint in (f"repos/{repository}/releases/tags/{tag}", f"repos/{repository}/git/ref/tags/{tag}"):
        probe = subprocess.run(["gh", "api", endpoint], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if probe.returncode == 0:
            raise FileExistsError("Release/tag already exists; select a new tag")
    files = [WORK / "release" / name for name in (value["apk"], "build-info.json", "SHA256SUMS")]
    # Let gh upload against the ID returned during draft creation. The REST
    # by-tag endpoint retrieves published releases and may not find a draft.
    command("release-create", ["gh", "release", "create", tag, *files, "--repo", repository,
        "--target", value["sourceCommit"], "--title", "Codex Android " + tag,
        "--notes-file", ROOT / "config/android/release-notes.txt", "--draft"])
    releases = json.loads(run(["gh", "api", f"repos/{repository}/releases?per_page=100"]))
    matches = [item for item in releases if item["tag_name"] == tag and item["draft"]]
    if len(matches) != 1:
        raise ValueError("Could not identify the new draft; refusing publication")
    metadata = matches[0]
    assets = {item["name"]: item for item in metadata["assets"]}
    apk_asset = assets.get(value["apk"], {})
    if (apk_asset.get("size") != value["apkBytes"]
            or apk_asset.get("digest") != "sha256:" + value["apkSha256"]):
        raise ValueError("Uploaded APK digest/size differs; release remains draft")
    publication = WORK / "publish-release.json"
    save(publication, {"draft": False, "body": value["description"]})
    result = json.loads(command("release-publish", ["gh", "api", "--method", "PATCH",
        f"repos/{repository}/releases/{metadata['id']}", "--input", publication]))
    if result["draft"] or (result["body"] or "").strip() != value["description"]:
        raise ValueError("Published Release description/state differs")
    print(result["html_url"])
    if env.get("GITHUB_STEP_SUMMARY"):
        with Path(env["GITHUB_STEP_SUMMARY"]).open("a") as stream:
            stream.write(f"[Download {tag}]({result['html_url']})\n\n"
                f"Desktop: {value['desktopVersion']}; backend: {value['engine']['tag']}.\n\n"
                "Native libraries reused from the verified baseline; fresh-device installation still requires validation.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("plan", "client", "baseline", "base", "gpu", "engine", "image", "native", "apk", "publish"))
    stage = parser.parse_args().stage
    {"plan": plan, "client": acquire_client, "baseline": acquire_native_baseline, "base": base, "gpu": gpu, "engine": engine,
     "image": image, "native": recover_native, "apk": apk, "publish": publish}[stage]()
