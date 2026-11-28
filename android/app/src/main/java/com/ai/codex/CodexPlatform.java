package com.ai.codex;

import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Environment;
import android.view.WindowInsets;

/** Platform shims for the API 27 floor. Every helper hides a call that only exists
 * on newer releases so a single APK can run on 8.1, 10 and 14+ without
 * NoSuchMethodError at class-verification time. */
public final class CodexPlatform {
    private CodexPlatform() {}

    public static final String LEGACY_STORAGE = android.Manifest.permission.READ_EXTERNAL_STORAGE;

    /** Public-storage read access: MANAGE_EXTERNAL_STORAGE on R+, legacy grant below. */
    public static boolean allFilesAccess(Context context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            return Environment.isExternalStorageManager();
        }
        return context.checkSelfPermission(LEGACY_STORAGE) == PackageManager.PERMISSION_GRANTED;
    }

    /** Request whatever this platform needs; returns true when the caller must wait. */
    @SuppressWarnings("deprecation")
    public static boolean requestAllFilesAccess(android.app.Activity activity, int requestCode) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) return false;
        if (activity.checkSelfPermission(LEGACY_STORAGE) == PackageManager.PERMISSION_GRANTED) return false;
        activity.requestPermissions(new String[] {LEGACY_STORAGE}, requestCode);
        return true;
    }

    /** WindowInsets.getInsets(Type) is API 30+; below it only the system insets exist. */
    public static int left(WindowInsets insets) {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.R
                ? insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout()).left
                : insets.getSystemWindowInsetLeft();
    }

    public static int top(WindowInsets insets) {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.R
                ? insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout()).top
                : insets.getSystemWindowInsetTop();
    }

    public static int right(WindowInsets insets) {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.R
                ? insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout()).right
                : insets.getSystemWindowInsetRight();
    }

    public static int bottom(WindowInsets insets) {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.R
                ? insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout()).bottom
                : insets.getSystemWindowInsetBottom();
    }

    /** Applies the platform bar insets as padding. */
    public static void padForSystemBars(android.view.View view, WindowInsets insets) {
        view.setPadding(left(insets), top(insets), right(insets), bottom(insets));
    }

    /** IME visibility: WindowInsets.Type.ime() does not exist before R. */
    @SuppressWarnings("deprecation")
    public static boolean imeVisible(WindowInsets insets) {
        if (insets == null) return false;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) return insets.isVisible(WindowInsets.Type.ime());
        return insets.getSystemWindowInsetBottom() > 0;
    }
}