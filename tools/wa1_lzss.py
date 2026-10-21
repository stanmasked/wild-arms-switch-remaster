#!/usr/bin/env python3
"""Bounded Wild Arms 1 PS1 LZSS stream decoder (no bundled game assets).

Reference format: Christian Bauer, wa1tools, wa/lzss.py.
https://github.com/cebix/wa1tools (ISC license)

Copyright (C) Christian Bauer <www.cebix.net>
Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

This implementation additionally validates complete bounds/output size and
reports the number of consumed encoded bytes; it rejects corrupt streams.
"""
import struct

DICT_BYTES = 4096
MAX_REF_BYTES = 18
MAX_DECODE_BYTES = 2 * 1024 * 1024


class LZSSDecodeError(ValueError):
    """Truncated or malformed stream; do not fabricate missing source bytes."""


def decode_wa1_lzss(source, *, max_output=MAX_DECODE_BYTES):
    """Decode 32-bit output-length-prefixed WA1 LZSS into (bytes, consumed).

    Encoded refs: first byte holds offset low 8 bits; *upper* nibble of
    second byte holds offset bits 8..11, *lower* nibble holds length minus 3.
    Flags are read least-significant bit first, 1=literal, 0=reference.
    The 4096-byte dictionary starts zeroed, with write position 4078.
    """
    if not isinstance(source, (bytes, bytearray, memoryview)):
        raise TypeError("source must be bytes-like")
    if type(max_output) is not int or not 1 <= max_output <= MAX_DECODE_BYTES:
        raise ValueError("invalid maximum output size")
    source = memoryview(source)
    if len(source) < 4:
        raise LZSSDecodeError("truncated length header")
    expected = struct.unpack_from("<I", source)[0]
    if expected == 0 or expected > max_output:
        raise LZSSDecodeError("invalid or excessive decoded-size header")
    dictionary = bytearray(DICT_BYTES)
    write_at = DICT_BYTES - MAX_REF_BYTES
    result = bytearray()
    cursor = 4
    while len(result) < expected:
        if cursor >= len(source):
            raise LZSSDecodeError("truncated flags")
        flags = source[cursor]
        cursor += 1
        for bit in range(8):
            if len(result) == expected:
                break
            if flags & (1 << bit):
                if cursor >= len(source):
                    raise LZSSDecodeError("truncated literal")
                value = source[cursor]
                cursor += 1
                result.append(value)
                dictionary[write_at] = value
                write_at = (write_at + 1) & 0xFFF
            else:
                if cursor + 2 > len(source):
                    raise LZSSDecodeError("truncated dictionary reference")
                offset = source[cursor] | ((source[cursor + 1] & 0xF0) << 4)
                length = (source[cursor + 1] & 0x0F) + 3
                cursor += 2
                if len(result) + length > expected:
                    raise LZSSDecodeError("dictionary reference overshoots decoded size")
                for _ in range(length):
                    value = dictionary[offset]
                    offset = (offset + 1) & 0xFFF
                    result.append(value)
                    dictionary[write_at] = value
                    write_at = (write_at + 1) & 0xFFF
    return bytes(result), cursor
