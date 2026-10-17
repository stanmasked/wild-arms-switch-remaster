# Stage 244 — private capture replay collision preflight

This stage introduces the **read-only** 
\`tools/audit_record_capture_replay.py\`. It reruns the unmodified
stage-243 debugger-provenance checker (which reruns stage 242 and upstream
EXE/temporal audits), and then compares the current submission against:

1. A **verifier-issued challenge object** provided via a separate input.
2. A **previously accepted sessions ledger** provided via a separate input.

This checker detects a mismatch or collision **relative to the supplied
inputs**. It never mutates the ledger, records acceptance, consumes a challenge
or claims that either file was independently authenticated.

**Important: do not generate the challenge in the recorder itself, and do
not let the recorder manage the accepted-session ledger.** Those controls
would let a recorder replace both its nonce and the history, trivially
bypassing this check. For meaningful replay prevention, a verifier must issue
unpredictable one-time challenges **before** the capture and maintain a
separately protected, atomic, durable inventory of spent challenges and
accepted evidence; concurrent verifiers must coordinate acceptance. None of
those operational guarantees are implemented in this audit.

## Input schema

The stage-243 private arguments remain unchanged. The two additional
UTF-8 files contain strict JSON objects, with duplicate JSON keys rejected.

Example challenge (**synthetic values only**):

\`\`\`json
{
  "schema": "wild-arms-ps1-verifier-challenge-v1",
  "session_nonce": "0123456789abcdeffedcba9876543210",
  "verifier_tag": "offline_verifier",
  "capture_kind": "record-slot-samples"
}
\`\`\`

The nonce is exactly 32 lowercase hex characters (128 bits) and not all
zeroes. It must equal the stage-243 session provenance nonce, which that
stage requires to agree with both collector receipts. The verifier tag is
a strictly bounded identifier. The challenge file is bounded to **4096 bytes**.
No issue time, TTL or external signature is inferred or authenticated.

Example local ledger for a verifier with *no* previously accepted captures:

\`\`\`json
{
  "schema": "wild-arms-ps1-accepted-capture-ledger-v1",
  "accepted_sessions": []
}
\`\`\`

Every accepted ledger entry must have **exactly**:

- \`session_nonce\`: a prior captured session's 32-character hex nonce.
- \`provenance_sha256\`: SHA-256 of its exact session-provenance JSON bytes.
- \`before_stream_sha256\`: SHA-256 of exact *before* JSONL bytes.
- \`after_stream_sha256\`: SHA-256 of exact *after* JSONL bytes.

All digest fields are 64 lowercase hex characters. The checker refuses
the current submission if its nonce or any individual evidence digest is
already present in the supplied ledger. Duplicate nonces or digests across
accepted ledger entries are rejected as malformed input. This conservative
rule can reject intentionally identical deterministic captures even when
they are not fraudulent, so use it for evidence-submission validation, not
to infer runtime misbehavior.

Ledger bound: **256 KiB**, at most **512** prior entries. It is a bounded
read-only snapshot, not a transactional database or a proof of completeness.
Removing earlier entries, reordering external acceptance or running two
checks concurrently can bypass the practical replay defense.

## Local usage

\`\`\`sh
python3 -m tools.audit_record_capture_replay \
  /private/WildArms.bin \
  /private/disc-inventory.json \
  /private/temporal-slot-snapshots.json \
  /private/capture-manifest.json \
  /private/before-watch.jsonl \
  /private/after-snapshot.jsonl \
  /private/session-provenance.json \
  /private/before-receipt.json \
  /private/after-receipt.json \
  /private/verifier-issued-challenge.json \
  /private/verifier-accepted-session-ledger.json
\`\`\`

Exit codes:

- **0**: all supplied stage-243 claims consistent, challenge nonce agrees,
  and the submitted nonce/stream/provenance digests do not occur in the
  provided prior ledger.
- **1**: supplied evidence is coherent but stage-243 witness claims conflict,
  the challenge nonce differs or prior submitted evidence is detected.
- **2**: malformed, oversized, incomplete or digest-mismatched private input;
  public JSON only gives \`invalid_private_input\`.

Only counts and conservative booleans appear in CLI output. No private
nonces, hashes, paths, PCs, memory contents, debugger identities, journal
rows, original game data or challenge contents are printed. The test suite
uses **synthetic** fixtures; real disc/PS1 capture files are not uploaded
to GitHub Actions.

The report deliberately keeps these claims **false**:
\`challenge_issuance_independently_authenticated\`,
\`ledger_integrity_independently_authenticated\`,
\`durable_one_time_acceptance_recorded\`,
\`replay_prevention_guaranteed\`,
\`original_ps1_execution_verified\`, and
\`native_switch_game_build_verified\`.

**Future work:** integrate with an independently operated verifier that
handles one-time issuance/atomic consumption and a durable, authenticated
ledger. This stage does not establish the actual Wild Arms record size:
the static multiplication factor \`2708\`, earlier \`364\` estimate and
independent \`88\`-byte initializer must remain separate observations.
