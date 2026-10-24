# Stage536 — PCSX-Redux CD-ROM queue inactive-tail determinism candidate

## Evidence motivating the candidate

The owner-private Stage535 trace sampled `responseFifo0` at 12 VSync checkpoints in three runs. The DataReady response had cause value `1`, payload byte zero `0x22`, `payload_size=1`, and `payload_index=1`. In ordinary neutral and RIGHT runs, the inactive two-byte region at zero-based offsets 8–9 varied at every sample. With CD-ROM debug logging enabled, those same tail bytes were constant (`2e00`) at every sample. The final neutral raw VRAM was byte-identical with and without logging and matched the Stage532 neutral control; RIGHT matched the prior RIGHT VRAM capture.

Pinned PCSX-Redux source at commit `de4a33e9a69abec4f567ae33567537f867dc2bba` shows:

- `src/core/cdrom.h`, `QueueElement`: `payload[16]` and `value` have no member initializer; `clear()` resets flags and size/index but not the payload, value, or `hitMax`.
- `src/core/cdrom.cc`, `readInterrupt`: constructs a local `QueueElement ready`, sets its cause, and appends only the one-byte status value.
- The queue copies the full object; `src/core/sstate.cc` serializes the entire 16-byte payload even when `payload_size=1`.

This makes the inactive-tail bytes consistent with uninitialized/stale host memory being preserved in the savestate. The exact prior host stack contents have not been identified. The trace does **not** show a rendered-output change or prove a gameplay defect.

## Candidate upstream patch

`patches/pcsx-redux/stage536-zero-inactive-cdrom-queue-element.patch` proposes:

1. value-initialize the payload array and value member when a `QueueElement` is created;
2. zero the payload and value on `clear()`;
3. reset `hitMax` on `clear()` so the queue's logical empty/reset state is complete.

The inactive tail is not read as response data when `payload_index >= payload_size`. Clearing it should therefore preserve the active one-byte DataReady response while removing indeterminate/stale bytes from the serialized object. Resetting `hitMax` also matches the method's `clear()` contract and prevents an old consumed-payload flag from leaking into a reused queue element.

This is a **patch candidate only**. It has not been applied to or built into the upstream PCSX-Redux checkout, and the original-disc A/B experiment has not yet been repeated against a patched emulator.

## Regression coverage

The synthetic regression applies the patch with zero fuzz to a small excerpt matching the pinned upstream `QueueElement`, compiles a C++17 harness, and checks default initialization, one-byte DataReady behavior, full-tail clearing, `hitMax` reset and safe queue reuse. It contains no game assets and is not a substitute for an upstream integration build.

## Required next acceptance gates

1. Apply the patch in a separate private PCSX-Redux worktree at the exact pinned commit and build it with the same toolchain/configuration.
2. Repeat the Stage535 neutral and RIGHT captures, with CD-ROM logging both disabled and enabled.
3. Verify that the active response fields and raw VRAM remain unchanged relative to the corresponding unpatched runs, while inactive payload tail bytes are zero after construction/clear and savestate outputs no longer differ solely because of this tail.
4. Audit other `QueueElement` creation and clear paths, and test CD-ROM command/response regressions before treating the candidate as upstream-ready.

Original BIN/CUE, savestates, raw VRAM, emulator binaries, logs and private hashes remain in owner-only Drive. Public CI contains only synthetic source excerpts and tests.
