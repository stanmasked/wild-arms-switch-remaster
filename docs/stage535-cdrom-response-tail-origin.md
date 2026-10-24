# Stage535 — the savestate tail writer is identified

## Result

Stage534 localized the two-byte savestate drift to responseFifo0.payload[8:10], beyond the active payload prefix. Stage535 traced the live serialized queue across 12 VSync samples in three pinned PCSX-Redux runs:

- Neutral, ordinary logging.
- RIGHT, ordinary logging.
- Neutral, CD-ROM debug logging enabled.

At every sample, responseFifo0 had cause value 1, payload byte 0 = 0x22, payload_size = 1 and payload_index = 1. In the ordinary-logging runs, the two inactive bytes varied at all 12 sample points. With CD-ROM debug logging enabled, those bytes were 0x2e00 at all 12 sample points.

The final neutral raw VRAM was byte-identical between the debug and ordinary-logging runs and also matched the Stage532 neutral control. The final RIGHT raw VRAM matched the Stage532 RIGHT capture. This demonstrates that the logging-sensitive tail is not a rendered-frame difference in these runs.

## Immediate writer in pinned upstream source

The exact PCSX-Redux commit remains de4a33e9a69abec4f567ae33567537f867dc2bba.

- [Cause enum](https://github.com/grumpycoders/pcsx-redux/blob/de4a33e9a69abec4f567ae33567537f867dc2bba/src/core/cdrom.h#L166-L173): cause value 1 is DataReady.
- [readInterrupt](https://github.com/grumpycoders/pcsx-redux/blob/de4a33e9a69abec4f567ae33567537f867dc2bba/src/core/cdrom.cc#L251-L267): constructs a local QueueElement named ready, appends only getStatus(), then enqueues it as Cause::DataReady.
- [QueueElement](https://github.com/grumpycoders/pcsx-redux/blob/de4a33e9a69abec4f567ae33567537f867dc2bba/src/core/cdrom.h#L180-L221): payload is a fixed 16-byte array with no initializer. The one-byte push initializes only the first byte; the remaining array bytes are not initialized by this response path.
- [maybeEnqueueResponse](https://github.com/grumpycoders/pcsx-redux/blob/de4a33e9a69abec4f567ae33567537f867dc2bba/src/core/cdrom.cc#L300-L315): copies the entire QueueElement object into the response FIFO.
- [Save-state mapping](https://github.com/grumpycoders/pcsx-redux/blob/de4a33e9a69abec4f567ae33567537f867dc2bba/src/core/sstate.h#L314-L390): the full fixed 16-byte payload is serialized as CDRom responseFifo0.

This is the immediate writer: the DataReady response created by readInterrupt carries an uninitialized tail beyond its declared one-byte payload, and the full array is copied and serialized. The logging-sensitive values are consistent with host-stack residue. The exact prior stack contents that supplied each byte are not traced, and the report does not claim that every queue path has been audited.

The serialized commandExecuting value was 21 during these samples, but that is a separate command-execution field; the response FIFO cause is DataReady (1). These values should not be conflated.

## Engineering implications

- Treat raw savestate hashes as byte-integrity evidence, not as a semantic-state equality test.
- Keep the raw savestates and all values from the inactive tail in owner-only storage; they may contain unintended host-stack residue.
- The Stage534 classifier correctly accepts only differences wholly outside the declared active payload prefix. It does not normalize or rewrite the original evidence.
- A future emulator-side fix would initialize the 16-byte payload storage before copying/serializing it. That would be a separate, explicitly versioned patched-emulator experiment; the pinned evidence build remains unchanged.

## Acceptance

- **Inactive-tail writer localized:** PASS.
- **Debug logging changes tail values:** PASS; 12 distinct samples under ordinary logging versus one repeated value with CD-ROM debug logging.
- **Rendered output affected by debug logging:** NO in this experiment; final neutral VRAM hashes are exact matches.
- **Exact source of each stack-residue byte:** OPEN.
- **All CD-ROM queue paths audited:** OPEN.
- **Internal map index, PS1 hardware parity, Nintendo Switch runtime parity and full remake GPU parity:** still unverified.

The Stage535 raw timeline, logs, final savestates, VRAM snapshots and private manifest are stored in owner-only Google Drive. GitHub contains only the source explanation and synthetic CI tests.
