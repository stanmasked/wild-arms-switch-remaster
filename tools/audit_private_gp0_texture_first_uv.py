#!/usr/bin/env python3
"""Private conditional first-UV 4bpp texture/CLUT memory probe.

This models a single address pair in a supplied GP0 packet. It does NOT
rasterize triangles, prove that this UV was visible, emulate texture/CLUT
caches, or identify a source atlas. No source pixel index or color value
is included in its returned metadata. All reports remain owner-private.
"""
import hashlib

VRAM_WIDTH_WORDS = 1024
VRAM_HEIGHT = 512
VRAM_BYTES = VRAM_WIDTH_WORDS * VRAM_HEIGHT * 2


def probe_first_uv_4bpp(vram, last_upload_epoch, draw_epoch, info,
                        texture_window):
    """Match one declared UV nibble with its modeled 16-bit CLUT entry.

    'last_upload_epoch' is Stage437's per-halfword last-known-transfer
    epoch; -1 and older epochs are UNVERIFIED after GPU drawing.
    Texture window must have been explicitly set to exactly zero in
    this trace. Unknown or nonzero window => no speculative sample.
    """
    if (not isinstance(vram, (bytes,bytearray)) or len(vram) != VRAM_BYTES or
            len(last_upload_epoch) != VRAM_WIDTH_WORDS * VRAM_HEIGHT or
            type(draw_epoch) is not int or draw_epoch < 0 or
            type(info) is not dict or type(texture_window) not in (int,type(None))):
        raise ValueError("invalid private texture probe inputs")
    if texture_window is None:
        return {"status":"TEXTURE_WINDOW_STATE_NOT_OBSERVED",
                "texture_window_must_be_explicitly_zero":True,
                "gpu_sampling_unverified":True}
    if texture_window != 0:
        return {"status":"NONZERO_TEXTURE_WINDOW_NOT_MODELED",
                "texture_window_must_be_explicitly_zero":True,
                "gpu_sampling_unverified":True}
    fields=("tpage","clut","u","v")
    if any(type(info.get(field)) is not int for field in fields):
        raise ValueError("GP0 textured primitive lacks valid integer UV/CLUT/page")
    tpage, clut, u, v=(info[field] for field in fields)
    if (not 0 <= tpage <= 0xffff or not 0 <= clut <= 0xffff
            or not 0 <= u <= 255 or not 0 <= v <= 255
            or (tpage >> 7) & 3 or clut & 0x8000):
        raise ValueError("texture probe expects standard 4bpp TPAGE and CLUT")
    page_x=(tpage & 0xf)*64
    page_y=((tpage >> 4)&1)*256
    texture_x=page_x + (u//4)
    texture_y=page_y + v
    clut_x=(clut & 0x3f)*16
    clut_y=(clut >> 6)&0x1ff
    source_address=texture_y*VRAM_WIDTH_WORDS+texture_x
    tex_word=int.from_bytes(vram[2*source_address:2*source_address+2],"little")
    # u mod 4 selects one 4-bit index from the texture halfword.
    palette_index=(tex_word >> (4*(u%4))) & 15
    palette_address=clut_y*VRAM_WIDTH_WORDS+clut_x+palette_index
    source_16=vram[source_address*2:source_address*2+2]
    palette_16=vram[palette_address*2:palette_address*2+2]
    return {
        "status":"MODELED_FIRST_DECLARED_UV_WITH_DISABLED_TEXTURE_WINDOW",
        "first_uv_nibble_within_u16": u % 4,
        "first_uv_texture_word_x_words":texture_x,
        "first_uv_texture_word_y":texture_y,
        "first_uv_clut_row_x_words":clut_x,
        "first_uv_clut_row_y":clut_y,
        "texture_halfword_sha256":hashlib.sha256(source_16).hexdigest(),
        "selected_palette_halfword_sha256":hashlib.sha256(palette_16).hexdigest(),
        "texture_halfword_explicitly_written_since_last_draw":
            last_upload_epoch[source_address] == draw_epoch,
        "selected_clut_halfword_explicitly_written_since_last_draw":
            last_upload_epoch[palette_address] == draw_epoch,
        "first_uv_zero_index_hypothesis":palette_index == 0,
        "texture_window_must_be_explicitly_zero":True,
        "no_raw_texture_index_color_or_halfword_exported":True,
        "declared_uv_may_not_correspond_to_visible_rasterized_pixel":True,
        "gpu_sampling_and_cache_behavior_unverified":True,
    }
