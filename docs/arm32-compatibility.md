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

## Pinned Codex V8 source-build boundary (2026-11-22)

A second pass inspected the actual V8 source-build selectors at the pinned
Codex revision `ccf9be8cc458bd6b8336fe84d68d8893f2691a5e`, rather than only
checking the published release list:

- `third_party/v8/BUILD.bazel` maps Linux prebuilt archives and bindings
  only for x86_64 and AArch64 GNU/musl. Its source-archive and source-binding
  selectors likewise define Linux x86_64 and AArch64 targets; the default
  fallback is x86_64, not ARMv7.
- `third_party/v8/artifact_profile.bzl` defines CPU constraints only for
  `arm64` and `x64`; its profile values also accept only those two names.
  Its current platform check treats every non-`arm64` value as x64, so an
  ARMv7 extension must add an explicit ARM constraint/check rather than
  relying on the existing fallback. This is an explicit source-build
  configuration boundary, not merely a missing prebuilt download.
- `third_party/v8/README.md` documents the same Linux release/source pair
  targets for x86_64 and AArch64 only.
- This repository's `tools/executor/build-gnu-engine.py` also pins
  `TARGET = "aarch64-unknown-linux-gnu"` and configures the AArch64 linker,
  OpenSSL target, and V8 archive/binding inputs throughout the build.

Therefore a Rust target install or a Cargo target override cannot produce a
working ARMhf engine by itself. A real port must first add and qualify an
ARMv7 V8 CPU profile, Bazel platform/toolchain, generated V8 archive and
matching Rust bindings, then audit and build the full Codex dependency graph
and both shipped executables. No such ARMv7 V8 profile or artifact pair is
present in the pinned source. This is now the primary engine feasibility
blocker; do not create a nominal ARMv7 CI lane that merely compiles a small
Rust crate or skips the V8-backed engine.

Pinned source references:

- [V8 BUILD.bazel](https://github.com/openai/codex/blob/ccf9be8cc458bd6b8336fe84d68d8893f2691a5e/third_party/v8/BUILD.bazel)
- [V8 artifact_profile.bzl](https://github.com/openai/codex/blob/ccf9be8cc458bd6b8336fe84d68d8893f2691a5e/third_party/v8/artifact_profile.bzl)
- [V8 README](https://github.com/openai/codex/blob/ccf9be8cc458bd6b8336fe84d68d8893f2691a5e/third_party/v8/README.md)
- [This repository's GNU engine builder](https://github.com/2719126468-ship-it/codex-desktop-android/blob/main/tools/executor/build-gnu-engine.py)

## Exact V8 Bazel graph audit (2026-11-22, pinned Codex revision)

A direct read of the pinned source files confirms that the ARMv7 blocker is
implemented in the build graph, not just in release asset naming:

- `third_party/v8/artifact_profile.bzl` defines
  `_CPU_CONSTRAINTS` with only `arm64` and `x64`. The
  `_v8_artifact_files` rule also restricts `v8_cpu` to those two values.
  Its platform check selects ARM64 for `arm64` and x64 otherwise; adding
  `armv7` without changing this rule would incorrectly route the check to
  x86_64 rather than validate an ARMv7 constraint.
- `third_party/v8/BUILD.bazel` has no ARMv7 branch in the prebuilt archive,
  source archive, prebuilt binding, or source binding selectors. The Linux
  GNU/musl archive generation list contains only `aarch64` and `x86_64`.
  The source-binding target list likewise declares only those two Linux CPUs.
- The source-build target table maps only x86_64 and AArch64 to V8 CPU
  profiles. The generated binding targets and release-pair targets are
  declared for those same architectures; the default selector falls back to
  x86_64, which must never be mistaken for an ARMv7 build.
- `third_party/v8/README.md` documents release-pair publishing for the
  x86_64 and AArch64 Linux GNU/musl targets only.

### Required V8 port sequence (do not skip gates)

1. Add an explicit Bazel ARMv7 CPU constraint and platform/toolchain mapping;
   make the artifact-profile rule reject unknown CPUs rather than treating
   every non-ARM64 value as x64.
2. Define the exact ARMv7 Linux GNU ABI (including hard-float ABI and minimum
   CPU/FPU assumptions) and verify it agrees across Bazel, Clang, Rust,
   Debian armhf, and the Android PRoot guest.
3. Build the V8 archive from the pinned V8 source with a dedicated ARMv7
   profile and produce the matching generated Rust bindings from the same
   headers, defines, and ABI settings. Archive and binding must be a single
   versioned pair with reproducible hashes.
4. Build and run V8's own tests and Codex's V8 integration/runtime tests on
   ARMv7 hardware or a qualified emulator. Cross-compilation success alone
   is insufficient.
5. Only then wire the pair into Codex's Cargo/Bazel selectors and build both
   shipped GNU executables. Audit all transitive native dependencies and
   runtime loading on a real ARMv7 Android 8.1 device.

This is a feasibility/implementation boundary, not a claim that V8 itself
cannot support 32-bit ARM. The pinned Codex integration currently lacks the
CPU profile, target platform, archive, binding, and release-pair graph needed
to build it. The next implementation should be a separate, tightly scoped
V8 ARMv7 source-build spike; do not change the Android ABI filter or mark
the product lane green before that spike produces and tests a real archive
and matching bindings.

Pinned source files:
- [artifact_profile.bzl](https://github.com/openai/codex/blob/ccf9be8cc458bd6b8336fe84d68d8893f2691a5e/third_party/v8/artifact_profile.bzl)
- [BUILD.bazel](https://github.com/openai/codex/blob/ccf9be8cc458bd6b8336fe84d68d8893f2691a5e/third_party/v8/BUILD.bazel)
- [README.md](https://github.com/openai/codex/blob/ccf9be8cc458bd6b8336fe84d68d8893f2691a5e/third_party/v8/README.md)


## Clarification from the V8 engine-policy audit (2026-11-22)

The V8 engine itself already contains a 32-bit ARM compilation branch in
Codex's pinned source. In
`third_party/v8/engine.BUILD.bazel`, the `v8_target_arm` selection emits
`V8_TARGET_ARCH_ARM`, `CAN_USE_ARMV7_INSTRUCTIONS`, and
`CAN_USE_VFP3_INSTRUCTIONS`. Therefore the blocker is **not** that V8 has
no ARM32 code-generation configuration.

The missing piece is Codex's consumer artifact integration:

- `artifact_profile.bzl` accepts only `arm64` and `x64` profile values
  and declares only AArch64/x86_64 platform constraints. Its current
  non-ARM64 branch checks x86_64, so simply adding an `armv7` string would
  be incorrect; the rule must explicitly validate ARMv7.
- `third_party/v8/BUILD.bazel` has no ARMv7 Linux archive or generated
  binding selector, and its bindgen target flags do not declare an ARMv7
  Linux triple.
- The existing Codex V8 source profile, archive and Rust binding therefore
  cannot currently be selected as a consistent ARMv7 artifact pair.

There are two distinct ABIs in this project and they must not be conflated:

1. Android host JNI/runtime libraries use the NDK's
   `armeabi-v7a` / Android API 27 ABI.
2. The Debian PRoot guest and its GNU Codex engine need a Linux ARM
   hard-float userspace ABI, expected to be
   `armv7-unknown-linux-gnueabihf` if the selected Debian armhf toolchain
   and V8 build are proven compatible.

An Android NDK `armeabi-v7a` shared object cannot be substituted for a
glibc-based Debian armhf executable or library, and a GNU armhf V8 archive
cannot be loaded directly into the Android Bionic host process. Each side
needs its own toolchain, dependencies, manifest, and runtime tests.

This clarification narrows the V8 task: first prove a reproducible
ARMv7 hard-float V8 archive plus bindings from the pinned source, then
integrate that pair into the GNU guest engine. It does not remove the
separate Android JNI/runtime port or the missing ARMhf desktop-client
distribution blocker. No ARMv7 binary has been built or tested as part of
this source audit.



## GNU engine package-selector audit (2026-11-22)

The pinned Codex package layer adds another required integration boundary
after the V8 Bazel graph:

- `scripts/codex_package/targets.py` has explicit `TargetSpec` entries for
  x86_64 and AArch64 Linux GNU/musl, but no
  `armv7-unknown-linux-gnueabihf` entry. Its host normalization also maps
  only amd64/x86_64 and aarch64/arm64; ARMv7 must be explicit rather than
  inferred from a generic 32-bit host name.
- `scripts/codex_package/v8.py` does not build V8. It downloads the Codex
  release pair named from `TargetSpec.target`:
  `librusty_v8_<profile>_<target>.a.gz` and
  `src_binding_<profile>_<target>.rs`, then verifies both against the
  pinned release checksum manifest. Adding a target-table row alone would
  therefore request assets that do not exist; it cannot generate the
  ARMv7 pair.
- This repository's `tools/executor/build-gnu-engine.py` imports
  `fetch_codex_v8_artifacts` and freezes the returned archive and binding
  hashes into build evidence. The current build flow is a consumer of
  published V8 release pairs, not a V8 source-archive producer.

The implementation must consequently introduce a distinct, reproducible
ARMv7 V8 producer stage before enabling the ARMhf package target. That stage
must emit the archive and binding together, record their source revision,
toolchain/profile inputs and SHA-256 values, and test the pair by linking and
running a minimal Rusty_V8 consumer under ARMv7. The GNU engine builder can
then consume that locally qualified pair through its existing paired
`RUSTY_V8_ARCHIVE` / `RUSTY_V8_SRC_BINDING_PATH` override, but only after
the pair's provenance is verified and the target-specific linker/OpenSSL
configuration is implemented. It must not silently fall back to the
published x86_64 or AArch64 artifacts.

### Current implementation status

| Layer | Pinned-source status |
| --- | --- |
| V8 ARM code-generation branch | Present (`v8_target_arm`) |
| Codex V8 artifact CPU profile | Missing ARMv7 |
| V8 Linux ARMhf archive selector | Missing |
| V8 Linux ARMhf bindgen target | Missing |
| Codex package `TargetSpec` | Missing ARMhf |
| V8 source-pair producer in this repo | Missing |
| GNU engine ARMhf linker/OpenSSL profile | Missing |
| ARMhf Codex executables | Not built |

This is why the successful C/Rust toolchain probe is a useful prerequisite,
not a green engine build. The next code change should be isolated to a
reproducible V8 ARMv7 producer and its source-graph selectors; do not enable
the package target or change the Android APK ABI filters until that stage
has a passing Rusty_V8 consumer test.
