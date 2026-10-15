# Wild Arms (USA) — preliminary disc layout

Read-only inspection of the user's local disc image confirms ISO9660 volume `WILDARMS` in raw 2352-byte MODE2/Form1 sectors.

- Five top-level directories: `BIN`, `EXE`, `IXA`, `STR`, `SYS`.
- 51 files and 5 directories (excluding root).
- Executables: `/EXE/OPENING.EXE;1`, `/EXE/SCUS_946.08;1`, `/EXE/WILDARMS.EXE;1`.
- Large container candidates: `/BIN/CDEN.BIN;1` (123002880 bytes) and `/BIN/CDSTG.BIN;1` (76021760 bytes).

These are ISO directory metadata only, not decoded asset formats.

Run locally: `python3 tools/inspect_disc.py "/path/to/Wild Arms (USA).bin"`

Never commit the disc image, extracted proprietary assets or BIOS.
