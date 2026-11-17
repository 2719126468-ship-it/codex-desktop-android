package com.ai.codex;
import org.junit.Test;
import static org.junit.Assert.*;
public class CodexLogExportTest {
    @Test public void hidesHeadersAndConfigKeys() {
        String text = "Authorization: Bearer secret-header\n{\"Authorization\":\"Bearer secret-json\"}\n"
            + "experimental_bearer_token = \"secret-toml\"\naccess_token: secret-token\nCookie: a=secret-cookie; b=another-secret\n";
        String cleaned = CodexLogExport.redact(text);
        for (String secret : new String[]{"secret-header", "secret-json", "secret-toml", "secret-token", "secret-cookie", "another-secret"}) assertFalse(cleaned.contains(secret));
        assertTrue(cleaned.contains("[REDACTED]"));
    }
    @Test public void keepsUsefulStartupDiagnostics() {
        String text = "Codex graphics: Debian Mesa llvmpipe\nEGL initialization failed: 0x3001\n";
        assertEquals(text, CodexLogExport.redact(text));
    }
}
