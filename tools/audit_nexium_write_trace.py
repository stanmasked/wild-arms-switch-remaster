#!/usr/bin/env python3
"""Stage 302: extract versioned WA_SAVE_TRACE markers from NeXium debug logs.

Diagnostic tool only: never changes the game, journal, or CI pass criterion.
The fourth-guest strict screenshot/CRC audit remains a separate fail gate.
"""
import argparse
import json
import re
from pathlib import Path

PATTERN = re.compile(
    r"WA_SAVE_TRACE v1 result=(\d+) ready=(\d+) step=(\d+) "
    r"oldA=(\d+) oldB=(\d+) tmp=(\d+) pub=(\d+) gen=(\d+) "
    r"tries=(\d+) renamed=(\d+) equal=(\d+) errno=(\d+)"
    r"(?: count=(\d+) eof=(\d+) more=(\d+) magic=(\d+)"
    r" crc=(\d+) decoded=(\d+))?")
FIELDS = ("result", "ready", "step", "old_a", "old_b",
          "temporary", "published", "generation",
          "attempts", "renamed", "bytes_equal", "errno")
READBACK_FIELDS = ("bytes_read", "eof", "extra_byte",
                   "magic_ok", "crc_ok", "decoded_ok")
STEPS = {
    0: "preflight", 1: "previous_slots_read", 2: "temporary_opened",
    3: "temporary_synced", 4: "temporary_validated",
    5: "old_slot_removed", 6: "rename_attempted",
    7: "postpublish_readback", 8: "verified_committed",
    9: "failed_temporary_write", 10: "failed_temporary_verification",
    11: "failed_target_removal", 12: "failed_readback",
    13: "rescue_write_attempted", 14: "rescue_write_verified",
    15: "rescue_write_failed",
}


STATUS = {
    0: "stored", 1: "loaded", 2: "missing", 3: "corrupt",
    4: "invalid_world", 5: "invalid_state", 6: "io_error",
    7: "sequence_exhausted"
}
FAILURE_STAGES = {
    1: "preexisting_slot_read_error",
    2: "temporary_file_open_error",
    9: "temporary_write_sync_or_close_failed",
    10: "temporary_record_verification_failed",
    11: "old_slot_unlink_failed",
    12: "published_record_not_verified",
    15: "redundant_slot_rescue_failed",
}
def classify(payload):
    """Reason from recorded stages only, never from final SD contents."""
    if payload["ready"] == 0:
        return "storage_unavailable"
    if (payload["result"] == 0 and payload["step"] in (8, 14) and
        payload["bytes_equal"] == 1 and payload["published"] == 1):
        return ("exact_new_generation_rescued" if payload["step"] == 14
                else "exact_new_generation_verified")
    if payload["result"] == 6:
        return FAILURE_STAGES.get(payload["step"], "io_error_phase_unknown")
    if payload["result"] == 0:
        return "reported_success_missing_proof"
    if payload["result"] == 3:
        return "corrupt_prior_journal"
    return "other_save_status"

def validate_trace_payload(payload):
    return (payload["ready"] in (0, 1) and
            payload["renamed"] in (0, 1) and
            payload["bytes_equal"] in (0, 1) and
            payload["result"] in STATUS and
            payload["step"] in STEPS and
            0 <= payload["attempts"] <= 4)

def extract(logs):
    entries = []
    for file in logs:
        path = Path(file)
        if not path.is_file():
            continue
        for line in path.read_text(errors="replace").splitlines():
            for hit in PATTERN.finditer(line):
                raw = hit.groups()
                payload = dict(zip(FIELDS, map(int, raw[:len(FIELDS)])))
                detail = raw[len(FIELDS):]
                if detail and all(v is not None for v in detail):
                    payload.update(zip(READBACK_FIELDS, map(int, detail)))
                payload["extended_readback"] = bool(
                    detail and all(v is not None for v in detail))
                payload["step_label"] = STEPS.get(
                    payload["step"], "unknown")
                payload["source"] = path.name
                payload["valid_fields"] = validate_trace_payload(payload)
                if payload["extended_readback"]:
                    payload["valid_fields"] = (
                        payload["valid_fields"] and
                        0 <= payload["bytes_read"] <= 56 and
                        all(payload[key] in (0, 1) for key in
                            READBACK_FIELDS[1:]))
                payload["result_label"] = STATUS.get(
                    payload["result"], "unknown")
                payload["existing_a_label"] = STATUS.get(
                    payload["old_a"], "unknown")
                payload["existing_b_label"] = STATUS.get(
                    payload["old_b"], "unknown")
                payload["temporary_label"] = STATUS.get(
                    payload["temporary"], "unknown")
                payload["published_label"] = STATUS.get(
                    payload["published"], "unknown")
                payload["failure_class"] = (
                    classify(payload) if payload["valid_fields"]
                    else "malformed_trace_fields")
                if (payload["valid_fields"] and
                    payload["extended_readback"] and
                    payload["result"] == 6 and payload["step"] == 12):
                    if payload["bytes_read"] != 56:
                        payload["failure_class"] = "readback_short_record"
                    elif payload["extra_byte"] == 1:
                        payload["failure_class"] = "readback_extra_byte"
                    elif payload["magic_ok"] == 0:
                        payload["failure_class"] = "readback_header_mismatch"
                    elif payload["crc_ok"] == 0:
                        payload["failure_class"] = "readback_crc_mismatch"
                    elif payload["decoded_ok"] == 0:
                        payload["failure_class"] = "readback_decode_rejected"
                    else:
                        payload["failure_class"] = "readback_payload_differs"
                entries.append(payload)
    # NeXium may mirror a single event to multiple log sinks. Preserve all
    # raw lines while allowing the report consumer to inspect source.
    return {
        "kind": "stage_302_guest_sd_write_stage_diagnostics",
        "found": len(entries) > 0,
        "records": entries,
        "failure_classes": [x["failure_class"] for x in entries],
        "all_fields_valid": bool(entries) and all(
            x["valid_fields"] for x in entries),
        "production_save_result_unmodified": True,
        "strict_pixel_check_bypassed": False,
    }

def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", required=True, type=Path)
    cli.add_argument("logs", nargs="+", type=Path)
    x=cli.parse_args()
    report=extract(x.logs)
    x.output.parent.mkdir(parents=True,exist_ok=True)
    x.output.write_text(json.dumps(report, indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,sort_keys=True))

if __name__ == "__main__":
    main()
