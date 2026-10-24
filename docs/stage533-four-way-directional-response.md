# Stage533 — four-way directional response and deterministic VRAM replay

## Original-game experiment

Stage533 extends the owner-private Stage532 Surf Village experiment. The exact dialog_series_230.state checkpoint was loaded into the pinned PCSX-Redux build with OpenBIOS, dynarec and the software GPU. The canonical Wild Arms (USA) BIN/CUE and emulator AppImage were rechecked against the Stage531 owner-private source manifest.

Five runs were captured: neutral control and LEFT, RIGHT, UP and DOWN. Each directional override was active for 30 VSync frames. Every run was repeated from the same checkpoint. The four directional runs and the neutral control all began with the same raw 1 MiB VRAM hash. For each of the five conditions, the before-VRAM and after-VRAM buffers matched their repeats byte-for-byte.

## Measured framebuffer displacement

Phase correlation on the 320×240 grayscale framebuffer estimates the visible background displacement from before to after. Since the camera tracks Rudy, the background moves opposite the input direction.

| Run | Background shift (x, y) | Changed grayscale pixels |
|---|---:|---:|
| Neutral | (+0.06, +0.04) px | 870 |
| LEFT | (+56.02, −0.04) px | 63,480 |
| RIGHT | (−26.93, −0.03) px | 59,953 |
| UP | (+0.03, +36.04) px | 62,473 |
| DOWN | (+0.14, −57.95) px | 65,438 |

The neutral control stays within one pixel of zero displacement. All four directional signs match the expected opposite background movement. Displacement magnitudes are asymmetric; this experiment does not assume constant speed or infer the map boundary/collision state from a single short input.

## Determinism and unresolved state serialization

All repeated raw VRAM outputs are exact matches, which establishes reproducible rendered output for this controlled software-GPU experiment. However, serialized after-savestate files are not byte-identical across repeated runs. The reason for this serialization difference has not yet been localized, so it remains an explicit follow-up rather than being treated as harmless or ignored.

A new tools/validate_directional_response_stage533.py gate checks the aggregate report schema, shared initial-VRAM identity, repeated-output hashes, expected displacement signs, neutral-control tolerance and the explicit unverified-status flags. Its tests use synthetic report data only; it does not read or authenticate private game data or recompute image correlation.

## Evidence and acceptance boundaries

- **Four-way input response:** observed in the original game under PCSX-Redux software GPU.
- **Rendered-output repeatability:** PASS; raw VRAM is byte-identical across each repeated condition.
- **Stage532 archive durability:** independently downloaded from owner-only Drive; whole ZIP SHA-256, ZIP CRC and all 23 manifest-listed member hashes matched.
- **Internal field-map index:** still unconfirmed.
- **Serialized savestate determinism:** open; after-state files differ even when rendered VRAM matches.
- **PS1 hardware parity, Switch runtime parity and full remake GPU parity:** not established.

Original BIN/CUE, savestates, raw VRAM, GUI captures, private hashes and detailed run logs remain in owner-only Google Drive. GitHub CI runs synthetic tests only.
