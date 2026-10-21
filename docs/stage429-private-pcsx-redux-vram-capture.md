# Stage429 — private VRAM capture from a real PS1 emulator

## Purpose

Stage426 recovered 112 **candidate** 16-color rows from the owner's
authentic Surf Village CDSTG assets. Stage427 can search a full PS1
VRAM dump for exact occurrences of those rows; Stage428 can check
CLUT coordinates referenced in a separate complete GP0 packet trace.

Until this stage, acquiring the first trustworthy VRAM file was a
manual, poorly constrained step. PCSX-Redux documents a loopback REST
endpoint for the raw GPU VRAM contents:

`GET http://127.0.0.1:8080/api/v1/gpu/vram/raw`

Reference: https://pcsx-redux.consoledev.net/web_server/

Stage429 adds a safe **user-private local capture** plus verification
of the produced file. It does **not** run an emulator in public CI,
ship the owner's game, or claim to have captured the actual Surf
Village VRAM in this PR.

## Reproducible owner-local procedure

1. Run the legally owned original Wild Arms disc in PCSX-Redux on
   the owner's own computer. Navigate to **Surf Village (field map 2)**.
   Use `Debug > GPU > GPU Logger` and enable GPU logging if collecting
   command evidence separately. Remember that a GPU logger 'frame'
   can span more than one VSync when the game is slower.
2. Pause PCSX-Redux at a clearly documented gameplay moment (for
   example, after a VSync) so the VRAM does not change while it is
   downloaded. Record emulator version, game revision and observed
   scene privately. Stage429 **cannot independently verify** that the
   emulator was paused or that map 2 was actually on screen.
3. Enable `Configuration > Emulation > Enable Web Server` in
   PCSX-Redux. By default it listens locally on port 8080. Prefer
   binding to loopback only; this helper explicitly rejects non-loopback
   URLs, proxy routing and redirects.
4. Create a private local output directory, outside the Git checkout.
   Run the following on the same machine as the emulator:

```sh
mkdir -p /private/WildArms/surf-vram-429
python tools/capture_private_pcsx_redux_vram.py \
  /private/WildArms/surf-vram-429 \
  --basename surf_map2_frame_example \
  --label 'Surf Village paused gameplay; frame number unverified'

python tools/capture_private_pcsx_redux_vram.py \
  /private/WildArms/surf-vram-429 \
  --basename surf_map2_frame_example --verify-only
```

The `/private/WildArms/` folder is illustrative; use an existing
owner-private directory on the local machine. No file is created on
GitHub, in Actions, or on a third-party server. The tool does not
transfer the file back to ChatGPT.

## Output and guarantees

- `surf_map2_frame_example.u16le.bin`: exact 1,048,576-byte raw
  VRAM response, intended as 1024x512 little-endian 16-bit words.
- `surf_map2_frame_example.capture.json`: SHA-256, capture UTC time,
  byte count and explicit uncertainty flags; **never contains VRAM
  bytes, palette u16 values, screenshots or graphics**.
- Both files use owner-private permissions (0600 on POSIX), temporary
  files and no-clobber hard links. A failed second publish rolls back
  the first so incomplete pairs are not treated as valid.
- `--verify-only` rechecks the full raw VRAM size and SHA-256 before
  running Stage427 or Stage428 matching. It does not claim to
  authenticate what software originally produced the file.
- The URL must be `http://127.0.0.1:PORT/api/v1/gpu/vram/raw`
  (or bracketed loopback IPv6 `[::1]`). HTTPS, non-loopback
  hosts, credentials, query parameters and redirects are rejected.
- Failed HTTP responses, truncated snapshots and oversized responses
  are rejected without creating private output files.
- Existing outputs are never silently replaced. Supply a new
  basename per capture to preserve repeatability.

Caution: PCSX-Redux documentation specifies VRAM as 1024x512 16bpp,
but the helper **does not independently establish host-side word
endianness or capture provenance**. Confirm the encoding in a
controlled test before treating the `.u16le.bin` filename as proof
of exact little-endian PS1 row interpretation.

## Connection to the previous stages

After obtaining a genuine paused Surf Village capture, privately run:

```sh
python tools/audit_surf_vram_palette_occurrences.py \
  /private/WildArms/CDSTG.BIN \
  /private/WildArms/surf-vram-429/surf_map2_frame_example.u16le.bin \
  --map-index 2 > /private/WildArms/stage427-matches.json
```

Stage428 still requires an **independent complete GP0 packet trace**
with the corresponding frame and the SHA-256 from this capture, in
its documented JSONL format. The capture helper does not extract or
invent a GP0 trace. Raw post-frame VRAM can be overwritten after a
draw; coordinate equality does not guarantee palette bytes present
at draw time. PS1 GPU CLUT caching is another reason not to infer
pixel-accurate color usage solely from a later VRAM snapshot.
References:

- https://pcsx-redux.consoledev.net/Debugging/gpu-logger/
- https://psx-spx.consoledev.net/ps1/gpu/texture-caching/
- https://psx-spx.consoledev.net/dev/ps1/gpu/rendering-attributes/

## CI acceptance criteria

`tests/test_capture_private_pcsx_redux_vram.py` uses synthetic
in-memory responses only. It verifies loopback restrictions, GET and
response sizes, redirects and errors, no-clobber publication, recovery
from partial publication failures, 0600 modes, provenance uncertainty,
verification success and detection of tampered, truncated or
path-traversal metadata.

A green CI result validates the **capture utility**, not an actual
Wild Arms game frame. Original discs, VRAM dumps, GPU command traces
and resulting images always remain owner-private.

**Next milestone:** obtain at least two separately paused authentic
Surf Village captures with recorded emulator build and scene state;
compare metadata hashes privately; capture a GP0 draw trace and
compare against the exact-time CLUT used for one concrete roof/well.
