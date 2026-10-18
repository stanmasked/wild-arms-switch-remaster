# Stage 263P — signed multi-round escrow continuity and supplied-archive comparisons

Stage 263O verifies that **three separately pinned Ed25519 operator
keys** agree on a *single* checkpoint from the Stage 263N accepted-head
registry. A single-round comparison cannot detect missing intermediate
archived checkpoints or show that the operator has the complete history
between genesis and the currently accepted registry head.

Stage 263P adds `tools.audit_record_witness_escrow_history`, a
**read-only, retrospective** verifier of a privately stored *sequence*
of signed three-operator receipt bundles. It has no `init`, `delete`,
`reset`, `accept` or witness-fence release operation.

## Canonical signed archive

The operator preserves exact Stage 263O signed envelope bytes for
every event, starting with the mandatory **genesis** receipt round.
Each archive is compact canonical JSON with sorted keys, one final
newline and schema
`wild-arms-ps1-three-operator-escrow-history-v1`.

The file contains `rounds`, an ordered list of objects, each
containing exactly `escrow-a`, `escrow-b` and `escrow-c`. Each
value is the lowercase hex encoding of the exact signed receipt file
bytes, *not* the JSON body extracted from the envelope. The operator
may build the file using the `pack(rounds)` helper with a list of
three-role byte dictionaries, then independently retain the SHA-256
of the complete archive file.

Maximum 32 rounds (genesis plus 31 accepted checkpoints) and a bounded
overall archive size. Larger histories **fail closed** pending a new
reviewed format; no missing rounds are silently ignored.

## Checks

Verification independently validates:

- The whole archive's SHA-256 against a separately supplied external
  enrollment, strict canonical JSON, unique keys, bounded arrays and
  exactly three signed roles per round.
- All three Ed25519 signatures in **every** round, distinct DER public
  keys even when PEM formatting differs, correct schema, required
  fields, safety declarations and shared 128-bit nonce.
- A signed **genesis** round matching the registry genesis SHA-256,
  predecessor escrow genesis and Stage 263M checkpoint genesis.
- For every accepted Stage 263N event `i`, **exactly one** signed
  round `i` with the event's actual SHA-256, latest accepted checkpoint
  SHA-256 and the same pinned registry scope.
- The signed predecessor of each escrow round equals the
  domain-separated SHA-256 of the previous trio of full signed
  envelopes. Nonces may not repeat across rounds.
- The final escrow round bundle digest equals the independently
  retained current escrow tip. The accepted registry's count/head and
  latest checkpoint also must equal independent external pins.

The entire registry chain is audited under one SQLite `BEGIN
IMMEDIATE` snapshot. The tool then verifies the signed archives
against the exact event hashes from that snapshot. It does not
modify registry or custody data.

## Optional second independently pinned archive

A second archive can be passed using
`--comparison-history` and `--comparison-sha256`. The verifier
requires **both** parameters or neither. It cryptographically checks
both complete histories against the same current registry history and
escrow tip, and refuses different signed round hashes or any
inconsistent intermediate round.

This checks two **supplied** archives; it is not a way to search
unknown servers for unsubmitted archives or privately signed forks.

Example:

```sh
python3 -m tools.audit_record_witness_escrow_history \
  /independent-private/accepted-checkpoints.sqlite \
  /independent-private/signed-history-a.json \
  INDEPENDENTLY_PINNED_HISTORY_A_SHA256 \
  --checkpoint-tag private-wild-arms-ledger \
  --expected-count CURRENT_REGISTRY_COUNT \
  --expected-head CURRENT_REGISTRY_HEAD_SHA256 \
  --expected-checkpoint CURRENT_ACCEPTED_CHECKPOINT_SHA256 \
  --latest-escrow-sha256 CURRENT_THREE_OPERATOR_ESCROW_BUNDLE_SHA256 \
  --escrow-a-public /operator-a/public.pem \
  --escrow-a-public-sha256 PINNED_A_PEM_SHA256 \
  --escrow-b-public /operator-b/public.pem \
  --escrow-b-public-sha256 PINNED_B_PEM_SHA256 \
  --escrow-c-public /operator-c/public.pem \
  --escrow-c-public-sha256 PINNED_C_PEM_SHA256 \
  --comparison-history /operator-other/history.json \
  --comparison-sha256 INDEPENDENTLY_PINNED_HISTORY_B_SHA256
```

The CLI prints only a bounded summary: number of verified rounds,
registry event count and the final escrow digest. It does not output
private signed receipt bytes, nonce values or signatures.

## Trust boundary

This audit is **not** an independently operated escrow service or an
append-only remote transparency log. It proves only that *presented*
archive files satisfy the consistency rules against the *presented*
independently pinned current registry. An attacker who can restore an
old registry and substitute old signed receipts **and** old external
pins can still produce a passing audit. The tool cannot determine that
all operators archived their materials at different physical sites,
that a hidden conflicting archive exists, or that the current escrow
digest is the latest value accepted globally.

The registry snapshot and subsequent signature verification also do
not lock remote archives or prevent a privileged actor from modifying
the registry immediately after the transaction ends. The receipt
archive cannot prove the original observer truly executed, that all
OS writers were permanently disabled, or that Nintendo Switch gameplay
has been validated.

Accordingly, every successful report sets these flags to false:
`independent_physical_archive_storage_proved`,
`all_conflicting_archives_discovered`,
`continuous_escrow_latest_tip_proved`,
`old_registry_plus_old_external_pins_excluded`,
`witness_fence_retirement_authorized`, and
`witness_fence_retired`.

The 20 synthetic tests exercise multi-round continuity, missing and
swapped rounds, nonce reuse, conflicting signed receipts, two-archive
comparisons, tampered JSON, replay with old external pins, and private
CLI behavior. **No unresolved witness fence is retired.**
