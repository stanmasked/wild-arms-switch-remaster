# 0x800D2C44 field reference audit

Verified against user-owned Wild Arms (USA) PS-X EXE. Fifteen selected instructions match the original disc image.

- 0x80078F8C adds register s6 to the loaded base pointer before four stores and a load at +0x54.
- 0x800791BC calls 0x80078DB0 before an LW instruction at 0x800791C8. The v1 value is caller-saved; its provenance must not be assumed to survive.
- 0x80086CE4 loads +0x54 through register v0.

These accesses do not alone establish that all three target the same record. No source game assets are committed.
