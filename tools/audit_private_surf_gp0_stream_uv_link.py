#!/usr/bin/env python3
"""OWNER-PRIVATE Surf Village source-run coverage of ONE modeled GP0 UV word.

Stage440 reports long decoded-CDSTG stream occurrences anywhere in VRAM.
Stage441 asks if such a run *covers the first declared 4bpp UV word*
at the instant of a Stage439 modeled draw, not just somewhere on a
postframe snapshot. This neither rasterizes polygons nor proves the
source was uploaded or sampled by the original GPU.
"""
from collections import defaultdict
import hashlib
from audit_private_surf_stream_vram_runs import (
    BLOCK_BYTES, VRAM_BYTES, VRAM_GRID_BYTES, VRAM_ROW_BYTES,
    MAX_ANCHOR_FANOUT, MAX_DECODED_BYTES, MAX_STREAMS,
    _qualifies_anchor,
)

MAX_SOURCE_MATCH_SAMPLES = 16
VRAM_WIDTH_WORDS = 1024
VRAM_HEIGHT = 512


def prepare_private_stream_index(streams, *,
                                 minimum_distinct_bytes=12,
                                 minimum_nonzero_bytes=32):
    """Validate private decoded streams once, index high-information 64B blocks."""
    if (type(streams) is not list or len(streams) > MAX_STREAMS
            or type(minimum_distinct_bytes) is not int
            or not 2 <= minimum_distinct_bytes <= BLOCK_BYTES
            or type(minimum_nonzero_bytes) is not int
            or not 1 <= minimum_nonzero_bytes <= BLOCK_BYTES):
        raise ValueError("invalid decoded-stream index geometry")
    index = defaultdict(list)
    data = []
    skipped = 0
    for ordinal, record in enumerate(streams):
        if type(record) is not dict:
            raise ValueError("decoded stream metadata must be a dict")
        raw = record.get("decoded")
        region = record.get("graphics_region_index")
        if (type(raw) is not bytes or
                not BLOCK_BYTES <= len(raw) <= MAX_DECODED_BYTES or
                len(raw) % BLOCK_BYTES != 0 or
                type(region) is not int or region < 0):
            raise ValueError("decoded stream is not a valid bounded graphics source")
        data.append((raw,region))
        for offset in range(0,len(raw),BLOCK_BYTES):
            chunk=raw[offset:offset+BLOCK_BYTES]
            if not _qualifies_anchor(
                    chunk,minimum_distinct_bytes,minimum_nonzero_bytes):
                skipped+=1
                continue
            index[chunk].append((ordinal,offset))
    rejected=sum(len(refs) for refs in index.values()
                 if len(refs)>MAX_ANCHOR_FANOUT)
    eligible={block:refs for block,refs in index.items()
              if len(refs)<=MAX_ANCHOR_FANOUT}
    return {
        "source_streams":data,
        "eligible_anchor_index":eligible,
        "low_information_anchor_count":skipped,
        "high_fanout_anchor_count":rejected,
        "eligible_distinct_anchor_count":len(eligible),
    }


def match_first_uv_to_private_streams(
        index, modeled_vram, texture_x_words, texture_y,
        word_epoch, current_draw_epoch, *,
        minimum_contiguous_blocks=3, max_match_samples=8):
    """Find byte-exact row runs containing the single 16-bit texture word.

    The same modeled VRAM state is passed by Stage439 *before this
    exact draw packet*. A run must start at a 16-word VRAM grid boundary,
    have >=N contiguous matching 64B chunks, and cover the queried UV.
    """
    if (type(modeled_vram) not in (bytes,bytearray) or
            len(modeled_vram)!=VRAM_BYTES or
            type(texture_x_words) is not int or
            not 0 <= texture_x_words < VRAM_WIDTH_WORDS or
            type(texture_y) is not int or
            not 0 <= texture_y < VRAM_HEIGHT or
            type(current_draw_epoch) is not int or current_draw_epoch < 0 or
            len(word_epoch)!=VRAM_WIDTH_WORDS*VRAM_HEIGHT or
            type(minimum_contiguous_blocks) is not int or
            not 2 <= minimum_contiguous_blocks <= 32 or
            type(max_match_samples) is not int or
            not 1 <= max_match_samples <= MAX_SOURCE_MATCH_SAMPLES or
            type(index) is not dict or
            type(index.get("eligible_anchor_index")) is not dict or
            type(index.get("source_streams")) is not list):
        raise ValueError("invalid first-UV stream-coverage inputs")
    row_start=texture_y*VRAM_ROW_BYTES
    row=modeled_vram[row_start:row_start+VRAM_ROW_BYTES]
    focus_byte=texture_x_words*2
    results=[]
    total=0
    fully_fresh=0
    candidate_anchors=0
    for start in range(0, VRAM_ROW_BYTES-BLOCK_BYTES+1,
                       VRAM_GRID_BYTES):
        if start>focus_byte:
            break
        block=bytes(row[start:start+BLOCK_BYTES])
        candidates=index["eligible_anchor_index"].get(block,())
        for ordinal, source_offset in candidates:
            candidate_anchors+=1
            raw,region=index["source_streams"][ordinal]
            if source_offset>=BLOCK_BYTES and start>=BLOCK_BYTES:
                prior=raw[source_offset-BLOCK_BYTES:source_offset]
                if (prior in index["eligible_anchor_index"]
                        and prior==row[start-BLOCK_BYTES:start]):
                    # This is a continuation of an earlier eligible run.
                    continue
            length=0
            while (source_offset+(length+1)*BLOCK_BYTES<=len(raw)
                    and start+(length+1)*BLOCK_BYTES<=VRAM_ROW_BYTES
                    and raw[source_offset+length*BLOCK_BYTES:
                            source_offset+(length+1)*BLOCK_BYTES]
                    ==row[start+length*BLOCK_BYTES:
                          start+(length+1)*BLOCK_BYTES]):
                length+=1
            span=length*BLOCK_BYTES
            if length<minimum_contiguous_blocks or not (
                    start<=focus_byte and focus_byte+2<=start+span):
                continue
            total+=1
            offset_in_words=start//2
            end_in_words=(start+span)//2
            sample_word_ids=range(
                texture_y*VRAM_WIDTH_WORDS+offset_in_words,
                texture_y*VRAM_WIDTH_WORDS+end_in_words)
            every_written=all(word_epoch[addr]==current_draw_epoch
                              for addr in sample_word_ids)
            fully_fresh+=int(every_written)
            if len(results)<max_match_samples:
                original_slice=raw[source_offset:source_offset+span]
                results.append({
                    "candidate_stream_ordinal":ordinal,
                    "graphics_region_index":region,
                    "source_offset_bytes":source_offset,
                    "modeled_vram_run_start_x_words":start//2,
                    "modeled_vram_run_y":texture_y,
                    "first_uv_offset_within_run_bytes":focus_byte-start,
                    "matched_contiguous_64byte_blocks":length,
                    "matched_byte_span":span,
                    "run_sha256":hashlib.sha256(original_slice).hexdigest(),
                    "all_run_halfwords_explicitly_written_since_last_draw":
                        every_written,
                    "source_stream_geometry_and_provenance_unverified":True,
                })
    return {
        "status":"FIRST_UV_SOURCE_RUN_COVERAGE_SCANNED",
        "first_uv_x_words":texture_x_words,
        "first_uv_y":texture_y,
        "eligible_candidate_anchors_at_or_before_uv":candidate_anchors,
        "covering_byte_identical_run_count":total,
        "covering_runs_fully_refreshed_since_last_draw":fully_fresh,
        "reported_covering_run_count":len(results),
        "covering_run_samples_truncated":total>len(results),
        "covering_runs":results,
        "no_source_pixel_words_or_decoded_stream_bytes_exported":True,
        "matching_bytes_not_proof_of_gpu_upload_or_visible_texture":True,
        "source_to_texture_page_mapping_not_authenticated":True,
        "gpu_drawn_pixels_texture_cache_and_clut_state_unverified":True,
    }
