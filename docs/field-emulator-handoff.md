# Stage 282 — same-commit NRO + PNG emulator handoff

The Stage-281 NRO0 structural audit, native cross-compile, host core,
reverse-engineering audit, disc analysis and host-reference capture all
passed on commit 086fa21c. Actual emulator runtime remains unverified.

The Switch CI workflow now has two sequential jobs:

1. **build-nro** cross-compiles the synthetic-only homebrew app and
   audits the real NRO0 container. It uploads NRO plus JSON digest.
2. **emulator-handoff** downloads that exact job's artifact, builds the
   host reference generator from the **same GitHub checkout**, runs
   it twice, audits five resulting PNGs, and verifies the native NRO
   digest plus each PNG's compressed/raw SHA-256 before packaging.

The new artifact **wild-arms-field-emulator-handoff** contains:

- wild_arms_field.nro and wild_arms_field.nro.audit.json
- reference/ with 5 synthetic PNG files and capture_manifest.json
- tools/ with the offline PNG comparator and both audit scripts
- bundle_manifest.json with checkout commit, NRO build ID, SHA-256,
  verified frame digests, resolution and expected movement/exit counts
- README.md with explicit instructions for local NeXium/device capture

A new standard-library-only tool, `prepare_field_emulator_bundle.py`,
rejects mismatched manifests, unexpected files, modified reference
images, aliased input/output folders and stale output. The tests
use a **synthetic NRO**, never private original Wild Arms binaries.

When capturing genuine images, extract the artifact and follow its
README, then use the included comparator to measure pixel differences.
Recording the actual emulator version, renderer, controller and tested
source commit remains essential. Neither the artifact nor host-side CI
can demonstrate that an emulator actually executed the NRO.

Host self-tests:
```sh
python3 -m unittest discover -s tools -p 'test_prepare_field_emulator_bundle.py' -v
```
