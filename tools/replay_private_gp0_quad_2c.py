#!/usr/bin/env python3
"""ROM-free Stage528 PS1 GPU GP0(2C) narrow opaque 4bpp axis-aligned quad.

Not a general affine, perspective or triangle-edge rasterizer. Requires
canonical rectangle corners, UV differences of exactly one texel per
pixel, bounded page/CLUT, explicit clipping and absence of texture feedback.
No original-game pixels, GPU packets, hashes or screenshots appear here.
"""
import struct

WIDTH, HEIGHT = 1024, 512


def _xy(word):
    if type(word) is not int or word & 0xf800f800:
        raise ValueError("GP0(2C) vertex reserved bits or type")
    x, y = word & 0x7ff, (word >> 16) & 0x7ff
    if x & 0x400:
        x -= 0x800
    if y & 0x400:
        y -= 0x800
    return x, y


def _overlap(a, b):
    x, y, w, h = a
    xx, yy, ww, hh = b
    return x < xx + ww and xx < x + w and y < yy + hh and yy < y + h


def replay_bounded_4bpp_quad(vram, packet, *, draw_area, texture_window=0,
                              offset=0, mask=0):
    """Mutate owner-supplied 1MiB VRAM, returning number of written pixels.

    Nine-word GP0(2C): color, XY0, UV0|CLUT, XY1, UV1|TPAGE,
    XY2, UV2, XY3, UV3. Caller authenticates transport and capture timing.
    """
    if type(vram) is not bytearray or len(vram) != WIDTH * HEIGHT * 2:
        raise ValueError("GP0(2C) requires bytearray full VRAM")
    if (type(packet) is not list or len(packet) != 9 or
        any(type(word) is not int or not 0 <= word <= 0xffffffff for word in packet)
        or packet[0] >> 24 != 0x2c):
        raise ValueError("GP0(2C) must be one complete opaque textured quad")
    if (type(draw_area) is not tuple or len(draw_area) != 4 or
        any(type(z) is not int for z in draw_area)):
        raise ValueError("GP0(2C) requires explicit drawing area")
    if texture_window != 0 or offset != 0 or mask != 0:
        raise ValueError("GP0(2C) nonzero texture window, draw offset or mask unsupported")
    x_min, y_min, x_max, y_max = draw_area
    if not (0 <= x_min <= x_max < WIDTH and 0 <= y_min <= y_max < HEIGHT):
        raise ValueError("GP0(2C) inverted/bad drawing area")
    vertices = [_xy(packet[i]) for i in (1, 3, 5, 7)]
    (x, y), (right, top), (left, bottom), (right2, bottom2) = vertices
    if not (x == left and right == right2 and y == top and bottom == bottom2):
        raise ValueError("GP0(2C) nonrectangular quadrilateral unsupported")
    width, height = right - x, bottom - y
    if not (1 <= width <= 256 and 1 <= height <= 256 and
            x >= 0 and y >= 0 and right <= WIDTH and bottom <= HEIGHT):
        raise ValueError("GP0(2C) rectangle beyond supported dimensions or VRAM")
    uv = [(packet[i] & 255, (packet[i] >> 8) & 255) for i in (2, 4, 6, 8)]
    (u, v), (u1, v1), (u2, v2), (u3, v3) = uv
    if not (u == u2 and v == v1 and u1 == u3 and v2 == v3 and
            ((u + width - 1) & 255) == u1 and
            ((v + height - 1) & 255) == v2):
        raise ValueError("GP0(2C) UVs are not canonical one-texel-per-pixel rectangle")
    clut = packet[2] >> 16
    tpage = packet[4] >> 16
    if (clut & 0x8000 or tpage & ~0x9ff or
        ((tpage >> 7) & 3) != 0 or ((tpage >> 5) & 3) != 1 or
        ((tpage >> 11) & 1) or ((tpage >> 12) & 3)):
        raise ValueError("GP0(2C) requires validated 4bpp ABR1 tpage/CLUT")
    if packet[6] >> 16 or packet[8] >> 16:
        raise ValueError("GP0(2C) reserved UV2/UV3 high words must be zero")
    texture_x, texture_y = (tpage & 15) * 64, ((tpage >> 4) & 1) * 256
    clut_x, clut_y = (clut & 63) * 16, (clut >> 6) & 511
    if texture_x + 64 > WIDTH or clut_x + 16 > WIDTH or clut_y >= HEIGHT:
        raise ValueError("GP0(2C) texture/CLUT VRAM bounds")
    target = (x, y, width, height)
    if (_overlap(target, (texture_x, texture_y, 64, 256)) or
        _overlap(target, (clut_x, clut_y, 16, 1))):
        raise ValueError("GP0(2C) texture/CLUT framebuffer feedback unmodeled")
    color = packet[0]
    # A textured polygon interpolates UV across its pixel spans.
    # Vertex UV endpoints are width-1 / height-1 texels apart, but
    # the polygon covers width/height *pixel cells*. 16.16 gradients
    # with +0x8000 pixel-center rounding model the pinned PCSX-Redux
    # flat-shaded textured triangle rasterizer in this bounded case.
    # A 256-wide quad's last pixel maps to U=254, not U=255.
    du16 = ((width - 1) << 16) // width
    dv16 = ((height - 1) << 16) // height
    writes = 0
    for dy in range(height):
        yy = y + dy
        if not y_min <= yy <= y_max:
            continue
        ty = texture_y + ((v + ((dy * dv16 + 0x8000) >> 16)) & 255)
        for dx in range(width):
            xx = x + dx
            if not x_min <= xx <= x_max:
                continue
            tu = (u + ((dx * du16 + 0x8000) >> 16)) & 255
            texword = struct.unpack_from("<H", vram, 2 * (ty * WIDTH + texture_x + tu // 4))[0]
            index = (texword >> (4 * (tu & 3))) & 15
            pixel = struct.unpack_from("<H", vram, 2 * (clut_y * WIDTH + clut_x + index))[0]
            if pixel == 0:
                continue
            channels = [min(31, (((pixel >> (5 * i)) & 31) *
                                 ((color >> (8 * i)) & 255)) >> 7)
                        for i in range(3)]
            value = (pixel & 0x8000) | channels[0] | (channels[1] << 5) | (channels[2] << 10)
            struct.pack_into("<H", vram, 2 * (yy * WIDTH + xx), value)
            writes += 1
    return writes
