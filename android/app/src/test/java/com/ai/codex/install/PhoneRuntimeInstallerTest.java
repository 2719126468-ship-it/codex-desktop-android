package com.ai.codex.install;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.util.List;
import org.junit.Test;

public final class PhoneRuntimeInstallerTest {
    @Test public void recognizesThePublishedBundledRootfsName() {
        assertTrue(PhoneRuntimeInstaller.hasBundledArchive(List.of(
            "release.json", "inventory.json", "codex-phone-rootfs.tar.gz")));
        assertFalse(PhoneRuntimeInstaller.hasBundledArchive(List.of(
            "release.json", "inventory.json", "codex-phone-rootfs.tgz")));
    }
}
