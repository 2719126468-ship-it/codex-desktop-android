# 32-bit ARMv7 / Android 8.1 compatibility

## Status

**Blocked — no functional 32-bit APK or Codex workspace is available yet.**

The ARM64 Android 8.1 baseline was merged into `main` in PR #1. This PR
tracks the separate `armeabi-v7a` implementation and its acceptance gates;
it does not claim that a 32-bit build is already functional.

The pinned v80 release inputs currently used by this repository do not
contain the 32-bit desktop client, GNU engine, or complete Android native
runtime needed for a working ARMv7 device.

## What the repository currently proves

- `android/app/build.gradle:14` explicitly filters the Android host to
  `arm64-v8a`. The same file validates the GNU engine as
  `aarch64-unknown-linux-gnu` (line 53), the desktop client as `arm64`
  (line 76), and executor JNI under the `arm64-v8a` directory (lines
  157–160).
- `tools/install/native/build-native.sh` creates only
  `runtime/arm64-v8a` (line 21), invokes
  `aarch64-linux-android27-clang` (lines 63–65), and places the PRoot
  executable and both loaders in that ARM64 directory (lines 93–99).
  In particular, `libproot-loader32.so` is a 32-bit *guest ELF loader*
  carried inside the ARM64 runtime. It is not an ARM32 Android JNI library.
- `tools/install/build_rootfs.py` declares `ARCH = "arm64"` (line 25)
  and builds/publishes an ARM64 Debian rootfs (lines 250–259 and 313–344).
- `tools/install/official_client_package.py` pins the
  `chatgpt_arm64.deb` acquisition URL (line 24), rejects any package whose
  architecture is not `arm64` (line 52), and validates ARM64 core ELF
  executables (lines 266 and 316).
- The existing API 27 GitHub Actions workflow builds an ARM64 APK only.
  Its successful result is a regression check for the 64-bit baseline, not
  evidence of ARMv7 compatibility.

These are independent architecture locks across Android packaging, native
runtime, guest rootfs, and desktop client acquisition. Changing only Gradle's
`abiFilters` or adding `armeabi-v7a` to the APK would produce a misleading,
incomplete package and is not an acceptable fix.

## Required implementation work

### 1. Android host ABI

- Add an explicit `armeabi-v7a` product/build lane, independent of ARM64.
- Build all app-owned JNI and CMake targets with the NDK ARMv7 Android
  toolchain and API 27 minimum.
- Audit every third-party AAR/JNI dependency and Shizuku transport for
  actual `armeabi-v7a` support.
- Verify the final APK contains the complete required ARMv7 native set and
  no accidental ARM64-only libraries.

### 2. Native Android runtime

- Cross-build PRoot, matching loaders, talloc, android-shmem, X11, and
  executor/transport libraries for Android ARMv7.
- Validate ELF class 32, machine `EM_ARM`, EABI attributes, interpreter,
  dynamic dependencies, stack protections, and load alignment supported by
  the target toolchain and Android devices.
- Keep source pins, build commands, licenses, hashes, and manifests separate
  for each architecture. Never reuse ARM64 checksums or descriptors.

### 3. Linux desktop UI runtime and client

- Supply a Linux ARMhf desktop UI runtime, including a compatible
  Electron/Chromium build, shared libraries, and all native Node/Electron
  modules.
- Port and package the graphical Codex desktop client for ARMhf. Validate
  its complete process tree and native modules, not just the launcher ELF.
- Keep ARM64 desktop payloads isolated and selectable only on ARM64.

**Time-limited Electron path:** Electron 43.x is the final release line with
prebuilt Linux `armv7l` binaries. Electron 44 and newer publish only 64-bit
platform binaries; Electron 43 is scheduled to reach end of life in January
2027. A short-term ARMhf experiment could pin Electron 43 or an older
compatible release, but that creates a near-term security and maintenance
burden and must be validated against this desktop client's exact Electron
and native-module requirements. It is not a durable upstream-supported path.
Sources: [Electron 44 breaking changes](https://www.electronjs.org/docs/latest/breaking-changes/),
[Electron 43 release notice](https://releases.electronjs.org/release/v43.0.0).

**Separate Codex engine blocker:** the official Codex CLI installer currently
selects Linux x64 or ARM64 binaries only. Codex CLI is not a drop-in
replacement for this repository's graphical desktop client, and it does not
supply the ARMhf GNU engine payload required by this Android project.
Source: [official Codex installer](https://github.com/openai/codex/blob/main/scripts/install/install.sh).

### 4. Linux guest and Codex engine

- Supply an ARM hard-float (`armhf`) Debian rootfs and matching package set.
- Obtain or build both GNU engine executables (`codex-native` and
  `codex-code-mode-host`) for `armv7-unknown-linux-gnueabihf` or the exact
  supported ARM hard-float target.
- Rebuild and qualify the native executor for ARM32; verify every executable
  and shared object against its own manifest before installation.
- Keep the ARM64 engine payload unchanged and selectable only on ARM64.

**Blocking dependency:** the pinned v80 release provides an ARM64-only
desktop client and AArch64 GNU engine. Until compatible, redistributable
ARMhf desktop and engine payloads exist and their provenance is verified,
a complete 32-bit Codex workspace cannot be released. An app shell or
installer alone is not a valid substitute.

### 5. CI and device acceptance

- Add an independent API 27 `armeabi-v7a` CI job that builds from pinned
  sources and validates the final APK ABI and every native ELF.
- Keep the ARMv7 lane explicitly blocked/red while required ARM32 payloads
  are unavailable. Do not count the existing ARM64 CI job as ARM32 coverage.
- Test clean install, launch, PRoot startup, guest command execution,
  filesystem operations, process cancellation, Shizuku transport, and
  Codex engine startup on a real 32-bit Android 8.1 device.

## Release acceptance criteria

A 32-bit compatibility release is complete only when all layers are
available and verified: Android ARMv7 app/JNI, Android ARMv7 native runtime,
Linux ARMhf guest, working ARMhf desktop UI runtime/client, ARMhf Codex
engine/native executor, independent CI, and real-device API 27 acceptance.

Until then, advertise ARMv7 as **blocked / not supported**. The successful
ARM64 API 27 build is not evidence of 32-bit compatibility.
