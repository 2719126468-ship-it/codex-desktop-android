package com.ai.codex;

import org.junit.Test;
import static org.junit.Assert.*;
import static com.ai.codex.EnvironmentLaunchGate.State.*;

public final class EnvironmentLaunchGateTest {
    @Test public void existingEnvironmentNeverRequiresSharedStorageOrArchive() {
        assertEquals(READY, EnvironmentLaunchGate.evaluate(false, false, false));
        assertEquals(READY, EnvironmentLaunchGate.evaluate(false, true, false));
    }

    @Test public void firstInstallDistinguishesPermissionMissingPackageAndReady() {
        assertEquals(ACCESS_REQUIRED, EnvironmentLaunchGate.evaluate(true, false, false));
        assertEquals(ACCESS_REQUIRED, EnvironmentLaunchGate.evaluate(true, false, true));
        assertEquals(PACKAGE_REQUIRED, EnvironmentLaunchGate.evaluate(true, true, false));
        assertEquals(READY, EnvironmentLaunchGate.evaluate(true, true, true));
    }

    @Test public void returningWithoutPermissionDoesNotLoopSettingsPrompt() {
        EnvironmentLaunchGate gate = new EnvironmentLaunchGate();
        assertTrue(gate.shouldPrompt(ACCESS_REQUIRED));
        gate.presented(ACCESS_REQUIRED);
        assertFalse(gate.shouldPrompt(ACCESS_REQUIRED));
        assertTrue(gate.shouldPrompt(PACKAGE_REQUIRED));
        gate.presented(PACKAGE_REQUIRED);
        assertFalse(gate.shouldPrompt(PACKAGE_REQUIRED));
        assertFalse(gate.shouldPrompt(READY));
    }

    @Test public void explicitRetryAllowsAWaitingPromptAgain() {
        EnvironmentLaunchGate gate = new EnvironmentLaunchGate();
        gate.presented(PACKAGE_REQUIRED);
        gate.retry();
        assertTrue(gate.shouldPrompt(PACKAGE_REQUIRED));
        assertFalse(gate.shouldPrompt(READY));
    }
}
