# Stage452 — owner-private paused screen witness ↔ native GPUDUMP pretrace VRAM state

## Motivation

Stages432–434 produce paused, read-only PCSX-Redux **screenshot/CD/VRAM witnesses**
and screen-space reference patches. Stages447–451 independently produce
native GP0 dump evidence, including its **initial 1 MiB VRAM** and
exact GP0 packets through the first completed native VSync.

They can be captured at different times, under different camera/map
states or even different loaded games. **A screenshot hash and a GPU
dump hash alone are not proof they refer to one frame.**

Stage452 adds an owner-private, conservative **state-equality gate**
between these independently acquired kinds of evidence. In strict mode
it accepts only if the full 1 MiB paused witness VRAM digest matches
the original native dump **pretrace** VRAM digest. It does **not**
pretend that repeated identical texture memory proves the same frame.

## Checks

`tools/bind_private_screen_witness_to_gpudump.py`:

1. Verifies the four Stage432 witness files in the original
   directory using its established verifier: the **two-read VRAM
   manifest**, screenshot PNG chunk framing/CRC, screenshot SHA-256,
   original CD-info JSON and its SHA-256, manifest-controlled file
   names and exact one-megabyte raw VRAM length.
2. Re-runs Stage451's independent checks of the entire native
   GPUDUMP, pretrace VRAM file and GP0 JSONL: all original GP0
   packet words, starting VRAM bytes, exact first live-frame
   word count, native file identity, monotonic native VSync
   chronology and, by default, a complete final VSync boundary.
3. Compares the paused Stage432 witness raw VRAM SHA-256 with the
   native GPU dump's **full original pretrace 1 MiB VRAM** digest.
   An exact match supports **same memory state at the recorded
   observations** only. The stage does not infer a matching
   screenshot timestamp or matching native frame.
4. Verifies the Stage432 witness bundle a **second time** after
   native checks to catch accidental replacement of PNG,
   VRAM or CD info during analysis. This is a consistency
   check, not protection against a malicious concurrent writer.
5. By default, refuses VRAM mismatches; optional
   `--allow-different-vram-states` reports them as
   `DIFFERENT_VRAM_STATES_NO_FRAME_BINDING` without any
   claim of visual alignment.
6. By default, refuses an incomplete native capture; optional
   `--allow-incomplete-native-capture` retains Stage451's
   explicitly restricted *first-frame only* evidence.
7. Supports operator-independent expected screenshot SHA-256,
   native dump SHA-256, native GameID, frame label and number
   of completed native frames for consistency checks. None
   of these by itself authenticates the original disc,
   emulator executable or map state.
8. Exposes only owner-private **hashes, counts, conditional
   statuses and evidence caveats**. No screenshot pixels,
   raw VRAM, source CDSTG, GPU words, CD-info payload or
   game artwork are copied into reports.

Status values:

- `EXACT_VRAM_STATE_EQUALITY_WITH_UNVERIFIED_FRAME_ALIGNMENT`
- `DIFFERENT_VRAM_STATES_NO_FRAME_BINDING`

**Do not rename the first status to "same-frame proven."**
Two frames can have the same exact VRAM contents; an emulator
screenshot can reflect a completed framebuffer produced before
the pretrace VRAM read. VSync uses emulator CPU/GPU cycle stamps,
whereas the Stage432 screenshot endpoint provides no independent
GPU-cycle identity.

## Private operator workflow

The owner first records a paused Stage432 witness using PCSX-Redux's
local screen/VRAM/CD-info endpoints and separately captures a native
GPUDUMP with its built-in GPU Dump Recorder / Player.

After Stage447 import into native pretrace VRAM plus first-frame
GPU packet JSONL:

```sh
python tools/bind_private_screen_witness_to_gpudump.py \
  /private/WildArms/witness \
  surf_village_frame_witness \
  /private/WildArms/gpu/surf.gpudump \
  /private/WildArms/gpu/surf-first-frame.before.u16le.bin \
  /private/WildArms/gpu/surf-first-frame.gp0.jsonl \
  --expected-frame 0 \
  > /private/WildArms/gpu/stage452-private-screen-state.json
```

If the two separate captures have different VRAM states and the
operator wishes to investigate rather than reject, add
`--allow-different-vram-states`. The result will explicitly
state that no exact state binding was established.

The **next evidence gate** is a recording mechanism that links
the native GPUDUMP's frame to an *independently observed rendered
screen of precisely that GPU frame* with a trusted frame/cycle
identifier or verified player replay. Stage452 does not create
that frame-level synchronization or render the GPU packets.

## Synthetic test coverage and privacy

`tests/test_bind_private_screen_witness_to_gpudump.py`
contains **21 ROM-free tests**. It constructs entirely artificial
Stage432 paused witnesses and Stage447 native GPU dumps,
then exercises exact VRAM state match, mismatch/strict override,
PNG or disc-info replacement, mutated GP0/VRAM, multi-frame
chronology, native hash/GameID/frame expectations, two-read
witness stability, symlink/path-safety and metadata privacy.

No real original Wild Arms GPU capture was obtained. The
original disc BIN/CUE, textures, complete source GP0, native
dump, paused witness images, CD information and even derived
hashes/reports remain outside public GitHub or CI.

Passing synthetic CI is evidence of correct **consistency
checks**, not evidence that a real Surf Village roof or well
has been recovered or visually reconstructed.
