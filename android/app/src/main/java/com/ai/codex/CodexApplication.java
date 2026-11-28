package com.ai.codex;

import android.app.Application;

/** Records every startup stage and any uncaught throwable to external storage.
 * Installed before any activity is created so a crash in onCreate is still captured. */
public final class CodexApplication extends Application {
    @Override public void onCreate() {
        super.onCreate();
        CodexTrace.bind(this);
        CodexTrace.environment("process-start");
        final Thread.UncaughtExceptionHandler previous = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((thread, error) -> {
            CodexTrace.error("uncaught in " + thread.getName(), error);
            if (previous != null) previous.uncaughtException(thread, error);
            else android.os.Process.killProcess(android.os.Process.myPid());
        });
        CodexTrace.stage("application-ready");
    }
}