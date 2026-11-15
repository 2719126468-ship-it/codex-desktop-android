#!/usr/bin/env bash
# Build only the GNU ARM64 controller/Code Mode pair. No APK/ADB operation.
set -euo pipefail
repo=$(realpath "${1:?Pass_the_WSL_checkout_path}")
task_root="$HOME/codex-android"
checkout="$HOME/src/codex-native-0169"
export PATH="$HOME/.cargo/bin:$PATH"
export RUSTUP_TOOLCHAIN=1.99.1
export CARGO_NET_GIT_FETCH_WITH_CLI=true
if [[ -n "${CODEX_BUILD_PROXY:-}" ]]; then
    export CARGO_HTTP_PROXY="$CODEX_BUILD_PROXY"
    export HTTPS_PROXY="$CODEX_BUILD_PROXY" HTTP_PROXY="$CODEX_BUILD_PROXY" ALL_PROXY="$CODEX_BUILD_PROXY"
fi
test -f "$task_root/engine-deps/dependencies.json"
test -d "$task_root/engine-base.git"
mkdir -p "$HOME/src" "$repo/work"
if [[ ! -e "$checkout" ]]; then
    git -C "$task_root/engine-base.git" worktree add --detach "$checkout" d32063f96c2dff1dc96af839b3952abb6acfeda4
fi
if ! git -C "$checkout" apply --reverse --check "$repo/recovery/engine/engine.patch" 2>/dev/null; then
    git -C "$checkout" apply --index --check "$repo/recovery/engine/engine.patch"
    git -C "$checkout" apply --index "$repo/recovery/engine/engine.patch"
fi
state=$(python3 "$repo/tools/executor/build-gnu-engine.py" prepare \
    --verified-checkout --engine "$checkout" \
    --build-root "$task_root/engine-builds" --target-dir "$task_root/engine-target" \
    --dependencies "$task_root/engine-deps" --dependency-manifest "$task_root/engine-deps/dependencies.json" \
    --cargo-home "$HOME/.cargo" --rustup-home "$HOME/.rustup")
printf '%s\n' "$state" > "$repo/work/engine-build-state.txt"
python3 "$repo/tools/executor/build-gnu-engine.py" build --state "$state" --jobs "${CODEX_ENGINE_JOBS:-2}"
printf 'Completed ARM64 backend build. State: %s\n' "$state"
