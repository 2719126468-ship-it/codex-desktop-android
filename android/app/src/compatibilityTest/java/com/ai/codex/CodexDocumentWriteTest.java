package com.ai.codex;

import org.junit.Test;
import static org.junit.Assert.*;
import java.nio.file.*;

public class CodexDocumentWriteTest {
    @Test public void shortReplacementIsInvisibleUntilCommitAndHasNoTail() throws Exception {
        Path directory = Files.createTempDirectory("codex-document-test-");
        Path file = directory.resolve("config.toml");
        Files.writeString(file, "model = \"a very long original model\"\n");
        CodexDocumentWrite write = new CodexDocumentWrite(file, true);
        try {
            Files.writeString(write.temporary, "model = \"x\"\n");
            assertTrue(Files.readString(file).contains("original"));
            write.commit();
            assertEquals("model = \"x\"\n", Files.readString(file));
        } finally { write.abort(); Files.deleteIfExists(file); Files.delete(directory); }
    }
    @Test public void abortedWriteKeepsOriginal() throws Exception {
        Path directory = Files.createTempDirectory("codex-document-test-");
        Path file = directory.resolve("config.toml"); Files.writeString(file, "original");
        CodexDocumentWrite write = new CodexDocumentWrite(file, true);
        Files.writeString(write.temporary, "partial"); write.abort();
        assertEquals("original", Files.readString(file));
        assertFalse(Files.exists(write.temporary));
        Files.delete(file); Files.delete(directory);
    }
    @Test public void externalReplacementIsNotOverwritten() throws Exception {
        Path directory = Files.createTempDirectory("codex-document-test-");
        Path file = directory.resolve("config.toml"); Files.writeString(file, "original");
        CodexDocumentWrite write = new CodexDocumentWrite(file, true);
        try {
            Files.writeString(write.temporary, "ours");
            Path replacement = directory.resolve("external"); Files.writeString(replacement, "external");
            Files.move(replacement, file, StandardCopyOption.REPLACE_EXISTING);
            try { write.commit(); fail("must detect external replacement"); } catch (java.io.IOException expected) {}
            assertEquals("external", Files.readString(file));
        } finally { write.abort(); Files.deleteIfExists(file); Files.delete(directory); }
    }
    @Test public void linkedTargetCannotBeOpenedForWrite() throws Exception {
        Path directory = Files.createTempDirectory("codex-document-test-");
        Path original = directory.resolve("original"); Files.writeString(original, "original");
        Path link = directory.resolve("config.toml"); Files.createSymbolicLink(link, original);
        try { new CodexDocumentWrite(link, true); fail("must reject links"); } catch (java.io.IOException expected) {}
        Files.delete(link); Files.delete(original); Files.delete(directory);
    }
}
