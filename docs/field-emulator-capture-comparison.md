# Stage 276 — emulator screenshot comparison interface

The Stage-274 host reference PNG archive is available from the Field
capture workflow. Stage-275 builds added on-device autoplay with five
named checkpoints. Actual Switch emulator execution is NOT yet verified.

Use tools/compare_field_emulator_png.py when genuine emulator screenshots
are available. Extract the host reference archive and create a separate
directory for real screenshots. Capture a 1280x720 game framebuffer
without title bars or scaling, and name the five PNGs exactly:

- 00_area0_start.png
- 01_area0_event.png
- 02_area0_exit.png
- 03_area1_start.png
- 04_area0_return.png

Then compare with:

```sh
python3 tools/compare_field_emulator_png.py \
  --reference field-references \
  --manifest field-references/capture_manifest.json \
  --observed emulator-captures \
  --report emulator-diff/report.json \
  --capture-label 'NeXium local test' --write-diffs
```

The comparator accepts noninterlaced 8-bit RGB/RGBA PNG with standard
PNG filters 0-4. CRC, dimensions and reference SHA-256 are verified.
By default it requires exact RGB pixels; --max-channel-delta and
--max-changed-pixels optionally permit a documented tolerance.
It reports every scene's changed-pixel count and maximum channel delta,
and can export bright-red difference masks in emulator-diff/pixel-diffs/.

**Important:** A successful comparison does not prove that inputs
were captured from a real emulator. The tool records supplied evidence
as unverified operator input; the origin, emulator version, graphics
backend and source commit must be documented separately. The CI
unit tests use invented tiny PNGs and do not run any emulator.

CI self-tests: python3 -m unittest discover -s tools -p
'test_field_capture_compare.py' -v
