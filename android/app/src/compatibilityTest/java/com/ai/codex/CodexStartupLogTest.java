package com.ai.codex;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import static org.junit.Assert.*;

public final class CodexStartupLogTest {
    @Rule public final TemporaryFolder temporary = new TemporaryFolder();

    @Test public void milestonesUseElapsedTimeAndResetStartsAFreshLaunch() {
        CodexStartupLog log = new CodexStartupLog();
        log.reset(1000);
        assertTrue(log.step("检查运行环境", 1500));
        assertFalse(log.step("检查运行环境", 1900));
        assertFalse(log.step("  \n", 2000));
        assertTrue(log.runtime("desktop starting"));
        assertFalse(log.runtime("desktop starting"));
        assertEquals("[0000.5s] 检查运行环境\ndesktop starting", log.snapshot());

        log.reset(9000);
        assertEquals("", log.snapshot());
        assertTrue(log.step("检查运行环境", 8900));
        assertEquals("[0000.0s] 检查运行环境", log.snapshot());
    }

    @Test public void retainsOnlyRecentMilestonesAndReplacesRuntimeSnapshot() {
        CodexStartupLog log = new CodexStartupLog();
        log.reset(0);
        for (int i = 0; i < 15; i++) assertTrue(log.step("stage-" + i, i * 1000));
        log.runtime("obsolete runtime output");
        assertTrue(log.runtime("current runtime output"));
        String snapshot = log.snapshot();
        assertEquals(13, snapshot.split("\n").length);
        assertTrue(snapshot.startsWith("[0003.0s] stage-3\n"));
        assertTrue(snapshot.endsWith("[0014.0s] stage-14\ncurrent runtime output"));
        assertFalse(snapshot.contains("obsolete"));
        assertTrue(log.runtime(""));
        assertFalse(log.snapshot().contains("runtime output"));
    }

    @Test public void removesTerminalCommandsAndControlsButKeepsReadableDiagnostics() {
        String text = "\u001b]0;hidden title\u0007\u001b[32mGPU ready\u001b[0m\r\n"
                + "\u001b]8;;https://hidden.invalid\u001b\\link\u001b]8;;\u001b\\\tOK\u0000\b\u007f\n"
                + "\u001b[2J\u001b[H正在启动\r下一阶段";
        assertEquals("GPU ready\nlink  OK\n正在启动\n下一阶段", CodexStartupLog.sanitize(text));
        assertEquals("", CodexStartupLog.sanitize(null));
    }

    @Test public void hidesCredentialsHeadersAndAllUrlQueryValues() {
        String text = "Authorization: Bearer header-secret extra-header-secret\n"
                + "Proxy-Authorization: Basic proxy-secret\n"
                + "Cookie: session=cookie-secret; other=other-cookie-secret\n"
                + "{\"api_key\":\"api-secret\",\"access_token\":\"access-secret\"}\n"
                + "password=password-secret\nDB_PASSWORD=db-password-secret\n"
                + "client_secret=client-secret\nsession_token=session-secret\n"
                + "id_token=id-secret\ncode_verifier=verifier-secret\n"
                + "key=sk-abcdefghijklmnop123456\n"
                + "https://localhost/callback?code=query-secret&state=state-secret\n"
                + "EGL initialization failed: 0x3001";
        String clean = CodexStartupLog.sanitize(text);
        for (String secret : new String[]{"header-secret", "extra-header-secret", "proxy-secret",
                "cookie-secret", "other-cookie-secret", "api-secret", "access-secret",
                "password-secret", "db-password-secret", "client-secret", "session-secret",
                "id-secret", "verifier-secret", "sk-abcdefghijklmnop123456", "query-secret", "state-secret"}) {
            assertFalse("Leaked: " + secret, clean.contains(secret));
        }
        assertTrue(clean.contains("[REDACTED]"));
        assertTrue(clean.contains("https://localhost/callback?code=[REDACTED]&state=[REDACTED]"));
        assertTrue(clean.endsWith("EGL initialization failed: 0x3001"));
    }

    @Test public void snapshotKeepsLast64LinesAndCapsEachLineAt192Columns() {
        CodexStartupLog log = new CodexStartupLog();
        log.reset(0);
        log.step("old milestone", 0);
        StringBuilder text = new StringBuilder();
        for (int i = 0; i < 70; i++) text.append("line-").append(i).append('\n');
        text.append("x".repeat(500));
        log.runtime(text.toString());
        String[] lines = log.snapshot().split("\n");
        assertEquals(64, lines.length);
        assertEquals("line-7", lines[0]);
        for (String line : lines) assertTrue(line.length() <= 192);
        assertEquals("x".repeat(191) + "…", lines[63]);
        assertFalse(log.snapshot().contains("old milestone"));
    }

    @Test public void missingOrEmptyRuntimeFileIsOnlyAnEmptyDecoration() throws Exception {
        File missing = new File(temporary.getRoot(), "missing.log");
        assertEquals("", CodexStartupLog.readTail(missing));
        assertEquals("", CodexStartupLog.readTail(temporary.newFile("empty.log")));
    }

    @Test public void shortRuntimeTailPreservesUtf8AndRedactsBeforeReturning() throws Exception {
        File file = temporary.newFile("utf8.log");
        Files.write(file.toPath(), "正在启动 Codex…\naccess_token=private-value\n窗口已就绪\n".getBytes(StandardCharsets.UTF_8));
        assertEquals("正在启动 Codex…\naccess_token=[REDACTED]\n窗口已就绪", CodexStartupLog.readTail(file));
    }

    @Test public void tailSkipsACutMultibyteLineAtThe16KiBLimit() throws Exception {
        File file = temporary.newFile("large.log");
        String expected = "GPU ready\n窗口已就绪";
        byte[] bytes = ("机".repeat(6000) + "access_token=old-secret\n" + expected + "\n")
                .getBytes(StandardCharsets.UTF_8);
        assertTrue(bytes.length > 16 * 1024);
        assertTrue((bytes[bytes.length - 16 * 1024] & 0xc0) == 0x80);
        Files.write(file.toPath(), bytes);
        assertEquals(expected, CodexStartupLog.readTail(file));
        assertFalse(CodexStartupLog.readTail(file).contains("\ufffd"));
    }

    @Test public void anOversizedUnterminatedLineCannotExposeAPartialCredential() throws Exception {
        File file = temporary.newFile("unterminated.log");
        Files.write(file.toPath(), ("Authorization: Bearer " + "secret".repeat(4000)).getBytes(StandardCharsets.UTF_8));
        assertEquals("", CodexStartupLog.readTail(file));
        assertEquals("", CodexStartupLog.sanitize("x".repeat(17000)));
    }
}
