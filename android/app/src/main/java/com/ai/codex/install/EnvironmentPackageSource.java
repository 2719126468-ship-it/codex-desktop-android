package com.ai.codex.install;

import android.content.Context;
import android.os.Build;
import android.os.Environment;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/** Fixed archive transports; release hashes published inside the APK authenticate every byte.
 *
 * Two locations are probed, in order:
 *   1. this app's own external directory (Android/data/<pkg>/files) - readable on every
 *      supported release without any storage permission;
 *   2. the public Download directory - needs MANAGE_EXTERNAL_STORAGE on API 30+ and the
 *      legacy READ_EXTERNAL_STORAGE grant on API 27-29.
 * A full build also embeds the archive inside the APK, in which case neither is used. */
public final class EnvironmentPackageSource {
    public static final String ARCHIVE_NAME = "codex-phone-rootfs.tar.gz";
    private EnvironmentPackageSource() {}

    public static boolean needsInstall(Context context) {
        return !Files.exists(context.getFilesDir().toPath().resolve("debian"), LinkOption.NOFOLLOW_LINKS);
    }

    /** True when public Download is readable; the app-private location needs no grant. */
    public static boolean hasDownloadsAccess(Context context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            return Environment.isExternalStorageManager();
        }
        return context.checkSelfPermission(android.Manifest.permission.READ_EXTERNAL_STORAGE)
                == android.content.pm.PackageManager.PERMISSION_GRANTED;
    }

    /** The runtime permission this platform still needs, or null when none can be requested. */
    public static String requiredPermission() {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.R ? null : android.Manifest.permission.READ_EXTERNAL_STORAGE;
    }

    /** The app-private drop point: no permission, no scoped-storage waiver. */
    public static File privateArchiveFile(Context context) {
        File base = context.getExternalFilesDir(null);
        if (base == null) base = new File(context.getFilesDir(), "external");
        return new File(base, ARCHIVE_NAME);
    }

    public static File archiveFile() {
        return new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), ARCHIVE_NAME);
    }

    /** Every candidate path, most-readable first. */
    public static List<File> candidates(Context context) {
        List<File> paths = new ArrayList<>(2);
        paths.add(privateArchiveFile(context));
        paths.add(archiveFile());
        return paths;
    }

    /** The first candidate that holds an archive of the expected size, or null. */
    public static File presentArchive(Context context, RootfsExtractor.Spec spec) {
        for (File candidate : candidates(context)) {
            Path path = candidate.toPath();
            try {
                if (Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) && Files.size(path) == spec.compressedBytes) {
                    return candidate;
                }
            } catch (IOException unreadable) {
                // A candidate that cannot be stat'ed is simply not a transport.
            }
        }
        return null;
    }

    public static RootfsTransaction.ArchiveSource downloads(Context context, RootfsExtractor.Spec spec) throws IOException {
        Path privatePath = privateArchiveFile(context).toPath();
        if (Files.isRegularFile(privatePath, LinkOption.NOFOLLOW_LINKS)) {
            if (Files.size(privatePath) != spec.compressedBytes)
                throw new IOException("应用专属目录中的环境包大小不匹配，请重新拷贝。");
            return () -> new FileInputStream(privatePath.toFile());
        }
        if (!hasDownloadsAccess(context))
            throw new IOException("请允许 Codex 读取存储，或把 " + ARCHIVE_NAME + " 拷到 "
                    + privateArchiveFile(context).getAbsolutePath() + "。");
        Path archive = archiveFile().toPath();
        if (!Files.isRegularFile(archive, LinkOption.NOFOLLOW_LINKS))
            throw new IOException("未找到环境包，请下载 " + ARCHIVE_NAME + " 到 Download 目录后重新检查，无需解压。");
        if (Files.size(archive) != spec.compressedBytes)
            throw new IOException("Download 中的环境包大小不匹配，可能尚未下载完成或版本不兼容，请重新下载配套环境包。");
        return () -> {
            if (!hasDownloadsAccess(context) || !Files.isRegularFile(archive, LinkOption.NOFOLLOW_LINKS)
                    || Files.size(archive) != spec.compressedBytes)
                throw new IOException("Download 中的环境包已变化或无法读取，请重新检查。");
            return new FileInputStream(archive.toFile());
        };
    }

    /** Opens the archive embedded in this APK, if a full build shipped one. */
    public static RootfsTransaction.ArchiveSource bundled(Context context) throws IOException {
        String[] assets = context.getAssets().list("phone-runtime");
        for (String name : assets == null ? new String[0] : assets) {
            if (!name.startsWith("codex-phone-rootfs.")) continue;
            return () -> context.getAssets().open("phone-runtime/" + name,
                    android.content.res.AssetManager.ACCESS_STREAMING);
        }
        return null;
    }

    public static boolean hasBundledArchive(Context context) {
        try { return bundled(context) != null; } catch (IOException unavailable) { return false; }
    }

    /** Opens whichever authenticated transport this APK provides. */
    public static RootfsTransaction.ArchiveSource open(Context context, RootfsExtractor.Spec spec) throws IOException {
        RootfsTransaction.ArchiveSource embedded = bundled(context);
        return embedded != null ? embedded : downloads(context, spec);
    }
}