package com.ai.codex;

import java.io.IOException;
import java.io.InterruptedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.security.MessageDigest;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import static org.junit.Assert.*;

public final class EnvironmentEnginePayloadTest {
    @Rule public final TemporaryFolder temporary = new TemporaryFolder();

    private byte[] elf() {
        byte[] bytes = new byte[8192];
        bytes[0] = 0x7f; bytes[1] = 'E'; bytes[2] = 'L'; bytes[3] = 'F';
        bytes[4] = 2; bytes[5] = 1; bytes[18] = (byte)183;
        for (int i = 20; i < bytes.length; i++) bytes[i] = (byte)i;
        return bytes;
    }
    private String hash(byte[] bytes) throws Exception {
        return EnginePayloadFile.hex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }
    private interface Checked { void run() throws Exception; }
    private void expectIo(Checked operation) throws Exception {
        try { operation.run(); fail("Expected IOException"); } catch (IOException expected) { }
    }

    @Test public void verifiesExistingArm64ElfWithoutChangingContentOrMtime() throws Exception {
        byte[] bytes = elf();
        Path file = temporary.newFile("codex-native").toPath();
        Files.write(file, bytes);
        Files.setLastModifiedTime(file, FileTime.fromMillis(1600000000000L));
        FileTime modified = Files.getLastModifiedTime(file);
        EnginePayloadFile.verify(file, bytes.length, hash(bytes));
        assertArrayEquals(bytes, Files.readAllBytes(file));
        assertEquals(modified, Files.getLastModifiedTime(file));
    }

    @Test public void rejectsWrongHashAndSizeWhileKeepingOriginalFile() throws Exception {
        byte[] bytes = elf();
        Path file = temporary.newFile("codex-native").toPath();
        Files.write(file, bytes);
        expectIo(() -> EnginePayloadFile.verify(file, bytes.length, "0".repeat(64)));
        expectIo(() -> EnginePayloadFile.verify(file, bytes.length - 1, hash(bytes)));
        expectIo(() -> EnginePayloadFile.verify(file, bytes.length + 1, hash(bytes)));
        assertArrayEquals(bytes, Files.readAllBytes(file));
    }

    @Test public void rejectsHashMatchingWrongArchitectureAndNonElf() throws Exception {
        Path file = temporary.newFile("codex-native").toPath();
        byte[] wrongArch = elf(); wrongArch[18] = 62;
        Files.write(file, wrongArch);
        expectIo(() -> EnginePayloadFile.verify(file, wrongArch.length, hash(wrongArch)));
        byte[] nonElf = elf(); nonElf[0] = 0;
        Files.write(file, nonElf);
        expectIo(() -> EnginePayloadFile.verify(file, nonElf.length, hash(nonElf)));
        assertArrayEquals(nonElf, Files.readAllBytes(file));
    }

    @Test public void rejectsSymlinkWithoutFollowingOrDeletingIt() throws Exception {
        byte[] bytes = elf();
        Path target = temporary.newFile("target").toPath();
        Files.write(target, bytes);
        Path link = temporary.getRoot().toPath().resolve("codex-native");
        Files.createSymbolicLink(link, target);
        expectIo(() -> EnginePayloadFile.verify(link, bytes.length, hash(bytes)));
        assertTrue(Files.isSymbolicLink(link));
        assertArrayEquals(bytes, Files.readAllBytes(target));
    }

    @Test public void interruptionPreservesTheExistingFileAndInterruptFlag() throws Exception {
        byte[] bytes = elf();
        Path file = temporary.newFile("codex-native").toPath();
        Files.write(file, bytes);
        String expected = hash(bytes);
        Thread.currentThread().interrupt();
        try {
            try { EnginePayloadFile.verify(file, bytes.length, expected); fail("Expected interruption"); }
            catch (InterruptedIOException interrupted) { assertTrue(Thread.currentThread().isInterrupted()); }
        } finally { Thread.interrupted(); }
        assertArrayEquals(bytes, Files.readAllBytes(file));
    }

    @Test public void rejectsInvalidDescriptorAndMissingFile() throws Exception {
        Path file = temporary.newFile("codex-native").toPath();
        byte[] bytes = elf(); Files.write(file, bytes);
        expectIo(() -> EnginePayloadFile.verify(file, bytes.length, null));
        expectIo(() -> EnginePayloadFile.verify(file, 19, hash(bytes)));
        expectIo(() -> EnginePayloadFile.verify(file, 536870913L, hash(bytes)));
        expectIo(() -> EnginePayloadFile.verify(file, bytes.length, "bad"));
        Files.delete(file);
        expectIo(() -> EnginePayloadFile.verify(file, bytes.length, hash(bytes)));
    }
}
