#!/usr/bin/env python3
"""Stage519 opt-in private direct V2 write from the actual GUI Step-1 button.

Generate a single combined patch for the pinned *clean* PCSX-Redux checkout.
The owner supplies an absolute destination using WA1_PRIVATE_STEP1_V2_PATH.
No game bytes are included. No file is written until the actual button is
pressed at Player Frame 1. The legacy Save dialog remains the default.
"""
import argparse
import difflib
from pathlib import Path
import subprocess

import patch_private_pcsx_gpudump_player_step1_dump_hash as v2
import patch_private_pcsx_gpudump_player_step1_export as v1

PINNED = v2.PINNED
ENV_NAME = "WA1_PRIVATE_STEP1_V2_PATH"
BUTTON_ANCHOR = "            m_stepExportDialog.openDialog();\n"
DIRECT_BODY = """            const char* privatePath = std::getenv("WA1_PRIVATE_STEP1_V2_PATH");
            if (privatePath != nullptr) {
                // Opt-in path belongs to the owner, not a public CI artifact.
                // Do not default to the checkout or dump directory.
                const std::filesystem::path requested(privatePath);
                std::error_code parentError;
                const auto parent = requested.parent_path();
                const bool safeParent =
                    requested.is_absolute() && !requested.filename().empty() &&
                    !parent.empty() &&
                    std::filesystem::is_directory(parent, parentError) &&
                    !parentError && !std::filesystem::is_symlink(parent, parentError) &&
                    !parentError;
                if (!safeParent ||
                    !wa1WriteFrozenStepOneVRAM(
                        requested.string(), m_frozenStepOneVRAM,
                        m_frozenStepOneFrame, m_frozenDumpSHA256)) {
                    m_error = _("Private Step-1 direct V2 export refused; inspect path and permissions.");
                } else {
                    m_error.clear();
                }
                // Direct save does not leave private VRAM in GUI dialog state.
                m_frozenStepOneVRAM.clear();
                m_frozenStepOneFrame = 0;
                m_frozenDumpSHA256.fill(0);
            } else {
                m_stepExportDialog.openDialog();
            }
"""


def replace_exactly_once(source, anchor, replacement):
    if source.count(anchor) != 1:
        raise ValueError("Stage519 exact pinned Player GUI anchor missing or duplicated")
    return source.replace(anchor, replacement, 1)


def add_direct_path_to_patched_gui(source):
    """Add the environment-only path to already stage455+456 patched source."""
    source=replace_exactly_once(source,"#include <cstdio>\n",
                                "#include <cstdio>\n#include <cstdlib>\n")
    source=replace_exactly_once(source,BUTTON_ANCHOR,DIRECT_BODY)
    return source


def unified(old,new,path):
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True),new.splitlines(keepends=True),
        fromfile="a/"+path,tofile="b/"+path))


def make_diff(core_h,core_cc,gui_h,gui_cc):
    """Produce full upstream->Stage519 diff from pristine pinned originals."""
    result={
        v2.CORE_HEADER:v2.patched_core_header(core_h),
        v2.CORE_SOURCE:v2.patched_core_source(core_cc),
        v2.GUI_HEADER:v2.patched_gui_header(v1.patched_header(gui_h)),
        v2.GUI_SOURCE:add_direct_path_to_patched_gui(
            v2.patched_gui_source(v1.patched_source(gui_cc))),
    }
    originals={v2.CORE_HEADER:core_h,v2.CORE_SOURCE:core_cc,
               v2.GUI_HEADER:gui_h,v2.GUI_SOURCE:gui_cc}
    return "".join(unified(originals[p],result[p],p)
                   for p in (v2.CORE_HEADER,v2.CORE_SOURCE,
                             v2.GUI_HEADER,v2.GUI_SOURCE))


def check_or_apply(repository, apply=False):
    repository=Path(repository)
    if not repository.is_dir():
        raise ValueError("pinned PCSX-Redux checkout is absent")
    head=subprocess.run(["git","-C",str(repository),"rev-parse","HEAD"],
        capture_output=True,text=True,check=True).stdout.strip()
    if head != PINNED:
        raise ValueError("unexpected upstream revision for Stage519")
    status=subprocess.run(["git","-C",str(repository),"status","--porcelain"],
        capture_output=True,text=True,check=True).stdout
    if status:
        raise ValueError("Stage519 requires clean pinned upstream checkout")
    core_h=(repository/v2.CORE_HEADER).read_text(encoding="utf-8")
    core_cc=(repository/v2.CORE_SOURCE).read_text(encoding="utf-8")
    gui_h=(repository/v2.GUI_HEADER).read_text(encoding="utf-8")
    gui_cc=(repository/v2.GUI_SOURCE).read_text(encoding="utf-8")
    diff=make_diff(core_h,core_cc,gui_h,gui_cc)
    if not diff:
        raise ValueError("empty Stage519 patch")
    outcome=subprocess.run(["git","-C",str(repository),"apply","--check","-"],
        input=diff,capture_output=True,text=True)
    if outcome.returncode:
        raise ValueError("Stage519 combined patch rejected: "+outcome.stderr[:600])
    if apply:
        subprocess.run(["git","-C",str(repository),"apply","-"],
            input=diff,capture_output=True,text=True,check=True)
    return diff


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_pcsx_redux_checkout")
    parser.add_argument("--apply",action="store_true")
    args=parser.parse_args()
    diff=check_or_apply(args.pinned_pcsx_redux_checkout,args.apply)
    print(("Applied" if args.apply else "Validated")+
        " pinned owner-private GUI V2 direct-path patch; diff bytes="+
        str(len(diff.encode("utf-8"))))


if __name__=="__main__":
    main()
