# GTE NCLIP oriented triangle area and RTPT -> NCLIP

NCLIP consumes the existing signed 16-bit packed SXY0, SXY1 and SXY2 screen coordinates and writes MAC0 as a signed 32-bit register:

```text
wide_area = SX0*(SY1-SY2) + SX1*(SY2-SY0) + SX2*(SY0-SY1)
MAC0 = signed_low32(wide_area)
```

The signed 64-bit intermediate is checked against the signed 32-bit range, setting FLAG bit 16 on positive overflow and bit 15 on negative overflow. Those MAC0 overflow bits *alone* do not set FLAG bit 31. NCLIP has its **own command FLAG** rather than inheriting the FLAG of the previous RTPT.

Independent code reference: [PCSX ReARMed GTE NCLIP](https://github.com/notaz/pcsx_rearmed/blob/master/libpcsxcore/gte.c), especially `gteNCLIP_` and `mac0flags`.

## Added source

- `include/gte_nclip_reference.hpp`: pure, constexpr NCLIP computation from three packed SXY register values. It returns full signed area, architectural signed MAC0 and FLAG.
- `include/gte_rtpt_nclip_reference.hpp`: separate composition invoking the earlier three-vertex `rtpt_reference()` and then `nclip_reference()` on the resulting FIFO.
- `tests/test_gte_nclip_reference.cpp`: positive and negative winding (±10000), zero area, extreme signed screen values yielding MAC0 positive/negative overflow with 32-bit wrap, and RTPT-to-NCLIP sequencing with a prior RTPT depth error that does **not** carry into NCLIP FLAG.

The CMake root registers `wa_gte_nclip_reference_tests` as the **28th** named CTest suite.

## What was verified

An isolated local C++20 CMake build of the new stage and its included dependent headers succeeded and CTest passed **1/1**. The previous 27-suite full-project test run preceded this change; **a fresh 28-suite full-project build has not yet been executed**. No authentic hardware capture is available for an end-to-end register comparison and GitHub Actions CI has not been checked for this update.

## Scope

The standard RTPT model still has known fidelity limitations, including precise hardware FLAG behavior, and this NCLIP stage is a portable arithmetic reference rather than a playable game renderer. No original Wild Arms game assets were committed. A Switch game executable is not yet available.
