package com.ai.codex;

import android.content.Context;
import android.os.Build;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/** Crash and startup breadcrumbs on external storage.
 *
 * Android 10 on EMUI hides logcat and dumpsys from the shell, so a dead process leaves
 * no evidence at all. This recorder writes each startup stage and any uncaught throwable
 * to a world-readable file under Android/data/<pkg>/files, where a terminal can read it
 * without root. Nothing here touches user data; it records stage names and stack traces.
 */
public final class CodexTrace {
    private static final String FILE = "codex-startup.log";
    private static final Object LOCK = new Object();
    private static File destination;

    private CodexTrace() {}

    /** Binds the record to this process; safe to call repeatedly. */
    public static void bind(Context context) {
        synchronized (LOCK) {
            if (destination != null) return;
            File base = context.getExternalFilesDir(null);
            if (base == null) base = context.getFilesDir();
            try { base.mkdirs(); } catch (SecurityException ignored) { }
            destination = new File(base, FILE);
        }
    }

    public static File file(Context context) {
        bind(context);
        return destination;
    }

    /** Records one breadcrumb. Never throws: diagnostics must not break startup. */
    public static void stage(String name) {
        append("STAGE " + name);
    }

    public static void error(String where, Throwable error) {
        StringWriter buffer = new StringWriter();
        PrintWriter writer = new PrintWriter(buffer);
        error.printStackTrace(writer);
        writer.flush();
        append("ERROR " + where + "\n" + buffer);
    }

    private static void append(String text) {
        synchronized (LOCK) {
            if (destination == null) return;
            String line = timestamp() + " pid=" + android.os.Process.myPid()
                    + " tid=" + android.os.Process.myTid() + " " + text + "\n";
            try (FileOutputStream out = new FileOutputStream(destination, true)) {
                out.write(line.getBytes(StandardCharsets.UTF_8));
                out.flush();
            } catch (IOException | SecurityException ignored) { }
        }
    }

    private static String timestamp() {
        return new SimpleDateFormat("MM-dd HH:mm:ss.SSS", Locale.ROOT).format(new Date());
    }

    /** Device facts worth recording once, so the log is self-contained. */
    public static void environment(String stage) {
        append("ENV " + stage
                + " sdk=" + Build.VERSION.SDK_INT
                + " release=" + Build.VERSION.RELEASE
                + " abi=" + Build.SUPPORTED_ABIS[0]
                + " model=" + Build.MODEL
                + " api_levels=" + Build.VERSION.SDK_INT);
    }
}