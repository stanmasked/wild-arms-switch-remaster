#!/usr/bin/env python3
"""Owner-private CONDITIONAL GP0(A0) -> GP0(80) copies -> first-UV lineage.

A separate, more permissive origin graph than Stage443's *direct A0*
writer proof. Each 16-bit word retains original A0 packet index and
original destination word address over NONOVERLAPPING GP0(80) copies.
A source-run candidate qualifies only if the entire contiguous source
run survives, with consecutively indexed original A0 words.

Unknown pre-trace VRAM, rasterized GPU writes, texture caches, CLUT
sampling and completeness/authenticity of original GP0 capture are
NOT resolved. Only synthetic bytes and metadata are in public tests.
"""
from array import array
from audit_private_a0_draw_uv_lineage import (
    PrivateA0DrawLineage, VRAM_WIDTH, VRAM_HEIGHT, VRAM_WORD_COUNT,
    MAX_RUN_REPORTS_PER_DRAW,
)

UNKNOWN = -1
MAX_PACKETS = 20000


class PrivateA0CopyLineage(PrivateA0DrawLineage):
    """Keep an independent transitive origin even when direct writer is lost."""
    def __init__(self):
        super().__init__()
        self.origin_packet = array("i", [UNKNOWN]) * VRAM_WORD_COUNT
        self.origin_address = array("i", [UNKNOWN]) * VRAM_WORD_COUNT
        self.copy_hops = array("i", [UNKNOWN]) * VRAM_WORD_COUNT

    def record_a0(self, packet_index, x, y, width, height, match_report):
        super().record_a0(packet_index, x, y, width, height, match_report)
        for row in range(y, y + height):
            left = row * VRAM_WIDTH + x
            right = left + width
            self.origin_packet[left:right] = array("i", [packet_index])*width
            self.origin_address[left:right] = array("i", range(left, right))
            self.copy_hops[left:right] = array("i", [0])*width

    def copy_vram(self, source_x, source_y, dest_x, dest_y, width, height):
        """Snapshot origins before copying; original A0 authorship stays indirect.

        The caller's Stage437 GP0(80) decoder also validates no wrapping,
        malformed packets and source/destination overlap.
        """
        values = (source_x, source_y, dest_x, dest_y, width, height)
        if (any(type(v) is not int for v in values) or
                width <= 0 or height <= 0 or
                source_x < 0 or dest_x < 0 or source_y < 0 or dest_y < 0 or
                source_x + width > VRAM_WIDTH or dest_x + width > VRAM_WIDTH or
                source_y + height > VRAM_HEIGHT or dest_y + height > VRAM_HEIGHT):
            raise ValueError("invalid transitive GP0(80) copy geometry")
        if not (source_x + width <= dest_x or dest_x + width <= source_x or
                source_y + height <= dest_y or dest_y + height <= source_y):
            raise ValueError("overlapping transitive GP0(80) copy unsupported")
        snapshots = []
        for row in range(height):
            left = (source_y + row) * VRAM_WIDTH + source_x
            right = left + width
            snapshots.append((
                self.origin_packet[left:right],
                self.origin_address[left:right],
                self.copy_hops[left:right],
            ))
        for row, (packets, addresses, hops) in enumerate(snapshots):
            left = (dest_y + row) * VRAM_WIDTH + dest_x
            right = left + width
            self.origin_packet[left:right] = packets
            self.origin_address[left:right] = addresses
            self.copy_hops[left:right] = array(
                "i", (hop + 1 if hop >= 0 and packets[i] >= 0 else UNKNOWN
                      for i, hop in enumerate(hops)))
        # Stage443's *direct* writer remains intentionally invalidated.
        self.invalidate_vram_copy_destination(dest_x, dest_y, width, height)

    def clear_fill_origin(self, x, y, width, height):
        """Remove A0 origin claims for pixels overwritten by GPU fill."""
        self.invalidate_vram_copy_destination(x,y,width,height)
        for row in range(y,y+height):
            left=row*VRAM_WIDTH+x
            right=left+width
            self.origin_packet[left:right]=array("i",[UNKNOWN])*width
            self.origin_address[left:right]=array("i",[UNKNOWN])*width
            self.copy_hops[left:right]=array("i",[UNKNOWN])*width

    def inspect_copy_lineage(self, x, y, draw_epoch, word_epochs,
                             *, max_samples=MAX_RUN_REPORTS_PER_DRAW):
        """Cover the current UV with an entire, still-consecutive A0 source run."""
        if (type(x) is not int or type(y) is not int or
                not 0 <= x < VRAM_WIDTH or not 0 <= y < VRAM_HEIGHT or
                type(draw_epoch) is not int or draw_epoch < 0 or
                len(word_epochs) != VRAM_WORD_COUNT or
                type(max_samples) is not int or
                not 1 <= max_samples <= MAX_RUN_REPORTS_PER_DRAW):
            raise ValueError("invalid first-UV copy-lineage query")
        destination = y * VRAM_WIDTH + x
        packet = self.origin_packet[destination]
        original_address = self.origin_address[destination]
        hops = self.copy_hops[destination]
        result = {
            "status": "NO_KNOWN_A0_ORIGIN_FOR_FIRST_UV",
            "first_uv_x_words": x,
            "first_uv_y": y,
            "source_a0_packet_index": packet if packet >= 0 else None,
            "source_a0_word_x": original_address % VRAM_WIDTH
                if original_address >= 0 else None,
            "source_a0_word_y": original_address // VRAM_WIDTH
                if original_address >= 0 else None,
            "first_uv_copy_hops": hops if hops >= 0 else None,
            "candidate_original_a0_runs_covering_uv": 0,
            "whole_run_remains_contiguous_from_same_a0": 0,
            "whole_run_fresh_since_previous_draw": 0,
            "reported_run_count": 0,
            "sample_truncated_or_unknown": False,
            "run_samples": [],
            "interpretation": {
                "copy_lineage_is_conditional_on_exact_ordered_packet_trace": True,
                "direct_a0_proof_kept_separate_from_transitive_copy_origin": True,
                "all_words_in_source_run_must_survive_as_consecutive_origins": True,
                "gpu_drawn_pixels_and_texture_clut_cache_not_modeled": True,
                "matching_first_uv_does_not_prove_visible_rasterized_pixel": True,
                "original_gpu_trace_and_map_identity_unverified": True,
                "no_raw_texture_color_vram_or_gp0_data_exported": True,
            },
        }
        if packet < 0 or original_address < 0:
            return result
        for run in self.matched_runs.get(packet, ()):
            source_start = run["y"] * VRAM_WIDTH + run["start_x"]
            width = run["word_count"]
            if not source_start <= original_address < source_start + width:
                continue
            result["candidate_original_a0_runs_covering_uv"] += 1
            offset = original_address - source_start
            start_x = x - offset
            if start_x < 0 or start_x + width > VRAM_WIDTH:
                continue
            start = y * VRAM_WIDTH + start_x
            end = start + width
            # All words must retain the original packet and exact
            # ascending ORIGINAL VRAM addresses. Mixed copies, swapped
            # subruns, overwritten words or wrapped rows are rejected.
            contiguous = all(
                self.origin_packet[start + j] == packet and
                self.origin_address[start + j] == source_start + j
                for j in range(width))
            if not contiguous:
                continue
            result["whole_run_remains_contiguous_from_same_a0"] += 1
            fresh = all(epoch == draw_epoch for epoch in word_epochs[start:end])
            result["whole_run_fresh_since_previous_draw"] += int(fresh)
            if len(result["run_samples"]) < max_samples:
                run_hops = self.copy_hops[start:end]
                result["run_samples"].append({
                    "source_a0_packet_index": packet,
                    "candidate_stream_ordinal": run["stream_ordinal"],
                    "graphics_region_index": run["region_index"],
                    "source_offset_bytes": run["source_offset"],
                    "matched_byte_span": run["span"],
                    "original_a0_start_x_words": run["start_x"],
                    "original_a0_y": run["y"],
                    "current_run_start_x_words": start_x,
                    "current_run_y": y,
                    "minimum_copy_hops": min(run_hops),
                    "maximum_copy_hops": max(run_hops),
                    "run_origin_consecutive_and_not_overwritten": True,
                    "all_run_words_refreshed_since_previous_draw": fresh,
                })
        result["reported_run_count"] = len(result["run_samples"])
        result["sample_truncated_or_unknown"] = (
            packet in self.truncated or
            result["whole_run_remains_contiguous_from_same_a0"] >
                len(result["run_samples"]))
        if result["whole_run_remains_contiguous_from_same_a0"]:
            if result["whole_run_fresh_since_previous_draw"]:
                result["status"] = "CONDITIONAL_FRESH_TRANSITIVE_SOURCE_RUN"
            else:
                result["status"] = "TRANSITIVE_SOURCE_RUN_WITH_UNVERIFIED_FRESHNESS"
        elif result["sample_truncated_or_unknown"]:
            result["status"] = "SOURCE_MATCH_SAMPLES_TRUNCATED"
        elif result["candidate_original_a0_runs_covering_uv"]:
            result["status"] = "PARTIAL_OR_REORDERED_SOURCE_RUN_NOT_PROVEN"
        else:
            result["status"] = "A0_ORIGIN_WITH_NO_MATCHED_SOURCE_RUN_AT_UV"
        return result
