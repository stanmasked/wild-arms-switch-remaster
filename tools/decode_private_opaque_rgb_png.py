"""Strict bounded PNG RGB/RGBA decoder with no third-party dependency.

Only 8-bit opaque RGB/RGBA, non-interlaced, standard PNG filters.
The user's screenshot crop must be a lossless, unscaled exact ROI.
This decoder deliberately rejects palette/greyscale/16-bit/interlaced
screenshots instead of guessing color transforms or alpha composition.
"""
import struct
import zlib

from capture_private_pcsx_frame_witness import (
    validate_private_png, MAX_SCREEN_BYTES, PNG_SIGNATURE,
)

MAX_RAW_PIXELS=1024*512


def decode_private_opaque_rgb_png(data):
    """Return ((width,height), pure RGB bytes), no user pixels in reports."""
    if type(data) is not bytes or not 0<len(data)<=MAX_SCREEN_BYTES:
        raise ValueError("private PNG must be exact bounded byte string")
    validated=validate_private_png(data)  # also checks all chunk CRCs.
    width=validated["width"]
    height=validated["height"]
    if width*height>MAX_RAW_PIXELS:
        raise ValueError("private PNG exceeds raw VRAM pixel area")
    idat=[]
    pos=8
    started=False
    ended=False
    channels=None
    while pos<len(data):
        length=struct.unpack_from(">I",data,pos)[0]
        kind=data[pos+4:pos+8]
        content=data[pos+8:pos+8+length]
        pos+=length+12
        if kind==b"IHDR":
            if channels is not None or length!=13:
                raise ValueError("unexpected PNG header")
            w,h,depth,color,compression,filtering,interlace=struct.unpack(
                ">IIBBBBB",content)
            if ((w,h)!=(width,height) or depth!=8 or
                    color not in (2,6) or
                    compression!=0 or filtering!=0 or interlace!=0):
                raise ValueError("unsupported exact RGB PNG format")
            channels=3 if color==2 else 4
        elif kind==b"IDAT":
            if ended:
                raise ValueError("PNG IDAT chunks must be contiguous")
            started=True
            idat.append(content)
        elif kind==b"IEND":
            break
        elif kind[0]&0x20==0:
            raise ValueError("unknown critical PNG chunk unsupported")
        else:
            if started:
                ended=True
    if channels is None or not idat:
        raise ValueError("missing PNG image data")
    row_bytes=width*channels
    expected=height*(row_bytes+1)
    stream=zlib.decompressobj()
    inflated=stream.decompress(b"".join(idat),expected+1)
    if (len(inflated)!=expected or not stream.eof or
            stream.unconsumed_tail or stream.unused_data):
        raise ValueError("PNG decompression length or zlib stream invalid")
    result=bytearray(width*height*3)
    previous=bytes(row_bytes)
    cursor=0
    for row in range(height):
        kind=inflated[cursor]
        cursor+=1
        if kind>4:
            raise ValueError("unsupported PNG scanline filter")
        encoded=inflated[cursor:cursor+row_bytes]
        cursor+=row_bytes
        decoded=bytearray(row_bytes)
        for j,code in enumerate(encoded):
            left=decoded[j-channels] if j>=channels else 0
            above=previous[j]
            upper_left=previous[j-channels] if j>=channels else 0
            if kind==0:
                predictor=0
            elif kind==1:
                predictor=left
            elif kind==2:
                predictor=above
            elif kind==3:
                predictor=(left+above)//2
            else:
                candidate=left+above-upper_left
                left_delta=abs(candidate-left)
                up_delta=abs(candidate-above)
                upper_delta=abs(candidate-upper_left)
                predictor=(
                    left if left_delta<=up_delta and left_delta<=upper_delta
                    else above if up_delta<=upper_delta else upper_left)
            decoded[j]=(code+predictor)&0xff
        for i in range(width):
            start=i*channels
            if channels==4 and decoded[start+3]!=255:
                raise ValueError("transparent pixels not supported for exact RGB comparison")
            dst=(row*width+i)*3
            result[dst:dst+3]=decoded[start:start+3]
        previous=decoded
    return (width,height),bytes(result)
