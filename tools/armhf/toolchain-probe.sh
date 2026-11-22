#!/usr/bin/env bash
set -euo pipefail

command -v arm-linux-gnueabihf-gcc >/dev/null
command -v arm-linux-gnueabihf-readelf >/dev/null
command -v rustc >/dev/null
rustc --print target-list | grep -Fx 'armv7-unknown-linux-gnueabihf' >/dev/null

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

cat >"$work/probe.c" <<'EOF'
#include <stdio.h>
int main(void) {
    puts("armhf-c-toolchain-ok");
    return 0;
}
EOF

arm-linux-gnueabihf-gcc \
    -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -O2 -Wall -Wextra -Werror -fstack-protector-strong \
    "$work/probe.c" -o "$work/probe-c"

cat >"$work/main.rs" <<'EOF'
fn main() {
    println!("armhf-rust-toolchain-ok");
}
EOF

rustc --edition=2021 --target armv7-unknown-linux-gnueabihf \
    -C linker=arm-linux-gnueabihf-gcc \
    -C link-arg=-Wl,-z,relro,-z,now \
    "$work/main.rs" -o "$work/probe-rust"

verify_armhf() {
    local binary="$1"
    local header attributes
    header="$(arm-linux-gnueabihf-readelf -h "$binary")"
    attributes="$(arm-linux-gnueabihf-readelf -A "$binary")"
    grep -Eq 'Class:[[:space:]]+ELF32' <<<"$header"
    grep -Eq 'Data:[[:space:]]+2.s complement, little endian' <<<"$header"
    grep -Eq 'Machine:[[:space:]]+ARM' <<<"$header"
    grep -q 'Tag_ABI_VFP_args: VFP registers' <<<"$attributes"
    arm-linux-gnueabihf-readelf -l "$binary" | grep -q 'Requesting program interpreter: /lib/ld-linux-armhf.so.3'
    printf '\nVerified ARMhf ELF: %s\n' "$binary"
    arm-linux-gnueabihf-readelf -h "$binary" | grep -E 'Class:|Data:|Machine:'
    arm-linux-gnueabihf-readelf -A "$binary" | grep 'Tag_ABI_VFP_args'
}

verify_armhf "$work/probe-c"
verify_armhf "$work/probe-rust"

printf '\nToolchain probe passed. This validates only the Debian ARMhf C/Rust cross-toolchain; it does not build V8, Codex, Android JNI, or an APK.\n'
