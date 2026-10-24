# Stage537 — patched PCSX-Redux build gate

## Purpose

Stage537 takes the Stage536 candidate beyond source-context validation. It fetches the exact upstream PCSX-Redux commit `de4a33e9a69abec4f567ae33567537f867dc2bba`, validates the Stage535 source mapping, applies the queue-reset candidate, then builds the Linux x86_64 emulator and runs the upstream synthetic CD-ROM ISO smoke test and native test suite.

The build uses the upstream-maintained `ghcr.io/grumpycoders/pcsx-redux-build:noble` container image. The build manifest records the pinned source commit, candidate patch SHA-256 and generated AppImage SHA-256. The artifact expires after seven days and is intended for private follow-up validation, not distribution as a Wild Arms game package.

## Data boundary

The workflow does not download, mount, or reference the original Wild Arms BIN/CUE, private savestates, VRAM captures, input traces or screenshots. The emulator's built-in synthetic CD-ROM test ISO is generated only for upstream tests. The artifact contains the patched emulator, a build manifest and test XML, not the original game.

## Acceptance boundary

A successful workflow means the candidate compiles against the pinned source and the included upstream tests pass. It does **not** establish that the original game's response FIFO is now deterministic, that the original game behaves identically, or that any Nintendo Switch runtime is working. Those claims require the separately controlled private neutral/RIGHT replay with CD-ROM logging both disabled and enabled, comparing active response bytes and raw VRAM against the Stage535 baseline.

The Stage536 PR remains Draft until the patched emulator runtime experiment is completed and reviewed.

## Review note — 2026-10-24

Before treating the build as complete, the workflow was corrected to avoid deriving a build label from the Wild Arms repository's `GITHUB_SHA` inside a separate PCSX-Redux checkout. The version label now uses the pinned upstream commit prefix. The AppDir desktop file's `Exec` path is normalized before `linuxdeploy`, matching the pinned upstream Linux CI packaging step.

The workflow is constrained to PR #150's Stage537 branch or manual dispatch, and uses a concurrency group to avoid future duplicate full builds from stacked PRs. The Stage536 branch's build job was observed as skipped by design; its host and disc-analysis tests passed on head `8a20b546cc8413ff8c5a1d835b738b1eb91bf9db`.

Two older full-build runs (40079639906 and 40079641031) remained reported as in progress at the main emulator compile step. They use the previous workflow revision and are not acceptance evidence for the corrected packaging step. A successful build from the corrected Stage537 head, a verified retained artifact, and the private original-game A/B replay are still required.
