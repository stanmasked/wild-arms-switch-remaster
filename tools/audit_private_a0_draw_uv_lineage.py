#!/usr/bin/env python3
"""ROM-free, PRIVATE conditional provenance of modeled A0 upload -> GP0 first UV.

For each modeled VRAM halfword remember the packet index of its most recent
A0 write. GP0(80) destinations are explicitly marked UNKNOWN as this
stage does not attribute copied data to an A0 packet. GPU draw epochs
invalidate assumptions about pixel values without rasterization.

A qualifying A0 match must have its own packet-indexed decoded-source run
cover the queried first-UV word. Report only coordinates, stream ordinals,
source offsets, aggregate counts and uncertainty. No raw game assets.
"""
from array import array

VRAM_WIDTH = 1024
VRAM_HEIGHT = 512
VRAM_WORD_COUNT = VRAM_WIDTH * VRAM_HEIGHT
MAX_RUN_REPORTS_PER_DRAW = 16


class PrivateA0DrawLineage:
    """Track direct A0 writer by word, not mere memory equality."""
    def __init__(self):
        self.writer = array("i", [-1]) * VRAM_WORD_COUNT
        self.matched_runs = {}
        self.truncated = set()

    def record_a0(self, packet_index, x, y, width, height, match_report):
        if (type(packet_index) is not int or not 0 <= packet_index <= 20000
                or any(type(v) is not int for v in (x,y,width,height))
                or width <= 0 or height <= 0 or x < 0 or y < 0
                or x+width > VRAM_WIDTH or y+height > VRAM_HEIGHT
                or type(match_report) is not dict
                or type(match_report.get("run_samples")) is not list
                or type(match_report.get("sample_truncated")) is not bool):
            raise ValueError("invalid A0 provenance packet or geometry")
        for row in range(y,y+height):
            start=row*VRAM_WIDTH+x
            self.writer[start:start+width]=array("i",[packet_index])*width
        runs=[]
        for item in match_report["run_samples"]:
            if type(item) is not dict:
                raise ValueError("invalid A0 source match sample")
            destination_x=item.get("a0_destination_x_words")
            destination_y=item.get("a0_destination_y")
            span=item.get("matched_byte_span")
            region=item.get("graphics_region_index")
            source_offset=item.get("source_offset_bytes")
            source_ordinal=item.get("candidate_stream_ordinal")
            if (any(type(v) is not int for v in (
                    destination_x,destination_y,span,region,source_offset,source_ordinal))
                    or span <= 0 or span%2 or
                    destination_x < x or destination_x+span//2 > x+width
                    or not y <= destination_y < y+height
                    or region < 0 or source_offset < 0 or source_ordinal < 0):
                raise ValueError("A0 source run outside its declared packet")
            runs.append({
                "start_x":destination_x,
                "y":destination_y,
                "word_count":span//2,
                "stream_ordinal":source_ordinal,
                "region_index":region,
                "source_offset":source_offset,
                "span":span,
            })
        self.matched_runs[packet_index]=runs
        if match_report["sample_truncated"]:
            self.truncated.add(packet_index)

    def invalidate_vram_copy_destination(self, x, y, width, height):
        """Conservatively lose DIRECT A0 attribution after GP0(80) blit."""
        if (any(type(v) is not int for v in (x,y,width,height))
                or x < 0 or y < 0 or width <= 0 or height <= 0
                or x+width > VRAM_WIDTH or y+height > VRAM_HEIGHT):
            raise ValueError("invalid GPU copy destination")
        for row in range(y,y+height):
            begin=row*VRAM_WIDTH+x
            self.writer[begin:begin+width]=array("i",[-1])*width

    def inspect(self, x, y, draw_epoch, word_epochs,
                *, max_samples=MAX_RUN_REPORTS_PER_DRAW):
        """Query provenance at first UV *before* this particular draw."""
        if (type(x) is not int or type(y) is not int or
                not 0 <= x < VRAM_WIDTH or not 0 <= y < VRAM_HEIGHT or
                type(draw_epoch) is not int or draw_epoch < 0 or
                len(word_epochs) != VRAM_WORD_COUNT or
                type(max_samples) is not int or
                not 1 <= max_samples <= MAX_RUN_REPORTS_PER_DRAW):
            raise ValueError("invalid draw first-UV or packet chronology")
        addr=y*VRAM_WIDTH+x
        packet_index=self.writer[addr]
        result={
            "first_uv_x_words":x,
            "first_uv_y":y,
            "last_direct_a0_writer_packet_index":
                packet_index if packet_index >= 0 else None,
            "candidate_a0_matched_runs_covering_uv":0,
            "whole_run_last_written_by_same_direct_a0_packet":0,
            "whole_run_refreshed_after_preceding_draw":0,
            "sample_truncated":False,
            "covering_runs":[],
            "interpretation":{
                "source_to_a0_packet_to_first_uv_link_is_conditional":True,
                "vram_copy_destinations_are_not_direct_a0_attributions":True,
                "gpu_drawn_pixels_and_texture_cache_unmodeled":True,
                "first_declared_uv_not_verified_visible_sample":True,
                "original_gpu_trace_origin_and_completeness_unverified":True,
                "no_original_texture_bytes_or_palette_words_exported":True,
            }
        }
        if packet_index < 0:
            result["status"]="NO_DIRECT_A0_WRITER_FOR_TEXTURE_WORD"
            return result
        runs=self.matched_runs.get(packet_index, ())
        for run in runs:
            if run["y"]!=y or not (
                    run["start_x"]<=x<run["start_x"]+run["word_count"]):
                continue
            result["candidate_a0_matched_runs_covering_uv"] += 1
            start=y*VRAM_WIDTH+run["start_x"]
            end=start+run["word_count"]
            all_from_packet=all(v==packet_index for v in self.writer[start:end])
            all_fresh=all_from_packet and all(
                v==draw_epoch for v in word_epochs[start:end])
            result["whole_run_last_written_by_same_direct_a0_packet"] += int(
                all_from_packet)
            result["whole_run_refreshed_after_preceding_draw"] += int(all_fresh)
            if len(result["covering_runs"])<max_samples:
                result["covering_runs"].append({
                    "a0_packet_index":packet_index,
                    "candidate_stream_ordinal":run["stream_ordinal"],
                    "graphics_region_index":run["region_index"],
                    "source_offset_bytes":run["source_offset"],
                    "matched_byte_span":run["span"],
                    "run_start_x_words":run["start_x"],
                    "run_y":y,
                    "all_run_words_still_from_this_direct_a0":all_from_packet,
                    "all_run_words_refreshed_since_previous_draw":all_fresh,
                })
        result["sample_truncated"] = (
            result["candidate_a0_matched_runs_covering_uv"] > len(result["covering_runs"])
            or packet_index in self.truncated)
        if result["candidate_a0_matched_runs_covering_uv"]:
            if result["whole_run_refreshed_after_preceding_draw"]:
                result["status"]="CONDITIONAL_FRESH_A0_SOURCE_RUN_COVERS_FIRST_UV"
            else:
                result["status"]="A0_SOURCE_RUN_COVERS_UV_BUT_FRESHNESS_UNVERIFIED"
        elif packet_index in self.truncated:
            result["status"]="A0_SOURCE_MATCH_SAMPLES_TRUNCATED_CANNOT_EXCLUDE_LINK"
        else:
            result["status"]="A0_WRITER_WITHOUT_MATCHED_SOURCE_RUN_AT_UV"
        return result
