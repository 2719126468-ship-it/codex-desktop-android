package com.ai.codex.phone

import org.junit.Assert.*
import org.junit.Test

class PhoneLiveTextTest {
    @Test fun usesTheOverlayActionAndDropsBothLocalizedPrefixes() {
        assertEquals("点「发送」", PhoneLiveText.action("免确认 · Codex 正在操作 · 点「发送」", "免确认 · %1\$s", "Codex 正在操作 · %1\$s"))
        assertEquals("Tap Send", PhoneLiveText.action("No approval · Codex is acting · Tap Send", "No approval · %1\$s", "Codex is acting · %1\$s"))
    }
    @Test fun promptsWinOverPauseAndDetailsRetainTheCurrentAction() {
        val text = PhoneLiveText.detail("点「发送」", "微信", true, PromptKind.NATIVE_CONFIRM, listOf("输入「你好」"))
        assertTrue(text.startsWith("等待确认\n"))
        assertTrue(text.contains("当前动作：点「发送」"))
        assertTrue(text.contains("当前应用：微信"))
        assertTrue(text.contains("最近操作：输入「你好」"))
        assertTrue(PhoneLiveText.detail("看屏幕", null, true, PromptKind.HANDOFF, emptyList()).startsWith("等待接管"))
    }
    @Test fun recentActionsSurviveReadScreenUpdatesAndDoNotCrossTasks() {
        val h = PhoneLiveHistory()
        h.record(1, "点「搜索」")
        h.record(1, "Codex 正在看屏幕")
        h.record(1, "输入「你好」")
        h.record(1, "Codex 正在看屏幕")
        assertEquals(listOf("点「搜索」", "输入「你好」"), h.recent())
        h.record(2, "点「返回」")
        assertTrue(h.recent().isEmpty())
    }
    @Test fun historyIsBoundedAndRepeatedUpdatesDoNotCreateSteps() {
        val h = PhoneLiveHistory()
        repeat(10) { h.record(1, "点「$it」"); h.record(1, "点「$it」") }
        assertEquals(listOf("点「6」", "点「7」", "点「8」"), h.recent())
    }
}
