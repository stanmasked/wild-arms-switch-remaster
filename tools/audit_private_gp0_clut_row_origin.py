#!/usr/bin/env python3
"""PRIVATE conditional CLUT row lineage next to first-UV texture lineage.

Verify the complete 16-halfword CLUT row at the moment of a modeled 4bpp
draw: exact candidate source-byte equality, per-word A0/copy origin,
contiguous original A0 addresses, and last-draw transfer freshness.
The selected entry follows the modeled first-UV nibble. No GPU
rasterization/cache sampling, screenshot or original trace attestation.
"""
import hashlib

from audit_private_a0_transitive_copy_lineage import PrivateA0CopyLineage

VRAM_WORDS = 1024 * 512
VRAM_BYTES = VRAM_WORDS * 2
CLUT_WORDS = 16
MAX_PALETTE_CANDIDATES = 256
FIRST_UV_AVAILABLE = "MODELED_FIRST_DECLARED_UV_WITH_DISABLED_TEXTURE_WINDOW"


def inspect_private_clut_row_lineage(
        vram, lineage, word_epochs, draw_epoch, texture_probe, matching_rows):
    """Check the modeled 4bpp texture/CLUT pair without exporting source words."""
    if (type(vram) not in (bytes, bytearray) or len(vram) != VRAM_BYTES
            or not isinstance(lineage, PrivateA0CopyLineage)
            or len(word_epochs) != VRAM_WORDS
            or type(draw_epoch) is not int or draw_epoch < 0
            or type(texture_probe) is not dict
            or type(matching_rows) is not list
            or len(matching_rows) > MAX_PALETTE_CANDIDATES
            or any(type(ref) is not dict
                   or set(ref) != {"candidate_bank_index", "candidate_row_index"}
                   or type(ref["candidate_bank_index"]) is not int
                   or type(ref["candidate_row_index"]) is not int
                   for ref in matching_rows)):
        raise ValueError("invalid private modeled CLUT row lineage inputs")

    interpretation = {
        "only_modeled_pre_draw_vram_and_complete_declared_first_uv": True,
        "candidate_row_equality_not_proof_of_gpu_sampled_clut": True,
        "texture_and_clut_provenances_tracked_separately": True,
        "a0_origin_may_be_carried_across_gpu_80_copy_hops": True,
        "gpu_drawn_pixels_and_texture_clut_caches_unmodeled": True,
        "original_scene_gp0_trace_and_camera_not_authenticated": True,
        "zero_index_not_assumed_transparent_or_opaque": True,
        "no_original_source_vram_palette_or_pixel_words_exported": True,
    }
    if texture_probe.get("status") != FIRST_UV_AVAILABLE:
        return {
            "status": "FIRST_UV_UNAVAILABLE_CLUT_ENTRY_NOT_EVALUATED",
            "matching_source_palette_row_count": len(matching_rows),
            "no_clut_entry_provenance_claim": True,
            "interpretation": interpretation,
        }

    fields = ("first_uv_texture_word_x_words", "first_uv_texture_word_y",
              "first_uv_clut_row_x_words", "first_uv_clut_row_y")
    if any(type(texture_probe.get(name)) is not int for name in fields):
        raise ValueError("first UV source coordinates missing from available probe")
    texture_x = texture_probe[fields[0]]
    texture_y = texture_probe[fields[1]]
    clut_x = texture_probe[fields[2]]
    clut_y = texture_probe[fields[3]]
    if (not 0 <= texture_x < 1024 or not 0 <= texture_y < 512
            or not 0 <= clut_x <= 1008 or clut_x % 16 != 0
            or not 0 <= clut_y < 512):
        raise ValueError("invalid declared 4bpp texture/CLUT location")

    texture_address = texture_y * 1024 + texture_x
    row_address = clut_y * 1024 + clut_x
    texture_word = int.from_bytes(
        vram[texture_address*2:texture_address*2+2], "little")
    # The Stage439 modeled UV report does not carry the nibble position
    # directly. Include Stage439's original first-UV U coordinate in
    # its probe before using this method; otherwise reject.
    nibble = texture_probe.get("first_uv_nibble_within_u16")
    if type(nibble) is not int or not 0 <= nibble <= 3:
        raise ValueError("first UV nibble was not independently recorded")
    selected_index = (texture_word >> (4*nibble)) & 15
    selected_address = row_address + selected_index
    selected_word = bytes(vram[selected_address*2:selected_address*2+2])
    expected_hash = texture_probe.get("selected_palette_halfword_sha256")
    if (type(expected_hash) is not str
            or expected_hash != hashlib.sha256(selected_word).hexdigest()):
        raise ValueError("selected CLUT word differs from first-UV sample")
    row = bytes(vram[row_address*2:(row_address+CLUT_WORDS)*2])
    packet_ids = lineage.origin_packet[row_address:row_address+CLUT_WORDS]
    original_addresses = lineage.origin_address[row_address:row_address+CLUT_WORDS]
    hops = lineage.copy_hops[row_address:row_address+CLUT_WORDS]
    coherent = (
        packet_ids[0] >= 0
        and all(v == packet_ids[0] for v in packet_ids)
        and original_addresses[0] >= 0
        and original_addresses[0] % 1024 <= 1008
        and all(a == original_addresses[0]+i
                for i,a in enumerate(original_addresses))
        and all(h >= 0 for h in hops)
    )
    row_fresh = all(
        word_epochs[row_address+i] == draw_epoch for i in range(CLUT_WORDS))
    texture_packet = lineage.origin_packet[texture_address]
    selected_packet = lineage.origin_packet[selected_address]
    selected_fresh = word_epochs[selected_address] == draw_epoch
    texture_fresh = word_epochs[texture_address] == draw_epoch
    selected_origin_known = selected_packet >= 0

    if not matching_rows:
        status = "NO_DECODED_SOURCE_PALETTE_ROW_MATCH"
    elif coherent and row_fresh:
        status = "CONDITIONAL_FRESH_CANDIDATE_CLUT_ROW_ORIGIN"
    elif coherent:
        status = "CANDIDATE_CLUT_ROW_ORIGIN_WITH_UNVERIFIED_FRESHNESS"
    elif selected_origin_known:
        status = "CANDIDATE_ROW_WITH_PARTIAL_OR_MIXED_A0_ORIGINS"
    else:
        status = "CANDIDATE_ROW_WITHOUT_KNOWN_A0_ORIGIN"

    return {
        "status": status,
        "clut_x_words": clut_x,
        "clut_y": clut_y,
        "selected_clut_word_x_words": clut_x + selected_index,
        "selected_clut_word_y": clut_y,
        "candidate_palette_row_sha256": hashlib.sha256(row).hexdigest(),
        "matching_source_palette_row_count": len(matching_rows),
        "matching_source_palette_rows": matching_rows,
        "selected_clut_origin_a0_packet_index":
            selected_packet if selected_origin_known else None,
        "texture_halfword_origin_a0_packet_index":
            texture_packet if texture_packet >= 0 else None,
        "texture_and_clut_selected_halfwords_share_original_a0_packet":
            (selected_origin_known and texture_packet >= 0 and
             selected_packet == texture_packet),
        "selected_clut_copy_hops":
            hops[selected_index] if selected_origin_known else None,
        "entire_clut_row_has_contiguous_same_a0_origin": coherent,
        "entire_clut_row_fresh_since_last_draw": row_fresh,
        "selected_clut_halfword_fresh_since_last_draw": selected_fresh,
        "texture_halfword_fresh_since_last_draw": texture_fresh,
        "both_selected_palette_and_texture_fresh_since_last_draw":
            bool(selected_fresh and texture_fresh),
        "all_clut_row_copy_hops_min": min(hops) if coherent else None,
        "all_clut_row_copy_hops_max": max(hops) if coherent else None,
        "interpretation": interpretation,
    }
