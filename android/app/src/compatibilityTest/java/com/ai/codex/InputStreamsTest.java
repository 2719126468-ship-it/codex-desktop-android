package com.ai.codex;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;
import org.junit.Test;
import static org.junit.Assert.*;

/** Runs with the app regression suite and independently on a host JVM. */
public final class InputStreamsTest {
    @Test public void shortReadsContinueUntilTheBoundOrEof() throws Exception {
        byte[] bytes = new byte[]{1, 2, 3, 4, 5};
        InputStream input = new ByteArrayInputStream(bytes) {
            @Override public synchronized int read(byte[] target, int offset, int length) {
                return super.read(target, offset, Math.min(length, 2));
            }
        };
        assertArrayEquals(bytes, InputStreams.readNBytesCompat(input, 12));
    }

    @Test public void aBoundedReadDoesNotConsumeTheNextPacket() throws Exception {
        ByteArrayInputStream input = new ByteArrayInputStream(new byte[]{1, 2, 3, 4, 5});
        assertArrayEquals(new byte[]{1, 2, 3}, InputStreams.readNBytesCompat(input, 3));
        assertEquals(4, input.read());
        assertEquals(1, input.available());
    }

    @Test public void zeroLimitDoesNotReadOrCloseTheInput() throws Exception {
        InputStream input = new InputStream() {
            @Override public int read() { throw new AssertionError("Unexpected read"); }
            @Override public void close() { throw new AssertionError("The caller owns this stream"); }
        };
        assertArrayEquals(new byte[0], InputStreams.readNBytesCompat(input, 0));
    }

    @Test(timeout = 1000) public void anEmptyBulkReadDoesNotSpinOrDropAZeroByte() throws Exception {
        InputStream input = new ByteArrayInputStream(new byte[]{0, 1, 2}) {
            private boolean first = true;
            @Override public synchronized int read(byte[] target, int offset, int length) {
                if (first) { first = false; return 0; }
                return super.read(target, offset, length);
            }
        };
        assertArrayEquals(new byte[]{0, 1, 2}, InputStreams.readNBytesCompat(input, 4));
    }

    @Test public void ioFailureAfterPartialDataIsStillReported() throws Exception {
        IOException failure = new IOException("read failed");
        InputStream input = new InputStream() {
            private boolean first = true;
            @Override public int read() throws IOException { throw failure; }
            @Override public int read(byte[] target, int offset, int length) throws IOException {
                if (first) { first = false; target[offset] = 7; return 1; }
                throw failure;
            }
        };
        assertSame(failure, assertThrows(IOException.class, () -> InputStreams.readNBytesCompat(input, 4)));
    }

    @Test public void aLargeLimitDoesNotPreallocateTheEntireLimit() throws Exception {
        assertArrayEquals(new byte[]{1, 2}, InputStreams.readNBytesCompat(
                new ByteArrayInputStream(new byte[]{1, 2}), Integer.MAX_VALUE));
    }

    @Test public void readAllBytesSpansMultipleBuffers() throws Exception {
        byte[] expected = new byte[20017];
        Arrays.fill(expected, (byte) 0x83);
        assertArrayEquals(expected, InputStreams.readNBytesCompat(new ByteArrayInputStream(expected), Integer.MAX_VALUE));
        assertArrayEquals(expected, InputStreams.readAllBytes(new ByteArrayInputStream(expected)));
    }

    @Test public void negativeLengthsAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> InputStreams.readNBytesCompat(new ByteArrayInputStream(new byte[0]), -1));
    }

    @Test public void newerPlatformsKeepTheirNativeStreamOverrides() throws Exception {
        InputStream nativeStream = new InputStream() {
            @Override public int read() { throw new AssertionError("Unexpected compatibility fallback"); }
            @Override public byte[] readNBytes(int length) { return new byte[]{(byte) length}; }
            @Override public byte[] readAllBytes() { return new byte[]{12, 13}; }
        };
        assertArrayEquals(new byte[]{7}, InputStreams.readNBytes(nativeStream, 7));
        assertArrayEquals(new byte[]{12, 13}, InputStreams.readAllBytes(nativeStream));
    }
}
