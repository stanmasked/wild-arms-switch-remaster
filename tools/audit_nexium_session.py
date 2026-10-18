#!/usr/bin/env python3
"""Audit NeXium's internal session logs; not a guest rendering assertion."""
import argparse
import json
from pathlib import Path

MAX_LOG_BYTES = 2_000_000


def read_log(path):
    path = Path(path)
    if not path.is_file():
        return None
    if path.stat().st_size > MAX_LOG_BYTES:
        raise ValueError(f"oversized emulator log: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def analyze(guest_path, control_path):
    guest, control = read_log(guest_path), read_log(control_path)
    if guest is None:
        outcome = "internal_log_missing"
    elif "Failed to load NRO:" in guest:
        outcome = "load_failed_reported"
    elif "Auto-loaded NRO:" in guest:
        outcome = "auto_load_accepted"
    elif "Boot: NRO=" in guest:
        outcome = "boot_request_logged"
    else:
        outcome = "no_guest_boot_marker"
    return {
        "kind": "nexium_host_log_audit",
        "guest_session_log_found": guest is not None,
        "control_session_log_found": control is not None,
        "guest_boot_outcome": outcome,
        "guest_boot_request_seen": guest is not None and "Boot: NRO=" in guest,
        "guest_autoload_accepted": guest is not None and "Auto-loaded NRO:" in guest,
        "guest_load_failure_reported": guest is not None and "Failed to load NRO:" in guest,
        "control_has_autoload_marker": control is not None and "Auto-loaded NRO:" in control,
        "guest_rendered_frame_confirmed": False,
        "note": "An internal log entry never confirms that a guest frame rendered.",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--guest", required=True, type=Path)
    p.add_argument("--control", required=True, type=Path)
    p.add_argument("--report", required=True, type=Path)
    a = p.parse_args()
    try:
        status = analyze(a.guest, a.control)
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    except (ValueError, OSError) as exc:
        p.exit(2, f"NeXium session log audit invalid: {exc}\n")
    print(json.dumps(status, sort_keys=True))


if __name__ == "__main__":
    main()
