# Stage 281 — static NRO0 executable integrity audit

The Switch NRO CI workflow previously checked only whether its `.nro`
output existed and was nonempty. The new standard-library tool
`tools/audit_switch_nro.py` validates the Nintendo Switch homebrew
NRO0 container and creates a SHA-256 JSON manifest to accompany it.

The format contract is the official open-source libnx `nro.h`, as used
by switchbrew's `elf2nro` tool:
- 16-byte NroStart followed by NRO0 header at file offset 0x10.
- Declared executable image size and three text/rodata/data segments,
  each with offset and size; BSS metadata is recorded.
- Optional ASET trailer following the executable image. Its icon,
  NACP and RomFS sections use relative 64-bit offsets and sizes.
- All segment/asset ranges must fit within the real file and not
  overlap. Header version and flags must be supported.

The manifest includes the file digest, executable size, build ID and
section layout. Synthetic Python tests reject corrupt headers,
truncated files, overlapping and out-of-range segments/assets.
The Switch build workflow runs this audit after `make -C switch`
and uploads both the NRO and its audit JSON as one artifact.

Local usage:

```sh
python3 -m unittest discover -s tools -p 'test_audit_switch_nro.py' -v
python3 tools/audit_switch_nro.py switch/wild_arms_field.nro \
  --json switch/wild_arms_field.nro.audit.json
```

**This is a static file-integrity check**; NRO0 integrity does not
prove successful execution, timing, controller support, framebuffer
display or actual compatibility with NeXium/real Nintendo Switch.
All maps/art are original synthetic test data. No Wild Arms ROM,
disc sectors or BIOS are included.
