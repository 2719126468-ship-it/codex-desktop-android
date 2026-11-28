package com.ai.codex.install;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.util.List;
import org.junit.Test;

/** Full builds stage the archive as an opaque .rootfs entry; v80 shipped it as .tgz. */
public final class PhoneRuntimeInstallerTest {
    @Test public void recognizesEveryPublishedBundledRootfsName() {
        assertTrue(PhoneRuntimeInstaller.hasBundledArchive(List.of(
            "release.json", "inventory.json", "codex-phone-rootfs.tgz")));
        assertTrue(PhoneRuntimeInstaller.hasBundledArchive(List.of(
            "release.json", "inventory.json", "codex-phone-rootfs.rootfs")));
        assertFalse(PhoneRuntimeInstaller.hasBundledArchive(List.of(
            "release.json", "inventory.json", "codex-phone-rootfs.tar.gz")));
        assertFalse(PhoneRuntimeInstaller.hasBundledArchive(List.of("release.json", "inventory.json")));
        assertFalse(PhoneRuntimeInstaller.hasBundledArchive(null));
    }
}