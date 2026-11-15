package com.ai.codex;

import com.termux.x11.DisplayRefreshRate;
import org.junit.Test;
import static org.junit.Assert.*;

public class DisplayRefreshRateTest {
    @Test public void requestsFastestModeWithoutSwitchingToALowerResolution() {
        assertEquals(2, DisplayRefreshRate.fastestAtSize(1440, 3168,
            new int[]{1440,1080,1440,1440}, new int[]{3168,2376,3168,3168}, new float[]{60,240,120,90}));
        assertEquals(1, DisplayRefreshRate.fastestAtSize(1080, 2376,
            new int[]{1440,1080}, new int[]{3168,2376}, new float[]{120,90}));
    }
    @Test public void invalidOrMissingModesCannotCreateARefreshPreference() {
        assertEquals(-1, DisplayRefreshRate.fastestAtSize(1440,3168, new int[]{1080}, new int[]{2376}, new float[]{120}));
        assertEquals(-1, DisplayRefreshRate.fastestAtSize(1440,3168, new int[]{1440}, new int[]{3168}, new float[]{Float.NaN}));
    }
    @Test public void compatibilityOverrideDoesNotCapPhysicalHighRefresh() {
        assertEquals(120f, DisplayRefreshRate.current(120f, 60f), 0f);
        assertEquals(90f, DisplayRefreshRate.current(90f, 60f), 0f);
        assertEquals(165f, DisplayRefreshRate.current(165f, 60f), 0f);
    }
    @Test public void tracksBothUpwardAndDownwardDisplayChanges() {
        for (float rate : new float[] {60, 90, 120, 144, 90, 60, 30})
            assertEquals(rate, DisplayRefreshRate.current(rate, 60), 0f);
    }
    @Test public void invalidModeFallsBackToTheAppDisplayRate() {
        assertEquals(120f, DisplayRefreshRate.current(Float.NaN, 120), 0f);
        assertEquals(90f, DisplayRefreshRate.current(0, 90), 0f);
        assertEquals(0f, DisplayRefreshRate.current(Float.POSITIVE_INFINITY, -1), 0f);
    }
    @Test public void onlyTheNativeIntegerProtocolRoundsFractionalHz() {
        assertEquals(59.94f, DisplayRefreshRate.current(59.94f, 30), 0f);
        assertEquals(60, DisplayRefreshRate.x11(59.94f));
        assertEquals(120, DisplayRefreshRate.x11(119.88f));
        assertEquals(240, DisplayRefreshRate.x11(240f));
    }
    @Test public void missingDisplayDoesNotCreateAFixedSixtyHzVote() {
        assertEquals(0, DisplayRefreshRate.x11(0));
        assertEquals(0, DisplayRefreshRate.x11(Float.NaN));
        assertEquals(0, DisplayRefreshRate.x11(-60));
    }
}
