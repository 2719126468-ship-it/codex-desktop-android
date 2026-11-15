package com.ai.codex;

import org.junit.Test;
import static org.junit.Assert.*;

public class LiveNotificationTextTest {
    @Test public void workStatusIsReadableWithoutWaitingForAScroll() {
        assertEquals("Codex", LiveNotificationText.chip("Codex", 100));
        for (int frame = 0; frame < 30; frame++) {
            assertEquals("执行命令", LiveNotificationText.chip("正在执行命令 · 一个很长的任务标题", frame));
            assertEquals("看屏幕", LiveNotificationText.chip("Codex 正在看屏幕\n当前应用：微信", frame));
        }
    }
    @Test public void specificActionsBeatGenericBrandPrefixes() {
        assertEquals("点发送", LiveNotificationText.chip("点「发送」", 0));
        assertEquals("长按消息", LiveNotificationText.chip("长按「消息」", 0));
        assertEquals("正在输入", LiveNotificationText.chip("输入「一段很长的文本」", 0));
        assertEquals("正在滑动", LiveNotificationText.chip("滚动", 0));
        assertEquals("等待确认", LiveNotificationText.chip("等待确认\n当前动作：点「发送」", 0));
        assertEquals("已暂停", LiveNotificationText.chip("操控已暂停", 0));
    }
    @Test public void longTargetsAlternateActionAndTargetWithoutMidWordWindows() {
        assertEquals("正在点击", LiveNotificationText.chip("点「一个很长的按钮名称」", 0));
        assertEquals("一个很长…", LiveNotificationText.chip("点「一个很长的按钮名称」", 1));
    }
    @Test public void neverSplitsEmojiAndRemovesControlCharacters() {
        String text = "🛠️正在执行命令";
        for (int frame = 0; frame < 30; frame++) {
            String chip = LiveNotificationText.chip(text, frame);
            assertTrue(chip.codePointCount(0, chip.length()) <= 5);
            for (int i = 0; i < chip.length(); i++) {
                if (Character.isHighSurrogate(chip.charAt(i))) assertTrue(i + 1 < chip.length() && Character.isLowSurrogate(chip.charAt(++i)));
                else assertFalse(Character.isLowSurrogate(chip.charAt(i)));
            }
        }
        assertEquals("a b", LiveNotificationText.chip("a\tb", 0));
    }
}
