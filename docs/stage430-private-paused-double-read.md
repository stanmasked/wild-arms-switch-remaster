# Stage430 — double-read PS1 VRAM while PCSX-Redux reports paused

## Why Stage429 alone was insufficient

Stage429 safely saves a private 1 MiB PCSX-Redux raw VRAM snapshot, but
the mere fact that it returned exactly 1,048,576 bytes does not establish
that the emulator was paused. If a field animates or the CPU/GPU runs during
capture, parts of memory may be sampled at different moments.

PCSX-Redux documents a read-only `GET /api/v1/execution-flow`
returning a JSON `running` flag. Stage430 provides an optional,
stricter *private-only* capture using the already reviewed Stage429
loopback REST utility.

Hardware/software documentation:
https://pcsx-redux.consoledev.net/web_server/

**PCSX-Redux's web server listens on all interfaces by default.**
The client only requests 127.0.0.1 or [::1], but that does **not**
prevent other computers on the LAN from accessing a server bound to all
interfaces. Use an appropriate OS firewall or isolated machine/network.
Never expose this web server to the public Internet. The tool uses
GET requests only and **will never POST pause/resume/reset/write**.

## Exact capture sequence

For the single operator-requested local emulator instance:

1. GET `/api/v1/execution-flow`: reject unless `running` is **false**.
2. GET `/api/v1/gpu/vram/raw`: read exactly 1,048,576 bytes.
3. GET `/api/v1/execution-flow`: reject unless still **false**.
4. GET `/api/v1/gpu/vram/raw`: read the second full snapshot.
5. GET `/api/v1/execution-flow`: reject unless still **false**.
6. Require exact byte equality between reads one and two. Only then
   publish one private VRAM file and SHA-256 manifest, using Stage429
   no-clobber temporary-file publication and verification.

The execution-flow JSON reply is limited to 8192 bytes, must be valid
UTF-8 with no duplicate keys, and must contain `running` as a **JSON
boolean**. HTML, redirects, remote hosts, timeouts, short/oversized
VRAM files or malformed JSON are rejected. A failed read leaves no
new artifacts.

## Owner-private usage

Pause an authentic game session in Surf Village on PCSX-Redux, enable
its web server, and create a private directory **outside the checkout**:

```sh
mkdir -p /private/WildArms/surf-vram-stable

python tools/capture_private_stable_pcsx_vram.py \
  /private/WildArms/surf-vram-stable \
  --basename surf_map2_pause_a \
  --label 'Surf Village field, operator-paused'

python tools/capture_private_stable_pcsx_vram.py \
  /private/WildArms/surf-vram-stable \
  --basename surf_map2_pause_a --verify-only
```

This is an example path; the actual local private location must exist.
The tool does not run PCSX-Redux, read the operator's screen, pause
the game on its own, or export a GPU command log. It only captures
from an already-running local emulator API.

Files:

- `surf_map2_pause_a.u16le.bin` — identical VRAM bytes from both
  live reads, stored once privately (1024 × 512 × 2 bytes);
- `surf_map2_pause_a.capture.json` — Stage429-compatible metadata,
  adding `snapshot_read_count=2`, `execution_flow_read_count=3`,
  and explicit API-paused/byte-identical flags.

No raw color words, VRAM bytes, original screenshots, disc or PNGs
are emitted to console, GitHub or GitHub Actions.

## Narrow interpretation — do not overstate evidence

Three separate JSON observations of `running=false` cannot prove
that the emulator *never* briefly ran between requests. Equal snapshots
may also occur during an unchanged running scene; conversely some
legitimate hardware behavior can make two paused reads differ.

A stable pair proves only byte-for-byte equality of two captured VRAM
responses **conditional on the endpoint's identity and behavior**.
It does not verify the loaded disc's revision, Surf Village map identity,
the original capture frame number, bit/byte endianness, texture DMA
placement, GP0 draw chronology, CLUT sampling time, or framebuffer
equality. These require independent data and verification.

PCSX-Redux GPU Logger groups commands since the last VSync; a single
game frame may span multiple VSyncs:
https://pcsx-redux.consoledev.net/Debugging/gpu-logger/

Once one stable original VRAM snapshot exists, Stage427 may inspect
candidate palette memory occurrences on private disk. Stage428 also
needs an independently instrumented, complete GP0 packet trace for
the correct frame and cannot infer that trace from the VRAM bytes alone.

## Acceptance gates

- All **16 synthetic-only tests** in
  `tests/test_capture_private_stable_pcsx_vram.py` pass on Python CI.
- Matrix audits and Host Core pass on the exact PR head SHA.
- Only after a real Surf Village session has been captured locally
  may a report claim the first genuine paused double-read result.
- For actual CLUT attribution, verify a draw-time palette sample or
  reliable GPU logger replay rather than trusting post-frame memory
  as a substitute for pixel-accurate rendering.

**This stage implements a conservative capture instrument, not the
original game's map-rendering restoration itself.**
