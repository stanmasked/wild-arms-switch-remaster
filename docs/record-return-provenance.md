# Record pointer returned from initializer: confirmed link

Analyzed the user-owned Wild Arms (USA) PS-X EXE (raw MODE2/Form1 image) without committing proprietary binaries.

Seven exact MIPS words independently verified on the original image:

| PC | MIPS | Consequence |
|---|---|---|
| 0x80078E48 | addu v0,s0,zero | Callee returns computed record pointer in v0 |
| 0x80078E64 | jr ra | Function return |
| 0x80078E68 | nop | Return delay slot |
| 0x800791BC | jal 0x80078DB0 | Call record initializer |
| 0x800791C0 | addiu a3,zero,1 | JAL delay slot |
| 0x800791C4 | addu v1,v0,zero | Explicitly copy returned pointer |
| 0x800791C8 | lw s3,0x54(v1) | Load field +0x54 of the returned record |

This resolves the previous register-provenance uncertainty: the relevant v1 is explicitly overwritten after JAL; it is not assumed to survive the call. The caller at 0x800791BC receives the record pointer returned by 0x80078DB0, whose earlier analysis established the 88-byte index step and base-pointer variable 0x800D2C44.

The runtime record count, semantic field type, and allocation remain undetermined. Static matching does not establish scene reachability.

Reproduce on a local user-owned image:
```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 -m tools.verify_record_return 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_verify_record_return.py' -v
```
Five local synthetic tests passed. Original image exact signature verification passed.
