/* SPDX-License-Identifier: GPL-3.0-only */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include "native-open-beneath.h"

#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "check failed at line %d: %s\n", __LINE__, strerror(errno)); \
    return 1; \
} } while (0)

static int write_file(int root, const char *path, const char *text) {
    int fd = codex_open_beneath(root, path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (fd < 0) return -1;
    ssize_t written = write(fd, text, strlen(text));
    int saved = errno;
    if (close(fd) < 0 && written >= 0) return -1;
    errno = saved;
    return written == (ssize_t)strlen(text) ? 0 : -1;
}

int main(int argc, char **argv) {
    const char *parent = argc > 1 ? argv[1] : "/var/tmp";
    char base[PATH_MAX];
    int length = snprintf(base, sizeof(base), "%s/codex-open-beneath-XXXXXX", parent);
    CHECK(length > 0 && length < (int)sizeof(base) && mkdtemp(base));
    int root = open(base, O_PATH | O_DIRECTORY | O_CLOEXEC);
    CHECK(root >= 0);
    int same_root = codex_open_beneath(root, ".", O_RDONLY | O_DIRECTORY | O_CLOEXEC, 0);
    struct stat root_info, same_root_info;
    CHECK(same_root >= 0 && fstat(root, &root_info) == 0 && fstat(same_root, &same_root_info) == 0);
    CHECK(root_info.st_dev == same_root_info.st_dev && root_info.st_ino == same_root_info.st_ino);
    CHECK(close(same_root) == 0);
    CHECK(mkdirat(root, "nested", 0700) == 0);
    CHECK(write_file(root, "nested/file", "real") == 0);
    int fd = codex_open_beneath(root, "nested/file", O_PATH | O_CLOEXEC, 0);
    CHECK(fd >= 0);
    struct stat info;
    CHECK(fstat(fd, &info) == 0 && S_ISREG(info.st_mode) && info.st_size == 4);
    close(fd);
    CHECK(write_file(root, "nested/created", "new") == 0);
    fd = codex_open_beneath(root, "nested/created", O_RDONLY | O_CLOEXEC, 0);
    CHECK(fd >= 0);
    char data[4] = {0};
    CHECK(read(fd, data, 3) == 3 && !memcmp(data, "new", 3));
    close(fd);
    CHECK(codex_open_beneath(root, "../escape", O_PATH | O_CLOEXEC, 0) < 0 && errno == EINVAL);
    CHECK(codex_open_beneath(root, "nested/./file", O_PATH | O_CLOEXEC, 0) < 0 && errno == EINVAL);
    CHECK(codex_open_beneath(root, "/absolute", O_PATH | O_CLOEXEC, 0) < 0 && errno == EINVAL);
    CHECK(symlinkat("file", root, "nested/link") == 0);
    CHECK(codex_open_beneath(root, "nested/link", O_PATH | O_CLOEXEC, 0) < 0 && errno == ELOOP);
    CHECK(symlinkat("/", root, "nested/escape") == 0);
    CHECK(codex_open_beneath(root, "nested/escape/etc", O_PATH | O_CLOEXEC, 0) < 0 && errno == ELOOP);
    int system_root = open("/", O_PATH | O_DIRECTORY | O_CLOEXEC);
    CHECK(system_root >= 0);
    CHECK(codex_open_beneath(system_root, "proc", O_PATH | O_CLOEXEC, 0) < 0 && errno == EXDEV);
    CHECK(close(system_root) == 0);
    CHECK(unlinkat(root, "nested/link", 0) == 0);
    CHECK(unlinkat(root, "nested/escape", 0) == 0);
    CHECK(unlinkat(root, "nested/file", 0) == 0);
    CHECK(unlinkat(root, "nested/created", 0) == 0);
    CHECK(unlinkat(root, "nested", AT_REMOVEDIR) == 0);
    CHECK(close(root) == 0);
    CHECK(unlinkat(AT_FDCWD, base, AT_REMOVEDIR) == 0);
    puts("PASS openat component walk, root/read/create, link and mount refusal");
    return 0;
}
