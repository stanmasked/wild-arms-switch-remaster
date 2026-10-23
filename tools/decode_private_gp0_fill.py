"""Conservative GP0(02h) VRAM quick-fill geometry, no original game assets.

PS1 GP0(02) performs a 15-bit BGR555 VRAM fill; the 24-bit RGB command
drops three low bits per channel and bit 15 is always zero. X is rounded
down to 16 pixels, width is rounded up to 16 pixels, Y/height are
9-bit masked. Fill ignores GP0(E6) masking.

PS1 hardware can wrap at VRAM boundaries. This owner-private replay
intentionally rejects nonempty wrapped fills instead of pretending to
model the wrapped case. The zero-dimension command is a genuine no-op.
"""
VRAM_WIDTH=1024
VRAM_HEIGHT=512
FILL_KNOWN_BITS=0x01ff03ff


def decode_bounded_gp0_fill(words):
    """Return strict {x,y,width,height,pixel} or raise ValueError."""
    if (type(words) is not list or len(words)!=3 or
            any(type(w) is not int or not 0<=w<=0xffffffff for w in words)
            or words[0]>>24 != 0x02):
        raise ValueError("GP0 02 fill must contain exactly three u32 words")
    color, origin, size=words
    # Reserved upper bits are ignored by the real GPU. Our restricted
    # provenance gate rejects aliases rather than silently normalizing them.
    if origin & ~FILL_KNOWN_BITS or size & ~FILL_KNOWN_BITS:
        raise ValueError("GP0 02 fill has reserved coordinate or size bits")
    x=origin&0x3f0
    y=(origin>>16)&0x1ff
    raw_width=size&0x3ff
    width=(raw_width+15)&~15
    height=(size>>16)&0x1ff
    if width and height and (x+width>VRAM_WIDTH or y+height>VRAM_HEIGHT):
        raise ValueError("GP0 02 fill rectangle wraps beyond supported VRAM")
    r=(color&0xff)>>3
    g=((color>>8)&0xff)>>3
    b=((color>>16)&0xff)>>3
    return {"x":x,"y":y,"width":width,"height":height,
            "pixel":(b<<10)|(g<<5)|r}
