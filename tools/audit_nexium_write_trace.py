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
    r"tries=(\d+) renamed=(\d+) equal=(\d+) errno=(\d+)")
FIELDS = ("result", "ready", "step", "old_a", "old_b",
          "temporary", "published", "generation",
          "attempts", "renamed", "bytes_equal", "errno")
STEPS = {
    0: "preflight", 1: "previous_slots_read", 2: "temporary_opened",
    3: "temporary_synced", 4: "temporary_validated",
    5: "old_slot_removed", 6: "rename_attempted",
    7: "postpublish_readback", 8: "verified_committed",
    9: "failed_temporary_write", 10: "failed_temporary_verification",
    11: "failed_target_removal", 12: "failed_readback",
}

def extract(logs):
    entries = []
    for file in logs:
        path = Path(file)
        if not path.is_file():
            continue
        for line in path.read_text(errors="replace").splitlines():
            for hit in PATTERN.finditer(line):
                payload = dict(zip(FIELDS, map(int, hit.groups())))
                payload["step_label"] = STEPS.get(
                    payload["step"], "unknown")
                payload["source"] = path.name
                entries.append(payload)
    # NeXium may mirror a single event to multiple log sinks. Preserve all
    # raw lines while allowing the report consumer to inspect source.
    return {
        "kind": "stage_302_guest_sd_write_stage_diagnostics",
        "found": len(entries) > 0,
        "records": entries,
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
