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
    boot_request = guest is not None and (
        "Booting NRO:" in guest or "Boot: NRO=" in guest)
    boot_failed = guest is not None and "Boot failed:" in guest
    frontend_rejected = guest is not None and "Failed to load NRO:" in guest
    frontend_requested = guest is not None and "Auto-loaded NRO:" in guest

    # Most meaningful blocker takes precedence. A frontend request can
    # coexist with a later, fatal guest BootContext loader failure.
    if guest is None:
        outcome = "internal_log_missing"
    elif boot_failed:
        outcome = "guest_boot_failed"
    elif frontend_rejected:
        outcome = "frontend_load_request_failed"
    elif boot_request:
        outcome = "guest_boot_requested"
    elif frontend_requested:
        outcome = "frontend_autoload_requested"
    else:
        outcome = "no_guest_boot_marker"
    return {
        "kind": "nexium_host_log_audit",
        "guest_session_log_found": guest is not None,
        "control_session_log_found": control is not None,
        "guest_boot_outcome": outcome,
        "guest_boot_request_seen": boot_request,
        "guest_boot_failure_reported": boot_failed,
        "frontend_autoload_request_seen": frontend_requested,
        "frontend_load_request_failure_seen": frontend_rejected,
        "control_has_autoload_marker": control is not None and "Auto-loaded NRO:" in control,
        "guest_rendered_frame_confirmed": False,
        "note": "GUI accepted request or guest Booting NRO log is not proof of successful loader or guest frame.",
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
