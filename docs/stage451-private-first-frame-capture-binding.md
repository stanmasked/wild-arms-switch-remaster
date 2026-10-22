# Stage451 — Bind an imported first GPU frame to the same native PCSX capture

## Why this gate is needed

Stages447–450 establish four separately useful views of a native
PCSX-Redux GPU Dump Recorder file:

- Stage447 extracts a **one-megabyte initial VRAM** and a complete
  **supported first-frame GP0 command list** (with explicit
  pretrace bootstrap E1–E6 state), without recording original
  game resources in public CI.
- Stage448 reports native GP0/GP1 transport record types, completed
  VSync intervals and possible unsupported events without
  truncating genuine commands to make them pass.
- Stage449 independently checks **every imported GP0 packet word**
  and **every pretrace VRAM byte** against the original native dump.
- Stage450 checks the **64-bit native VSync cycle stamps**,
  duplicate TraceBegin, out-of-order markers and whether the
  whole capture terminates on a VSync boundary.

The fact that these checks each pass at some point does not
guarantee that the *same* native file was inspected in all of
them. Stage451 binds their conclusions to an **identical native
file SHA-256** and confirms that Stage448's native first-frame
GP0 transport word count agrees with Stage449's independent
import. This is necessary to prevent accidental mixing of
VRAM, GP0 JSONL and a different first-frame dump.

## Implementation

`tools/bind_private_pcsx_first_frame_evidence.py` performs a
single owner-local gate on three files:

1. Recomputes the full Stage449 private import integrity check,
   optionally comparing an independently supplied native dump
   SHA-256, game serial (operator assertion), or Stage437 frame
   label. No payload or game serial is returned.
2. Recomputes the Stage448 native transport preflight with the
   first completed frame included, rejecting unsupported live
   GP0/GP1/readback operations; its count includes the **live
   GPU words only**, not the initial full VRAM A0 upload or
   the artificial E1–E6 restore commands.
3. Independently recomputes the Stage450 chronology (including
   optional independently expected completed-frame count).
4. Requires all **three native file SHA-256 digests** to match;
   that the imported GP0 words and 1 MiB VRAM are byte-exact;
   that the first-frame GP0 word count matches the native
   transport aggregate; and that chronological VSync stamps
   strictly increase with one TraceBegin.
5. **By default, rejects** a native capture whose final typed
   record is not VSync. The `--allow-trailing-native-events`
   override allows using the *first complete frame only* but
   clearly marks the whole capture as **unverified**. It can
   never bypass malformed frame order or inconsistent imports.
6. Returns private metadata including the first native frame's
   64-bit GPU cycle stamp, complete VSync count, source file and
   imported artifact hashes, and supported packet counts.
   That first VSync cycle is an **emulator clock**, not actual
   wall-clock time. Stage437's frame number is an **operator
   label**, not a true native GPU cycle value.
7. Optionally writes the private report with
   `--private-manifest-out`, using exclusive no-clobber
   publication and restrictive **0600** file permissions.
   The report itself is owner-private (hashes can be
   sensitive); it must not be uploaded to public GitHub,
   issue comments, CI artifacts or releases.

Two distinct statuses can be returned:

- `WHOLE_NATIVE_CAPTURE_BOUND_TO_FIRST_FRAME_IMPORT`
- `FIRST_FRAME_BOUND_WITH_UNVERIFIED_TRAILING_NATIVE_EVENTS`

A completed boundary is a **recording-format condition**:
it does not prove correct GPU drawing, texture cache,
visibility, original game revision, map location, camera,
selected Surf Village roof, well, sprite, or CLUT color.

## Private use after real capture

Only after the owner has captured the original game using
PCSX-Redux's built-in **GPU Dump Recorder / Player** and has
already run the Stage447 native importer:

```sh
python tools/bind_private_pcsx_first_frame_evidence.py \
  /private/WildArms/gpu/surf.gpudump \
  /private/WildArms/gpu/surf-first-frame.before.u16le.bin \
  /private/WildArms/gpu/surf-first-frame.gp0.jsonl \
  --expected-frame 0 \
  --private-manifest-out /private/WildArms/gpu/stage451-binding.private.json
```

If multiple complete frames were intentionally recorded,
`--expected-completed-frames` can assert their count.
If the owner independently verifies a disc serial or
native file digest, `--expected-native-game-id` and
`--expected-native-sha256` can be used as *consistency*
checks; they are not independent emulator/disc attestation.

Do **not** pass `--allow-trailing-native-events` unless the
operator explicitly wants first-frame evidence despite an
unfinished recording tail, and understands this narrower scope.

The output manifest should be checked before proceeding to
Stage437–445 source→A0→GP0(80)→UV→CLUT comparisons.

## Remaining original-style HD scene proof gates

This stage still **does not extract original artwork or run
an actual Wild Arms GPU capture**. The native GPU recorder has
been verified in upstream PCSX-Redux source, but no authentic
Surf Village dump has been supplied to this project session.
A correct capture metadata chain is a prerequisite, not an
artwork reconstruction result.

Later work must cross-check exact original disc revision,
in-game map/camera and native frame number, then compare
visible screen-space ROIs against authentic framebuffer
screenshots, including GPU texture/CLUT caches, STP/bit15,
clipping and geometry. Original BIN/CUE, CDSTG, GPU packet
files, VRAM snapshots, screenshots, and every derived
private report must **never** be published in GitHub CI.

## Synthetic tests

`tests/test_bind_private_pcsx_first_frame_evidence.py` adds
**20 ROM-free tests** for coherent first frame binding, exact
three-read native hash identity, multi-frame recordings,
incomplete tails (strict fail versus explicit opt-in),
nonmonotonic VSyncs, expected counts, GP0 or VRAM mutation,
inconsistent preflight counts, independent operator digest
or serial mismatch, atomic/no-clobber private report writing,
symlink refusal, malformed arguments, and metadata privacy.

Passing these tests is a test of modeled input consistency,
**not** a claim that a real PS1 frame or roof/well texture
has been recovered.
