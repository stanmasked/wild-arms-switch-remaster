#!/usr/bin/env python3
"""PRIVATE, no-registration comparison of two verified PS1 field screenshots.

Two separately captured Stage432 witnesses provide screen-space evidence of
changes in one ROI. Unchanged pixels are only TEMPORALLY CONSISTENT between
these two observations; do not call them authenticated static map tiles.
No pixel values, screenshots or derived images are emitted to public CI.
"""
import argparse
from io import BytesIO
import hashlib
import json
from pathlib import Path

from audit_private_surf_reference_patch import (
    _opaque_rgb_png, _png_bytes, compare_opaque_rgb, validate_roi)
from capture_private_pcsx_frame_witness import (
    _publish_four_no_overwrite, verify_private_frame_witness)
from capture_private_pcsx_redux_vram import _validate_basename

MAX_PIXELS = 1024 * 1024


def temporal_consistency_mask(first, second, width, height, *, tolerance=0):
    """One byte per pixel: 1 means RGB within tolerance in both originals."""
    if (type(width) is not int or type(height) is not int or width <= 0
            or height <= 0 or width*height > MAX_PIXELS
            or type(tolerance) is not int or not 0 <= tolerance <= 255):
        raise ValueError("invalid temporal ROI geometry or tolerance")
    size = width * height * 3
    if (type(first) is not bytes or type(second) is not bytes
            or len(first) != size or len(second) != size):
        raise ValueError("both temporal RGB samples must have identical geometry")
    stable = bytearray(width*height)
    changed = 0
    for pixel in range(width*height):
        offset = pixel*3
        if max(abs(first[offset+i]-second[offset+i]) for i in range(3)) <= tolerance:
            stable[pixel] = 1
        else:
            changed += 1
    return bytes(stable), {
        "roi_pixel_count": width*height,
        "temporally_consistent_pixel_count": width*height-changed,
        "temporally_changed_pixel_count": changed,
        "temporally_consistent_fraction": round(
            (width*height-changed)/(width*height), 8),
        "temporal_tolerance_per_rgb_channel": tolerance,
        "temporal_mask_sha256": hashlib.sha256(stable).hexdigest(),
        "temporal_mask_is_not_a_semantic_static_tile_label": True,
    }


def assess_rendered_candidate(first, candidate, mask, width, height,
                              *, error_threshold=0):
    """Always return all-pixel error AND separate stable-only error.

    A candidate with zero stable errors may still differ from the original
    due to animation, wrong scene state or its own provenance.
    """
    if (type(error_threshold) is not int or
            not 0 <= error_threshold <= 255):
        raise ValueError("invalid candidate RGB error threshold")
    if (type(mask) is not bytes or len(mask) != width*height
            or any(bit not in (0,1) for bit in mask)):
        raise ValueError("expected one binary temporal mask byte per pixel")
    total, diff = compare_opaque_rgb(
        first, candidate, width, height, threshold=error_threshold)
    stable_count = sum(mask)
    dynamic_count = len(mask)-stable_count
    if stable_count == 0:
        # A completely changing ROI cannot support a stable-pixel score.
        stable_metrics = None
    else:
        total_error = 0
        squared_error = 0
        largest = 0
        mismatched = 0
        exact = 0
        for pixel, is_stable in enumerate(mask):
            if not is_stable:
                continue
            offset = pixel*3
            channels = [diff[offset+i] for i in range(3)]
            maximum = max(channels)
            total_error += sum(channels)
            squared_error += sum(v*v for v in channels)
            largest = max(largest, maximum)
            exact += (maximum == 0)
            mismatched += (maximum > error_threshold)
        stable_metrics = {
            "stable_pixel_count": stable_count,
            "exact_matching_stable_pixel_count": exact,
            "threshold_exceeding_stable_pixel_count": mismatched,
            "threshold_exceeding_stable_pixel_fraction":
                round(mismatched/stable_count,8),
            "stable_rgb_mean_absolute_channel_error":
                round(total_error/(3*stable_count),8),
            "stable_rgb_root_mean_square_channel_error":
                round((squared_error/(3*stable_count))**0.5,8),
            "stable_max_absolute_rgb_channel_error": largest,
        }
    return {
        "all_pixel_comparison": total,
        "stable_only_comparison": stable_metrics,
        "temporally_changed_pixels_excluded_from_stable_only_score":
            dynamic_count,
        "all_pixel_metrics_are_not_masked": True,
        "static_semantics_unverified": True,
        "frame_identity_and_gpu_clut_unverified": True,
    }


def _load_verified_frame(folder, basename):
    _validate_basename(basename)
    result = verify_private_frame_witness(folder, basename=basename)
    # The operator's scene label is a consistency guard, NOT proof of map ID.
    manifest_path = Path(folder) / (basename + ".capture.json")
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 32768:
        raise ValueError("invalid private witness manifest")
    def no_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate witness manifest JSON key")
            result[key] = value
        return result
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"),
                          object_pairs_hook=no_duplicate_keys)
    label = manifest.get("operator_scene_label")
    if type(label) is not str or not 1 <= len(label) <= 160:
        raise ValueError("invalid witness operator scene label")
    path = Path(folder) / (basename + ".screen.png")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != result["screen_sha256"]:
        raise ValueError("screenshot changed after Stage432 witness verification")
    size, rgb = _opaque_rgb_png(raw)
    return result, size, rgb, label


def compare_private_reference_frames(
        witness_dir, first_basename, second_basename,
        output_directory, analysis_basename, *,
        x, y, width, height, temporal_tolerance=0,
        candidate_png=None, candidate_threshold=0):
    from PIL import Image
    for name in (first_basename,second_basename,analysis_basename):
        _validate_basename(name)
    if first_basename == second_basename:
        raise ValueError("two independently named Stage432 captures are required")
    root=Path(witness_dir)
    output=Path(output_directory)
    if not output.is_dir():
        raise ValueError("private output directory must already exist")

    meta_a, size_a, frame_a, label_a = _load_verified_frame(root, first_basename)
    meta_b, size_b, frame_b, label_b = _load_verified_frame(root, second_basename)
    if label_a != label_b:
        raise ValueError("operator scene labels differ between reference frames")
    if size_a != size_b:
        raise ValueError("original screen dimensions differ: no resampling permitted")
    if meta_a["cd_info_sha256"] != meta_b["cd_info_sha256"]:
        raise ValueError("CD-info byte fingerprints differ between reference frames")
    rectangle=validate_roi(x,y,width,height,*size_a)
    first=frame_a.crop(rectangle)
    second=frame_b.crop(rectangle)
    first_rgb=first.tobytes()
    second_rgb=second.tobytes()
    mask, mask_stats=temporal_consistency_mask(
        first_rgb,second_rgb,width,height,tolerance=temporal_tolerance)
    mask_image=Image.frombytes(
        "L",(width,height),bytes(255 if v else 0 for v in mask))
    mask_image=mask_image.convert("RGB")
    first_png=_png_bytes(first)
    second_png=_png_bytes(second)
    mask_png=_png_bytes(mask_image)
    outputs={
        analysis_basename+".first.png":first_png,
        analysis_basename+".second.png":second_png,
        analysis_basename+".temporal-mask.png":mask_png,
    }
    manifest={
        "schema":1,
        "kind":"WA1_PRIVATE_SURF_TEMPORAL_ROI_CONSISTENCY",
        "first_capture": first_basename,
        "second_capture": second_basename,
        "first_screenshot_sha256":meta_a["screen_sha256"],
        "second_screenshot_sha256":meta_b["screen_sha256"],
        "first_vram_sha256":meta_a["vram_sha256"],
        "second_vram_sha256":meta_b["vram_sha256"],
        "same_disc_info_sha256":meta_a["cd_info_sha256"],
        "operator_scene_labels_match_but_are_not_authenticated":True,
        "screenshots_byte_identical":
            meta_a["screen_sha256"]==meta_b["screen_sha256"],
        "screenshot_dimensions":{"width":size_a[0],"height":size_a[1]},
        "roi_xywh":{"x":x,"y":y,"width":width,"height":height},
        "first_roi_rgb_sha256":hashlib.sha256(first_rgb).hexdigest(),
        "second_roi_rgb_sha256":hashlib.sha256(second_rgb).hexdigest(),
        "first_roi_png_sha256":hashlib.sha256(first_png).hexdigest(),
        "second_roi_png_sha256":hashlib.sha256(second_png).hexdigest(),
        "mask_png_sha256":hashlib.sha256(mask_png).hexdigest(),
        "mask_stats":mask_stats,
        "candidate_comparison":None,
        "interpretation":{
            "both_original_screens_verified_against_stage432_witness":True,
            "candidate_and_reference_not_automatically_aligned":True,
            "stable_pixels_mean_consistent_only_in_two_observations":True,
            "screenshot_and_disc_info_do_not_authenticate_map_identity":True,
            "gp0_draw_time_clut_and_source_tile_mapping_unverified":True,
            "all_outputs_stay_private":True,
        },
    }
    if candidate_png is not None:
        candidate_file=Path(candidate_png)
        if candidate_file.is_symlink() or not candidate_file.is_file():
            raise ValueError("candidate must be an existing non-symlink PNG")
        candidate_bytes=candidate_file.read_bytes()
        candidate_size, candidate=_opaque_rgb_png(candidate_bytes)
        if candidate_size!=(width,height):
            raise ValueError("candidate differs from ROI dimensions; no scaling permitted")
        manifest["candidate_comparison"]=assess_rendered_candidate(
            first_rgb,candidate.tobytes(),mask,width,height,
            error_threshold=candidate_threshold)
        manifest["candidate_comparison"].update({
            "candidate_png_sha256":hashlib.sha256(candidate_bytes).hexdigest(),
            "candidate_rgb_sha256":hashlib.sha256(candidate.tobytes()).hexdigest(),
            "candidate_file_basename":candidate_file.name,
            "candidate_is_independent_renderer_output_unverified":True,
        })
        # The RGB mask is a diagnostic, not an alpha channel or a crop guide.
        candidate_output=_png_bytes(candidate)
        outputs[analysis_basename+".candidate.png"]=candidate_output
        manifest["candidate_comparison"]["copied_candidate_png_sha256"]=hashlib.sha256(
            candidate_output).hexdigest()

    filename=analysis_basename+".evidence.json"
    outputs[filename]=(json.dumps(manifest,indent=2,sort_keys=True)+"\n").encode("utf-8")
    _publish_four_no_overwrite(output,outputs)
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_witness_directory",type=Path)
    p.add_argument("first_witness_basename")
    p.add_argument("second_witness_basename")
    p.add_argument("private_output_directory",type=Path)
    p.add_argument("analysis_basename")
    p.add_argument("--x",type=int,required=True)
    p.add_argument("--y",type=int,required=True)
    p.add_argument("--width",type=int,required=True)
    p.add_argument("--height",type=int,required=True)
    p.add_argument("--temporal-tolerance",type=int,default=0)
    p.add_argument("--candidate-png",type=Path)
    p.add_argument("--candidate-threshold",type=int,default=0)
    args=p.parse_args()
    result=compare_private_reference_frames(
        args.private_witness_directory,args.first_witness_basename,
        args.second_witness_basename,args.private_output_directory,
        args.analysis_basename,x=args.x,y=args.y,
        width=args.width,height=args.height,
        temporal_tolerance=args.temporal_tolerance,
        candidate_png=args.candidate_png,
        candidate_threshold=args.candidate_threshold)
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
