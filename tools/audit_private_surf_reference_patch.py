#!/usr/bin/env python3
"""PRIVATE PS1 Surf Village ROI and optional candidate-to-frame comparison.

Stage432 screenshot provenance is checked before extracting a reference.
The optional candidate MUST already be a rendered image at EXACT reference
screen pixel geometry; texture atlases are not valid drop-in candidates.
No scale, shift, resampling, color correction, or alpha compositing.
Source disc, screenshot, VRAM, original tiles and derived PNGs stay private.
"""
import argparse
from io import BytesIO
import hashlib
import json
from pathlib import Path
import struct

from capture_private_pcsx_frame_witness import (
    _publish_four_no_overwrite, verify_private_frame_witness)
from capture_private_pcsx_redux_vram import _validate_basename

MAX_ROI_PIXELS = 1024 * 1024


def validate_roi(x, y, width, height, frame_width, frame_height):
    values = (x, y, width, height, frame_width, frame_height)
    if any(type(number) is not int for number in values):
        raise ValueError("reference ROI values must be plain integers")
    if (x < 0 or y < 0 or width <= 0 or height <= 0 or
            frame_width <= 0 or frame_height <= 0 or
            width * height > MAX_ROI_PIXELS or
            x + width > frame_width or y + height > frame_height):
        raise ValueError("reference ROI outside original captured framebuffer")
    return (x, y, x + width, y + height)


def compare_opaque_rgb(reference, candidate, width, height, *, threshold=0):
    """Pure-Python numerical evidence; returns metadata and unsigned RGB diff.

    Both inputs must be RGB bytes, in the same original SCREEN coordinates.
    This does not authenticate scene/CLUT identity or assign source textures.
    """
    if (any(type(item) is not int or item <= 0 for item in (width, height))
            or width * height > MAX_ROI_PIXELS or
            type(threshold) is not int or not 0 <= threshold <= 255):
        raise ValueError("invalid pixel comparison dimensions or threshold")
    expected = width * height * 3
    if (not isinstance(reference, bytes) or not isinstance(candidate, bytes)
            or len(reference) != expected or len(candidate) != expected):
        raise ValueError("RGB buffer length does not match unscaled reference ROI")
    difference = bytearray(expected)
    mismatched_pixels = 0
    exactly_equal_pixels = 0
    sum_abs = 0
    sum_square = 0
    maximum = 0
    bounds = [width, height, -1, -1]
    for pixel in range(width * height):
        ix = pixel * 3
        a, b, c = (
            abs(reference[ix + channel] - candidate[ix + channel])
            for channel in range(3))
        difference[ix:ix+3] = bytes((a, b, c))
        local_max = max(a, b, c)
        sum_abs += a + b + c
        sum_square += a*a + b*b + c*c
        maximum = max(maximum, local_max)
        if local_max == 0:
            exactly_equal_pixels += 1
        if local_max > threshold:
            mismatched_pixels += 1
            x, y = pixel % width, pixel // width
            bounds = [min(x, bounds[0]), min(y, bounds[1]),
                      max(x, bounds[2]), max(y, bounds[3])]
    pixels = width * height
    return ({
        "pixel_count": pixels,
        "rgb_channel_count": expected,
        "absolute_error_threshold_per_channel": threshold,
        "exact_matching_pixel_count": exactly_equal_pixels,
        "threshold_exceeding_pixel_count": mismatched_pixels,
        "threshold_exceeding_pixel_fraction": round(mismatched_pixels / pixels, 8),
        "mean_absolute_rgb_channel_error": round(sum_abs / expected, 8),
        "root_mean_square_rgb_channel_error": round(
            (sum_square / expected)**0.5, 8),
        "max_absolute_rgb_channel_error": maximum,
        "threshold_exceeding_bounds_xyxy_inclusive": bounds
            if mismatched_pixels else None,
        "reference_and_candidate_same_dimensions": True,
        "no_resampling_or_auto_alignment": True,
    }, bytes(difference))


def _opaque_rgb_png(raw_png):
    """Decode exactly the immutable byte sequence whose SHA-256 was checked."""
    from PIL import Image
    if not isinstance(raw_png, bytes) or not 0 < len(raw_png) <= 16*1024*1024:
        raise ValueError("private PNG must be a bounded immutable byte string")
    with Image.open(BytesIO(raw_png)) as picture:
        if picture.format != "PNG":
            raise ValueError("frame comparison input must be actual PNG")
        if (picture.width < 1 or picture.height < 1 or
                picture.width * picture.height > 4096*4096):
            raise ValueError("invalid or excessive PNG dimensions")
        rgba = picture.convert("RGBA")
        if rgba.getchannel("A").getextrema() != (255, 255):
            raise ValueError("transparent pixels not supported for exact RGB comparison")
        return picture.size, rgba.convert("RGB")


def _png_bytes(image):
    stream = BytesIO()
    image.save(stream, format="PNG", optimize=True)
    return stream.getvalue()


def create_private_surf_reference_patch(
        witness_directory, witness_basename, private_output_directory,
        patch_basename, *, x, y, width, height,
        candidate_png=None, mismatch_threshold=0):
    """Generate private reference ROI, optional 3-panel comparison and hashes."""
    _validate_basename(witness_basename)
    _validate_basename(patch_basename)
    witness_directory = Path(witness_directory)
    output_directory = Path(private_output_directory)
    if not output_directory.is_dir():
        raise ValueError("private output directory must already exist")
    # Provenance gate checks stage432 VRAM, CD-info and screenshot bytes.
    verified = verify_private_frame_witness(witness_directory,
                                            basename=witness_basename)
    screen_path = witness_directory / (witness_basename + ".screen.png")
    original_screen_bytes = screen_path.read_bytes()
    if hashlib.sha256(original_screen_bytes).hexdigest() != verified["screen_sha256"]:
        raise ValueError("original screenshot changed after witness verification")
    frame_size, screenshot = _opaque_rgb_png(original_screen_bytes)
    roi = validate_roi(x, y, width, height, *frame_size)
    patch = screenshot.crop(roi)
    reference_rgb = patch.tobytes()
    source_hash = hashlib.sha256(reference_rgb).hexdigest()
    outputs = {patch_basename + ".reference.png": _png_bytes(patch)}
    result = {
        "schema": 1,
        "kind": "WA1_PRIVATE_SURF_REFERENCE_FRAME_PATCH",
        "reference_witness_basename": witness_basename,
        "reference_witness_vram_sha256": verified["vram_sha256"],
        "reference_witness_screen_sha256": verified["screen_sha256"],
        "reference_witness_disc_info_sha256": verified["cd_info_sha256"],
        "screenshot_size": {"width": frame_size[0], "height": frame_size[1]},
        "reference_roi_xywh": {"x": x, "y": y, "width": width, "height": height},
        "reference_rgb_sha256": source_hash,
        "reference_png_filename": patch_basename + ".reference.png",
        "reference_png_sha256": hashlib.sha256(
            outputs[patch_basename + ".reference.png"]).hexdigest(),
        "candidate_supplied": candidate_png is not None,
        "comparison": None,
        "interpretation": {
            "original_screenshot_bytes_verified_against_stage432_witness": True,
            "frame_map_identity_not_authenticated_by_snapshot": True,
            "roi_semantic_location_selected_by_operator_not_machine_verified": True,
            "no_source_atlas_to_field_tile_mapping_proven": True,
            "no_gpu_draw_time_clut_or_stp_assignment_proven": True,
            "no_auto_scaling_or_color_correction": True,
            "all_png_and_evidence_json_remain_owner_private": True,
            "not_an_automatic_reference_certification": True,
        },
    }
    if candidate_png is not None:
        candidate_png = Path(candidate_png)
        if candidate_png.is_symlink() or not candidate_png.is_file():
            raise ValueError("candidate must be an existing, non-symlink PNG file")
        candidate_png_bytes = candidate_png.read_bytes()
        candidate_size, candidate = _opaque_rgb_png(candidate_png_bytes)
        if candidate_size != (width, height):
            raise ValueError("candidate must match ROI dimensions exactly; resampling forbidden")
        metrics, difference_rgb = compare_opaque_rgb(
            reference_rgb, candidate.tobytes(), width, height,
            threshold=mismatch_threshold)
        result["comparison"] = {
            **metrics,
            "candidate_png_sha256": hashlib.sha256(
                candidate_png_bytes).hexdigest(),
            "candidate_rgb_sha256": hashlib.sha256(candidate.tobytes()).hexdigest(),
            "candidate_filename_only": candidate_png.name,
            "image_metric_is_not_proof_of_original_palette_assignment": True,
        }
        from PIL import Image
        diff = Image.frombytes("RGB", (width, height), difference_rgb)
        gap = 10
        panel = Image.new("RGB", (width*3 + gap*2, height), (28, 28, 28))
        panel.paste(patch, (0,0))
        panel.paste(candidate, (width + gap,0))
        panel.paste(diff, (width*2 + gap*2,0))
        outputs[patch_basename + ".comparison.png"] = _png_bytes(panel)
        result["comparison"]["comparison_png_filename"] = patch_basename + ".comparison.png"
        result["comparison"]["comparison_png_sha256"] = hashlib.sha256(
            outputs[patch_basename + ".comparison.png"]).hexdigest()
        result["comparison"]["panel_order"] = [
            "reference_roi", "candidate_exact_frame_geometry", "absolute_rgb_difference"]
    json_file = patch_basename + ".evidence.json"
    outputs[json_file] = (json.dumps(result, indent=2, sort_keys=True)+"\n").encode()
    _publish_four_no_overwrite(output_directory, outputs)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_witness_directory", type=Path)
    parser.add_argument("witness_basename")
    parser.add_argument("private_output_directory", type=Path)
    parser.add_argument("patch_basename")
    parser.add_argument("--x", type=int, required=True)
    parser.add_argument("--y", type=int, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--candidate-png", type=Path)
    parser.add_argument("--threshold", type=int, default=0)
    args = parser.parse_args()
    result = create_private_surf_reference_patch(
        args.private_witness_directory, args.witness_basename,
        args.private_output_directory, args.patch_basename,
        x=args.x, y=args.y, width=args.width, height=args.height,
        candidate_png=args.candidate_png, mismatch_threshold=args.threshold)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__=="__main__":
    main()
