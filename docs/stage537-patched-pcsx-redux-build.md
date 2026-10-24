# Stage537 — patched PCSX-Redux build gate

## Purpose

Stage537 takes the Stage536 candidate beyond source-context validation. It fetches the exact upstream PCSX-Redux commit `de4a33e9a69abec4f567ae33567537f867dc2bba`, validates the Stage535 source mapping, applies the queue-reset candidate, then builds the Linux x86_64 emulator and runs the upstream synthetic CD-ROM ISO smoke test and native test suite.

The build uses the upstream-maintained `ghcr.io/grumpycoders/pcsx-redux-build:noble` container image. The build manifest records the pinned source commit, candidate patch SHA-256 and generated AppImage SHA-256. The artifact expires after seven days and is intended for private follow-up validation, not distribution as a Wild Arms game package.

## Data boundary

The workflow does not download, mount, or reference the original Wild Arms BIN/CUE, private savestates, VRAM captures, input traces or screenshots. The emulator's built-in synthetic CD-ROM test ISO is generated only for upstream tests. The artifact contains the patched emulator, a build manifest and test XML, not the original game.

## Acceptance boundary

A successful workflow means the candidate compiles against the pinned source and the included upstream tests pass. It does **not** establish that the original game's response FIFO is now deterministic, that the original game behaves identically, or that any Nintendo Switch runtime is working. Those claims require the separately controlled private neutral/RIGHT replay with CD-ROM logging both disabled and enabled, comparing active response bytes and raw VRAM against the Stage535 baseline.

The Stage536 PR remains Draft until the patched emulator runtime experiment is completed and reviewed.
