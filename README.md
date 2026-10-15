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
- Nintendo Switch `.nro` build: **not implemented or verified**.
- Original Wild Arms game data parsing and engine compatibility: **not implemented**.

## Next milestones
1. Inspect user-owned BIN/CUE image locally without committing it.
2. Identify disc layout and filesystem; document resource formats.
3. Add a Switch frontend with libnx and a real render/input loop.
4. Introduce rendering backends for original and HD assets.
5. Reimplement field traversal, event scripting, combat, sound, and saves against reference behavior.

Do not commit or distribute original game files, extracted artwork, music or BIOS.
