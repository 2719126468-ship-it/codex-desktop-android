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

static int codex_open_beneath(int root, const char *path, int flags, int mode) {
#ifdef __ANDROID__
    /* Vendor seccomp may kill openat2 with SIGSYS rather than return ENOSYS.
     * Walk each component without links and retain openat2's device boundary. */
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
    int current = fcntl(root, F_DUPFD_CLOEXEC, 3);
    if (current < 0) return -1;
    const char *component = path;
    for (;;) {
        const char *end = strchr(component, '/');
        size_t length = end ? (size_t)(end - component) : strlen(component);
        if (!length || length > NAME_MAX ||
                (length == 1 && component[0] == '.') ||
                (length == 2 && component[0] == '.' && component[1] == '.')) {
            errno = length > NAME_MAX ? ENAMETOOLONG : EINVAL;
            close(current);
            return -1;
        }
        char name[NAME_MAX + 1];
        memcpy(name, component, length);
        name[length] = 0;
        int final = end == NULL;
        int next = openat(current, name,
            final ? flags | O_NOFOLLOW : O_PATH | O_CLOEXEC | O_DIRECTORY | O_NOFOLLOW, mode);
        if (next < 0) {
            int saved = errno;
            close(current);
            errno = saved;
            return -1;
        }
        struct stat info;
        if (fstat(next, &info) < 0) {
            int saved = errno;
            close(next);
            close(current);
            errno = saved;
            return -1;
        }
        if (info.st_dev != root_info.st_dev) {
            close(next);
            close(current);
            errno = EXDEV;
            return -1;
        }
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
