package com.ai.codex;

import android.app.Notification;
import android.app.NotificationManager;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;

/** Requests Android Live Updates, including island presentation on supported ROMs. */
public final class LiveNotifications {
    public static final long SCROLL_MS = 2000;
    public static final int PHONE_ID = 5170;
    public static final String PHONE_CHANGED = "com.ai.codex.PHONE_LIVE_CHANGED";
    private LiveNotifications() { }
    public static Notification.Builder apply(Notification.Builder builder, boolean active, String line, long frame) {
        Bundle extras = new Bundle();
        extras.putBoolean("android.requestPromotedOngoing", active);
        builder.addExtras(extras);
        if (Build.VERSION.SDK_INT >= 36) {
            builder.setShortCriticalText(active ? LiveNotificationText.chip(line, frame) : null);
        }
        if (active) builder.setStyle(new Notification.BigTextStyle().bigText(line));
        if (active) builder.setCategory(Notification.CATEGORY_PROGRESS);
        return builder;
    }
    /** Runtime runs in a separate process; read OS-owned state rather than a static flag. */
    public static boolean phoneIsActive(Context context) {
        try {
            for (android.service.notification.StatusBarNotification posted : context.getSystemService(NotificationManager.class).getActiveNotifications()) {
                if (posted.getId() == PHONE_ID && posted.getTag() == null && posted.getPackageName().equals(context.getPackageName())) {
                    Notification n = posted.getNotification();
                    long timeout = n.getTimeoutAfter();
                    if ((n.flags & Notification.FLAG_ONGOING_EVENT) != 0 &&
                        (timeout <= 0 || System.currentTimeMillis() - posted.getPostTime() < timeout)) return true;
                }
            }
        } catch (RuntimeException ignored) { }
        return false;
    }
    public static void phoneChanged(Context context) {
        context.sendBroadcast(new Intent(PHONE_CHANGED).setPackage(context.getPackageName()));
    }
}
