#!/usr/bin/env python3
"""Stage396: independent THIRD real NeXium process / ARM cold restart audit.

Requires genuine Xvfb screenshots captured in a NEW NeXium guest process,
using the EXACT SAME isolated SDMC as the previous guest's transient ARM
training. Synthetic inputs are used ONLY by separate auditor unit tests.
"""
import argparse
import hashlib
import json
from pathlib import Path

from audit_nexium_arm_guest import (
    ARM_BORDER, ARM_FULL_BAR, ARM_PARTIAL_BAR, ARM_PAST_PARTIAL,
    GOLD, BLUE, RED, DARK,
    battle_slots, same_game, same_arm_panel,
)
from audit_nexium_field_journal import native_pixel, read_rgb

NAMES = ("08_arm_spent_before_exit", "09_arm_restart_field",
         "10_arm_restart_full", "11_arm_restart_return")


def valid_terminated(processes, prefix):
    forced=processes[f"{prefix}_force_killed"]
    status=processes[f"{prefix}_wait_status"]
    return (type(forced) is bool and type(status) is int and
            ((forced and status == 137) or
             (not forced and status in (0,143))))


def audit_arm_cold_boot(original_shots, cold_shots,
                        processes_file, cold_process_file,
                        arm_root, report):
    original_shots, cold_shots=Path(original_shots),Path(cold_shots)
    original_needed=("00_baseline_field", "03_arm_full", "07_arm_return")
    if not all((original_shots / (n + ".png")).is_file()
               for n in original_needed):
        raise ValueError("first or second guest reference screens missing")
    actual={p.name for p in cold_shots.glob("*.png")}
    expected={n + ".png" for n in NAMES}
    if actual != expected:
        raise ValueError(f"missing/extra third guest screenshots: {actual ^ expected}")
    processes=json.loads(Path(processes_file).read_text(encoding="utf-8"))
    cold=json.loads(Path(cold_process_file).read_text(encoding="utf-8"))
    if set(cold) != {"armrestart_pid","armrestart_wait_status",
                     "armrestart_force_killed","armrestart_wait_completed"}:
        raise ValueError("unexpected or missing cold restart process fields")
    for k in ("baseline_pid","arm_pid","armrestart_pid"):
        process=processes if k!="armrestart_pid" else cold
        if type(process.get(k)) is not int or process[k]<=0:
            raise ValueError(f"invalid guest PID {k}")
    if not isinstance(cold.get("armrestart_wait_completed"),bool):
        raise ValueError("invalid cold restart wait evidence")
    # Check actual journal mount root. A missing SDMC path does not prove
    # no disk I/O, and a nonempty directory is never a clean training case.
    arm_dir=battle_slots(arm_root)[0].parent
    rooted=arm_dir.is_dir() and not arm_dir.is_symlink()
    entries=list(arm_dir.iterdir()) if rooted else []
    before={name:read_rgb(original_shots / (name+".png"))
            for name in original_needed}
    new={name:read_rgb(cold_shots / (name+".png")) for name in NAMES}
    spent=new[NAMES[0]]
    field=new[NAMES[1]]
    full=new[NAMES[2]]
    returned=new[NAMES[3]]
    first_field=before["00_baseline_field"]
    prior_full=before["03_arm_full"]
    prior_return=before["07_arm_return"]
    checks={
        "three_distinct_true_nexium_processes":
            len({processes["baseline_pid"],processes["arm_pid"],
                 cold["armrestart_pid"]}) == 3
            and cold["armrestart_wait_completed"] is True
            and valid_terminated(cold,"armrestart"),
        "same_real_sdmc_restart_still_empty":
            rooted and not entries,
        "previous_guest_really_exited_with_spent_2_of_3_and_foe_down":
            native_pixel(spent,*ARM_BORDER)==GOLD
            and native_pixel(spent,*ARM_PARTIAL_BAR)==GOLD
            and native_pixel(spent,*ARM_PAST_PARTIAL)==DARK
            and native_pixel(spent,*ARM_FULL_BAR)==DARK
            and native_pixel(spent,692+100,249)==DARK,
        "arm_cold_boot_returns_to_exact_original_field":
            same_game(first_field,field)
            and same_game(prior_return,field),
        "new_zl_r_reset_magazine_three_of_three":
            native_pixel(full,*ARM_BORDER)==GOLD
            and native_pixel(full,*ARM_FULL_BAR)==GOLD
            and native_pixel(full,70,220)==BLUE
            and native_pixel(full,692+230,249)==RED,
        "cold_boot_matches_initial_unspent_arm_scene":
            same_game(prior_full,full)
            and same_arm_panel(prior_full,full),
        "third_guest_b_returns_without_side_effect":
            same_game(field,returned)
            and same_game(first_field,returned),
        "cold_boot_never_creates_battle_or_field_save":
            rooted and not entries
            and not any(p.exists() or p.is_symlink()
                        for p in battle_slots(arm_root)),
    }
    result={
        "kind":"stage396_real_nexium_third_process_cold_restart",
        "provenance":"actual_emulator_xvfb_guest_not_host_generated_fixture",
        "checks":checks,
        "all_checks_passed":all(checks.values()),
        "sha256":{name:hashlib.sha256(
            (cold_shots/(name+".png")).read_bytes()).hexdigest()
            for name in NAMES},
        "restarted_pid":cold["armrestart_pid"],
    }
    report=Path(report)
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",
                      encoding="utf-8")
    return result


if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--original-shots",type=Path,required=True)
    cli.add_argument("--cold-shots",type=Path,required=True)
    cli.add_argument("--processes",type=Path,required=True)
    cli.add_argument("--cold-process",type=Path,required=True)
    cli.add_argument("--arm-root",type=Path,required=True)
    cli.add_argument("--report",type=Path,required=True)
    opt=cli.parse_args()
    try:
        result=audit_arm_cold_boot(
            opt.original_shots,opt.cold_shots,opt.processes,
            opt.cold_process,opt.arm_root,opt.report)
    except (OSError,ValueError,KeyError,TypeError) as err:
        cli.exit(2,f"NeXium ARM cold reboot audit rejected: {err}\n")
    print(json.dumps(result["checks"],sort_keys=True))
    if not result["all_checks_passed"]:
        cli.exit(1,"Real NeXium cold reboot check failed\n")
