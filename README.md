# Wild Arms Switch — native-port research scaffold

Independent C++20 core prototype. No copyrighted game assets included.

## Verified host build
```sh
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

## Status
- Deterministic core tick, bounded cursor, rising-edge graphics-mode toggle: implemented and host-tested.
- Experimental asset-free field movement core: cardinal tile walking, wall/boundary collision, facing direction, one-shot-on-entry event/exit triggers and replay tests. **Host CI verification pending**.
- Playable **terminal-only** prototype with a hand-authored original map: `wa_field_demo`. This is **not** original Wild Arms gameplay and is **not** an NRO.
- Nintendo Switch `.nro` build: **not implemented or verified**.
- Original Wild Arms game data parsing and engine compatibility: **not implemented**.

## Experimental field walk (host only)

```sh
cmake -S . -B build
cmake --build build --target wa_field_demo wa_field_core_tests
ctest --test-dir build -R wa_field_core_tests --output-on-failure
./build/wa_field_demo
```

Use W/A/S/D to walk, Q to quit. The ASCII prototype demonstrates deterministic grid collision, an event tile (`!`) and an exit tile (`E`). It has no game assets, disc data, scripted story, combat, rendering, music, saves, or Switch frontend.

See [field core notes](docs/field-core-host-prototype.md).

## Next milestones
1. Inspect user-owned BIN/CUE image locally without committing it.
2. Identify disc layout and filesystem; document resource formats.
3. Add a Switch frontend with libnx and a real render/input loop.
4. Introduce rendering backends for original and HD assets.
5. Reimplement field traversal, event scripting, combat, sound, and saves against reference behavior.

Do not commit or distribute original game files, extracted artwork, music or BIOS.
