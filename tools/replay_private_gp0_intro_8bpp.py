#!/usr/bin/env python3
"""Stage527: bounded PS1 GP0(64) 4bpp and GP0(66) 8bpp RGB555 replay.

This deliberately models only the bounded GPU state and primitive subset
verified against an owner-private INTRO native GPU dump. Do NOT use it as a
general PS1 rasterizer. Unsupported modes, cache hazards or commands fail
closed; original game data are never included in public CI.

The caller must independently authenticate the complete native trace,
pre-trace VRAM and first-VSync framing. A byte-exact result alone does not
authenticate those inputs, the GUI snapshot or the original game disc.
"""
from collections import Counter
import struct

from decode_private_gp0_fill import decode_bounded_gp0_fill
from replay_private_gp0_quad_2c import replay_bounded_4bpp_quad

WIDTH = 1024
HEIGHT = 512
VRAM_BYTES = WIDTH * HEIGHT * 2
MAX_PACKETS = 20000


def _xy_signed(word):
    x = word & 0x7ff
    y = (word >> 16) & 0x7ff
    return (x - 0x800 if x & 0x400 else x,
            y - 0x800 if y & 0x400 else y)


def _overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def replay_bounded_8bpp_intro(initial_vram, packets):
    """Replay bounded GP0(02)/GP0(64)/(66) and E1-E6 GPU registers.

    Returns (full_1MiB_vram, redacted_counts). Input must be the pretrace
    1024x512 u16 little-endian VRAM and a list of complete GP0 packets.
    The renderer intentionally refuses all other rasterizing commands.
    """
    if type(initial_vram) is not bytes or len(initial_vram) != VRAM_BYTES:
        raise ValueError("Stage524 requires an exact 1MiB preframe VRAM")
    if (type(packets) is not list or not 1 <= len(packets) <= MAX_PACKETS):
        raise ValueError("Stage524 requires finite ordered complete GP0 packets")
    vram = bytearray(initial_vram)
    e1 = e2 = e3 = e4 = e5 = e6 = None
    counts = Counter()
    pixels_written = 0
    for packet in packets:
        if (type(packet) is not list or not 1 <= len(packet) <= 9 or
                any(type(w) is not int or not 0 <= w <= 0xffffffff
                    for w in packet)):
            raise ValueError("Stage524 unsupported GP0 packet size or words")
        opcode = packet[0] >> 24
        if opcode == 0:
            if len(packet) != 1 or packet[0] != 0:
                raise ValueError("Stage524 only admits canonical GP0 NOP")
            counts["00_NOP"] += 1
            continue
        if 0xe1 <= opcode <= 0xe6:
            if len(packet) != 1:
                raise ValueError("Stage524 truncated GP0 state command")
            w = packet[0] & 0x00ffffff
            if opcode == 0xe1:
                if w & ~0x00003fff:
                    raise ValueError("Stage524 unsupported GP0 E1 reserved bits")
                e1 = w
            elif opcode == 0xe2:
                if w & ~0x000fffff:
                    raise ValueError("Stage524 GP0 E2 reserved bits")
                e2 = w
            elif opcode in (0xe3, 0xe4):
                if w & ~0x0007ffff:
                    raise ValueError("Stage524 GP0 E3/E4 reserved bits")
                xy = (w & 0x3ff, (w >> 10) & 0x1ff)
                if opcode == 0xe3:
                    e3 = xy
                else:
                    e4 = xy
            elif opcode == 0xe5:
                if w & ~0x003fffff:
                    raise ValueError("Stage524 GP0 E5 reserved bits")
                e5 = w
            else:
                if w & ~3:
                    raise ValueError("Stage524 GP0 E6 reserved bits")
                e6 = w
            counts["GPU_STATE"] += 1
            continue
        if opcode == 0x02:
            fill = decode_bounded_gp0_fill(packet)
            x, y, width, height = (
                fill[k] for k in ("x", "y", "width", "height"))
            if width and height:
                row = struct.pack("<H", fill["pixel"]) * width
                for yy in range(y, y + height):
                    pos = (yy * WIDTH + x) * 2
                    vram[pos:pos + 2 * width] = row
                pixels_written += width * height
            counts["02_BOUNDED_FILL"] += 1
            continue
        if opcode == 0x2c:
            if None in (e1, e2, e3, e4, e5, e6):
                raise ValueError("Stage528 GP0(2C) missing explicit GPU state")
            pixels_written += replay_bounded_4bpp_quad(
                vram, packet,
                draw_area=(e3[0], e3[1], e4[0], e4[1]),
                texture_window=e2, offset=e5, mask=e6)
            counts["2C_BOUNDED_OPAQUE_4BPP_QUAD"] += 1
            continue
        if opcode not in (0x66, 0x64):
            raise ValueError("Stage524 GPU primitive or GP0 operation unsupported")
        if len(packet) != 4:
            raise ValueError("Stage524 textured rectangle must have four words")
        if None in (e1, e2, e3, e4, e5, e6):
            raise ValueError("Stage524 rectangle without complete explicit GPU state")
        depth = (e1 >> 7) & 3
        required_depth = 0 if opcode == 0x64 else 1
        if (e2 != 0 or e5 != 0 or e6 != 0 or
                depth != required_depth or
                ((e1 >> 5) & 3) != 1 or
                (e1 & (3 << 12)) != 0):
            mode = "4bpp" if opcode == 0x64 else "8bpp"
            raise ValueError(
                "Stage524 requires " + mode +
                "/ABR1/no-flip/mask-off/no-window/offset")
        if e3[0] > e4[0] or e3[1] > e4[1]:
            raise ValueError("Stage524 inverted GPU drawing area")
        rgb, vertex_word, uv_word, dimensions = packet
        x, y = _xy_signed(vertex_word)
        width, height = dimensions & 0x3ff, (dimensions >> 16) & 0x1ff
        if ((vertex_word & 0xf800f800) or
                (dimensions & ~0x01ff03ff)):
            raise ValueError("Stage524 ambiguous sprite coordinates or dimensions")
        if (x < 0 or y < 0 or x + width > WIDTH or
                y + height > HEIGHT):
            raise ValueError("Stage524 sprite wraps outside VRAM")
        if not width or not height:
            counts["64_EMPTY_RECT" if opcode == 0x64 else "66_EMPTY_RECT"] += 1
            continue
        texture_x = (e1 & 0xf) * 64
        texture_y = ((e1 >> 4) & 1) * 256
        uv_x, uv_y = uv_word & 0xff, (uv_word >> 8) & 0xff
        clut = uv_word >> 16
        if clut & 0x8000:
            raise ValueError("Stage524 reserved CLUT bit15")
        clut_x, clut_y = (clut & 0x3f) * 16, (clut >> 6) & 0x1ff
        texture_words = 64 if opcode == 0x64 else 128
        clut_words = 16 if opcode == 0x64 else 256
        if (texture_x + texture_words > WIDTH or
                texture_y + 256 > HEIGHT or
                clut_x + clut_words > WIDTH or clut_y >= HEIGHT):
            raise ValueError("Stage524 indexed texture or CLUT outside VRAM")
        destination = (x, y, width, height)
        if (_overlap(destination, (texture_x, texture_y, texture_words, 256)) or
                _overlap(destination, (clut_x, clut_y, clut_words, 1))):
            raise ValueError("Stage524 self-modifying texture/CLUT cache not modeled")
        for dy in range(height):
            yy = y + dy
            if not e3[1] <= yy <= e4[1]:
                continue
            tv = (uv_y + dy) & 0xff
            texture_row = (texture_y + tv) * WIDTH + texture_x
            for dx in range(width):
                xx = x + dx
                if not e3[0] <= xx <= e4[0]:
                    continue
                tu = (uv_x + dx) & 0xff
                if opcode == 0x64:
                    # PS1 four-bit indexed texture: four palette indices
                    # packed in each 16-bit little-endian texture word.
                    texture_word = struct.unpack_from(
                        "<H", vram, (texture_row + tu // 4) * 2)[0]
                    index = (texture_word >> (4 * (tu & 3))) & 0xf
                else:
                    # Stage524 eight-bit indexed texture, two indices/u16.
                    texture_word = struct.unpack_from(
                        "<H", vram, (texture_row + tu // 2) * 2)[0]
                    index = (texture_word >> (8 * (tu & 1))) & 0xff
                texel = struct.unpack_from(
                    "<H", vram, (clut_y * WIDTH + clut_x + index) * 2)[0]
                # PS1 index zero is not necessarily transparent: only the
                # *resolved* RGB555 value 0x0000 is fully transparent.
                if texel == 0:
                    continue
                color = [
                    min(31, (((texel >> (5 * channel)) & 31) *
                             ((rgb >> (8 * channel)) & 255)) >> 7)
                    for channel in (0, 1, 2)
                ]
                offset = (yy * WIDTH + xx) * 2
                background = struct.unpack_from("<H", vram, offset)[0]
                if opcode == 0x66 and (texel & 0x8000):
                    # Only GP0(66) has ABE=1; GP0(64) is opaque even
                    # when CLUT texel STP bit15 is set.
                    # ABE=1, Texel.STP=1 and ABR=1 => B+F, saturated
                    # independently on each of the 5-bit RGB channels.
                    color = [
                        min(31, v + ((background >> (5 * i)) & 31))
                        for i, v in enumerate(color)
                    ]
                output = (color[0] | (color[1] << 5) |
                          (color[2] << 10) | (texel & 0x8000))
                struct.pack_into("<H", vram, offset, output)
                pixels_written += 1
        counts["64_TEXTURED_OPAQUE_4BPP_RECT" if opcode == 0x64 else
               "66_TEXTURED_SEMITRANSPARENT_RECT"] += 1
    return bytes(vram), {
        "schema": 1,
        "kind": "WA1_SYNTHETIC_BOUNDED_GPU_INDEXED_RECTANGLE_REPLAY",
        "complete_packet_count": len(packets),
        "counts": dict(sorted(counts.items())),
        "bounded_pixel_write_count_not_unique_pixels": pixels_written,
        "gpu_unsupported_opcodes_and_states_fail_closed": True,
        "native_capture_and_scene_identity_not_authenticated_here": True,
        "drawing_to_display_interlace_semantics_not_verified": True,
        "gpu_texture_cache_coherency_not_modeled": True,
        "only_e1_4bpp_GP0_64_or_8bpp_GP0_66_ABR1_e2_e5_e6_zero": True,
        "2C_only_canonical_axis_aligned_one_to_one_4bpp_rectangles": True,
    }
