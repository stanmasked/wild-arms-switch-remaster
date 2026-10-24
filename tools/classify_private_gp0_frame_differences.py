#!/usr/bin/env python3
"""Stage529 bounded, ROM-free VRAM difference diagnostics.

Owner supplies independently obtained 1024x512 u16le initial VRAM,
detached Player VRAM and experimental-model VRAM. Returns counts, never
images, raw game bytes, palette data, game identifiers or source hashes.
Derived geometric statistics themselves must remain owner-private.
This code does not authenticate the screenshot or original game.
"""
from collections import Counter

VRAM_W, VRAM_H = 1024, 512
VRAM_BYTES = VRAM_W * VRAM_H * 2
MAX_AREA = 512 * 512


def classify_vram_differences(initial, observed, modeled, *, roi,
                              shifts=(-2, -1, 0, 1, 2)):
    """Bounded diagnostics for a source-independent, explicit VRAM ROI.

    Shift checks are heuristics, NOT evidence of UV phase correctness.
    """
    sources=(initial,observed,modeled)
    if any(type(z) is not bytes or len(z)!=VRAM_BYTES for z in sources):
        raise ValueError("requires three separate exact-size immutable 1MiB u16le buffers")
    if (type(roi) is not tuple or len(roi)!=4 or
            any(type(t) is not int for t in roi)):
        raise ValueError("ROI must be explicit integer (x,y,width,height) tuple")
    x0,y0,width,height=roi
    if (width<1 or height<1 or width*height>MAX_AREA or
            x0<2 or y0<2 or x0+width>VRAM_W-2 or y0+height>VRAM_H-2):
        raise ValueError("ROI outside strict VRAM or ±2 shift-safe bounds")
    if shifts!=(-2,-1,0,1,2):
        raise ValueError("fixed bounded ±2 offset schedule required")
    a,b,c=(memoryview(z).cast("H") for z in sources)
    categories=Counter()
    channel_absolute_error=[0,0,0]
    changed_from_initial=0
    source_nonzero=0
    expected_nonzero=0
    modeled_nonzero=0
    rows=set()
    changed_tiles=Counter()
    total=width*height
    for y in range(y0,y0+height):
        for x in range(x0,x0+width):
            index=y*VRAM_W+x
            old,reference,candidate=a[index],b[index],c[index]
            source_nonzero+=old!=0
            expected_nonzero+=reference!=0
            modeled_nonzero+=candidate!=0
            changed_from_initial+=reference!=old
            if reference==candidate:
                categories["equal"]+=1
                continue
            rows.add(y)
            changed_tiles[((x-x0)//32,(y-y0)//32)]+=1
            if reference==0 and candidate!=0:
                categories["model_nonzero_observed_zero"]+=1
            elif candidate==0 and reference!=0:
                categories["model_zero_observed_nonzero"]+=1
            else:
                categories["different_nonzero_colors"]+=1
            for i in range(3):
                channel_absolute_error[i]+=abs(
                    ((reference>>(i*5))&31)-((candidate>>(i*5))&31))
            if (reference&0x7fff)==(candidate&0x7fff):
                categories["high_bit_only_mismatch"]+=1
    mismatch_count=total-categories["equal"]
    offset_candidates=[]
    for dy in shifts:
        for dx in shifts:
            mism=0
            for y in range(y0,y0+height):
                oldbase=y*VRAM_W
                newbase=(y+dy)*VRAM_W+dx
                for x in range(x0,x0+width):
                    mism+=b[oldbase+x]!=c[newbase+x]
            offset_candidates.append((mism,dx,dy))
    offset_candidates.sort()
    return {
        "kind":"WILD_ARMS_STAGE529_PRIVATE_BOUNDED_VRAM_DISCREPANCY",
        "schema":1,
        "roi_xywh":[x0,y0,width,height],
        "roi_u16_words_compared":total,
        "authentic_observed_words_different_from_initial":changed_from_initial,
        "observed_nonzero_u16_words":expected_nonzero,
        "modeled_nonzero_u16_words":modeled_nonzero,
        "initial_nonzero_u16_words":source_nonzero,
        "observed_vs_modeled_u16_mismatches":mismatch_count,
        "category_counts":dict(sorted(categories.items())),
        "rgb555_channel_absolute_error_sums":channel_absolute_error,
        "rows_with_mismatches":len(rows),
        "distinct_32x32_mismatch_tiles":len(changed_tiles),
        "best_five_bounded_shift_candidates":[
            {"dx":dx,"dy":dy,"mismatches":count}
            for count,dx,dy in offset_candidates[:5]],
        "pixel_arrays_and_game_content_never_serialized":True,
        "shift_candidates_are_heuristics_not_uv_proof":True,
        "capture_and_scene_origin_not_authenticated_by_classifier":True,
    }
