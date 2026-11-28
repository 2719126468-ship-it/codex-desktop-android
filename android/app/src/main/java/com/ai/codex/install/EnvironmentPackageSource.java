package com.ai.codex.install;

import android.content.Context;
import android.os.Build;
import android.os.Environment;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

/** Fixed public Download transport; release hashes remain authenticated by the APK.
 * Android 8.1/9/10 do not expose MANAGE_EXTERNAL_STORAGE (API 30+): there the public
 * Download location is reachable through legacy READ_EXTERNAL_STORAGE instead, so the
 * access probe and the archive source both branch on the platform level. */
public final class EnvironmentPackageSource {
    public static final String ARCHIVE_NAME = "codex-phone-rootfs.tar.gz";
    private EnvironmentPackageSource() {}

    public static boolean needsInstall(Context context) {
        return !Files.exists(context.getFilesDir().toPath().resolve("debian"), LinkOption.NOFOLLOW_LINKS);
    }

    /** True when this build can read the public Download directory. */
    public static boolean hasDownloadsAccess(Context context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            return Environment.isExternalStorageManager();
        }
        return context.checkSelfPermission(android.Manifest.permission.READ_EXTERNAL_STORAGE)
                == android.content.pm.PackageManager.PERMISSION_GRANTED;
    }

    /** The permission this platform needs before the archive can be opened, or null. */
    public static String requiredPermission() {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.R ? null : android.Manifest.permission.READ_EXTERNAL_STORAGE;
    }

    public static File archiveFile() {
        return new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), ARCHIVE_NAME);
    }

    public static RootfsTransaction.ArchiveSource downloads(Context context, RootfsExtractor.Spec spec) throws IOException {
        if (!hasDownloadsAccess(context))
            throw new IOException("请允许 Codex 读取 Download 目录中的运行环境包。");
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

    /** True when the APK itself carries the environment archive. */
    public static boolean hasBundledArchive(Context context) {
        try { return bundled(context) != null; } catch (IOException unavailable) { return false; }
    }

    /** Opens whichever authenticated transport this APK provides. */
    public static RootfsTransaction.ArchiveSource open(Context context, RootfsExtractor.Spec spec) throws IOException {
        RootfsTransaction.ArchiveSource embedded = bundled(context);
        return embedded != null ? embedded : downloads(context, spec);
    }
}