# Wild Arms Remake — Stage 365: two earned victories across three NeXium boots

The parent Stage 364 PR #54 proved one actual seven-strike victory, 8 prototype EXP / 12 prototype Gella, and a fresh emulator reload. This stage adds a new independent **test-only route** on an empty emulated SDMC namespace.

## Three separate guest processes

1. **Guest 14:** fresh SDMC; exit autoplay via B, open R training battle, deliver seven *separate actual A edges* against unmodified enemies. Capture VICTORY before B closure, then held-ZL WINS 1, EXP 8, G 12. Check battle-progress.a generation 1, with no B.
2. **Guest 15:** independent process, same SDMC directory. Before fighting, capture held-ZL restored WINS 1 / EXP 8 / G 12. Win another full-HP fight with seven A strikes. Capture VICTORY, close B, then capture WINS 2 / EXP 16 / G 24. Check generation-2 battle-progress.b and byte-identical prior A.
3. **Guest 16:** third process, same SDMC. Before combat, capture restored WINS 2 / EXP 16 / G 24. Open R battle, then B retreat without a strike or reward. Generation-3 A must record 2 wins, 1 retreat, 16 EXP, 24 Gella; generation-2 B must be byte-identical. Unrelated field-save.a/.b must never be written.

The independent auditor tools/audit_nexium_battle_two_victories.py requires exactly eight actual Xvfb PNGs, five immutable committed guest journal copies, and three different labelled guest process PIDs. It validates nested WABJ/WABR CRC32, the exact generation sequence, observed Victory borders, changed reward digits, full panel parity after fresh boots, identical returned field pixels, unchanged committed prior-generation bytes, and SHA-256 evidence.

The companion 13 synthetic tests challenge fake Victory, mutated rewards, CRC tampering, duplicates, frame replacement, absent frames, and forged generations. **Host synthetic fixtures are not proof of NeXium guest execution.** Exact-head real NeXium verification is required.

**Limits:** No original PlayStation content or economy values; 8 EXP and 12 Gella per win are synthetic placeholders. Emulated SDMC storage is not proof against physical Nintendo Switch SD power failures. Keep Draft pending exact-head CI.
