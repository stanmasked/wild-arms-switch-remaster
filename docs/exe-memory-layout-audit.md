# Wild Arms main EXE memory declaration audit

Verified locally against the user's original **Wild Arms (USA)** raw MODE2/Form1 image.

| PS-X EXE header property | Value |
|---|---|
| Load start | `0x80011420` |
| Load size | `0x000C1800` |
| Load end (exclusive) | `0x800D2C20` |
| Header BSS address | `0x00000000` |
| Header BSS size | `0x00000000` |
| Investigated global address | `0x800D2C3C` |
| Difference from EXE load end | `0x1C` = 28 bytes |

**Important correction to previous hypothesis:** The target is outside the EXE load image, but the PS-X EXE header does not declare any BSS region. Therefore calling this memory location "confirmed BSS" is unsupported. It might be dynamically managed or cleared by custom boot code, but neither has been established.

The existing adjacent-pair scan reported 39 direct reads of this global and zero direct stores; this is not a whole-program proof that it is never written. Indirect stores, nonadjacent address construction, overlay writers, and boot-time initialization remain possible.

Reproduce without committing game assets:

```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 tools/audit_exe_memory.py 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Local synthetic and sector analysis tests: 19 passed at the time of this audit; GitHub Actions status not separately verified.
