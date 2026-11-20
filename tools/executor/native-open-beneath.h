/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef CODEX_NATIVE_OPEN_BENEATH_H
#define CODEX_NATIVE_OPEN_BENEATH_H

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/openat2.h>
#include <stdint.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

#ifdef __ANDROID__
static int codex_mount_id(int fd, uint64_t *id) {
    struct statx info;
    if (syscall(SYS_statx, fd, "", AT_EMPTY_PATH | AT_SYMLINK_NOFOLLOW, STATX_MNT_ID, &info) < 0)
        return -1;
    if (!(info.stx_mask & STATX_MNT_ID)) {
        errno = EOPNOTSUPP;
        return -1;
    }
    *id = info.stx_mnt_id;
    return 0;
}

static int codex_close_path(int parent, int child, int error) {
    if (child >= 0) close(child);
    close(parent);
    errno = error;
    return -1;
}
#endif

static int codex_open_beneath(int root, const char *path, int flags, int mode) {
#ifdef __ANDROID__
    /* Vendor seccomp may kill openat2 with SIGSYS rather than return ENOSYS.
     * Compare mount IDs so same-device bind mounts are also excluded. */
    if (!path[0] || path[0] == '/') {
        errno = EINVAL;
        return -1;
    }
    struct stat root_info;
    if (fstat(root, &root_info) < 0) return -1;
    if (!S_ISDIR(root_info.st_mode)) {
        errno = ENOTDIR;
        return -1;
    }
    /* A bare dot names the already admitted root. Dots within a walk are invalid. */
    if (!strcmp(path, ".")) return openat(root, ".", flags | O_NOFOLLOW, mode);
    uint64_t root_mount;
    if (codex_mount_id(root, &root_mount) < 0) return -1;
    int current = fcntl(root, F_DUPFD_CLOEXEC, 3);
    if (current < 0) return -1;
    const char *component = path;
    for (;;) {
        const char *end = strchr(component, '/');
        size_t length = end ? (size_t)(end - component) : strlen(component);
        if (!length || length > NAME_MAX ||
                (length == 1 && component[0] == '.') ||
                (length == 2 && component[0] == '.' && component[1] == '.')) {
            return codex_close_path(current, -1, length > NAME_MAX ? ENAMETOOLONG : EINVAL);
        }
        char name[NAME_MAX + 1];
        memcpy(name, component, length);
        name[length] = 0;
        int final = end == NULL;
        int next = openat(current, name,
            final ? flags | O_NOFOLLOW : O_PATH | O_CLOEXEC | O_NOFOLLOW, mode);
        if (next < 0) return codex_close_path(current, -1, errno);
        struct stat info;
        if (fstat(next, &info) < 0) return codex_close_path(current, next, errno);
        if (S_ISLNK(info.st_mode)) return codex_close_path(current, next, ELOOP);
        if (!final && !S_ISDIR(info.st_mode)) return codex_close_path(current, next, ENOTDIR);
        uint64_t next_mount;
        if (codex_mount_id(next, &next_mount) < 0) return codex_close_path(current, next, errno);
        if (next_mount != root_mount) return codex_close_path(current, next, EXDEV);
        close(current);
        if (final) return next;
        current = next;
        component = end + 1;
    }
#else
    struct open_how how = {.flags = (uint64_t)flags, .mode = (uint64_t)mode,
        .resolve = RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS | RESOLVE_NO_XDEV};
    return (int)syscall(SYS_openat2, root, path, &how, sizeof(how));
#endif
}

#endif
