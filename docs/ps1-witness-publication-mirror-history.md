# Stage 263T — complete signed dual-mirror witness history

Stage 263S authenticates one asserted Stage 263R two-mirror snapshot
with two independently pinned Ed25519 administrator public keys. It
does not itself check whether each intermediate publication was
observed in order. Stage 263T adds **complete signed epoch history**.

## Canonical archive

Create one private, canonical JSON archive containing `schema` and
`rounds`. Each round is an object with exactly `mirror-admin-a`
and `mirror-admin-b`, storing the lowercase hex encoding of the
**complete original signed Ed25519 envelopes**, not merely their
inner JSON bodies. The helper `pack(rounds)` constructs this format
from the exact two signed byte strings per epoch.

Every accepted Stage 263Q intake event requires exactly one new
two-admin signed mirror witness:

- Epoch 0 binds both empty publication journals, fixed genesis head,
  `WITNESS_GENESIS` predecessor and `frozen=false`.
- Epoch N binds precisely N complete journal events, the SHA-256 of
  event N, the conflict-frozen state after that event, and the
  domain-separated hash of both complete signed envelopes at epoch N-1.
- Both signed roles must agree on the same scope, nonce, epoch,
  event count, event hash, frozen state and predecessor.
- A nonce cannot be reused in another epoch; signatures and
  public-key DER identities must remain independent.
- The final signed-envelope-pair SHA-256 must equal an external,
  independently retained `latest-witness-sha256`.

The audit supports **up to 32 rounds** (genesis plus 31 event epochs),
with a bounded archive size. Longer histories fail closed until a
new reviewed format is available. The complete file SHA-256 must
also be independently retained.

## Verification

```sh
python3 -m tools.audit_record_witness_publication_mirror_history \
  /archive-a/publications.sqlite \
  /archive-b/publications.sqlite \
  /private/two-admin-signed-history.json SIGNED_HISTORY_FILE_SHA256 \
  --a-count EXTERNALLY_PINNED_A_EVENT_COUNT \
  --a-head EXTERNALLY_PINNED_A_HEAD_SHA256 \
  --b-count EXTERNALLY_PINNED_B_EVENT_COUNT \
  --b-head EXTERNALLY_PINNED_B_HEAD_SHA256 \
  --admin-a-public /operator-a/ed25519-public.pem \
  --admin-a-public-pin INDEPENDENT_A_PUBLIC_SHA256 \
  --admin-b-public /operator-b/ed25519-public.pem \
  --admin-b-public-pin INDEPENDENT_B_PUBLIC_SHA256 \
  --scope private-wild-arms-publication-mirrors \
  --latest-witness-sha256 EXTERNALLY_PINNED_LATEST_SIGNED_PAIR_SHA256
```

Both SQLite files must be private and have different filesystem
(device, inode) identifiers. Both `BEGIN IMMEDIATE` transactions
remain open together while the verifier audits each entire hash
chain and reads its ordered event history; their event rows and
conflict-freeze status must match exactly.

The signed archive is verified against **the event hashes of that
snapshot**, from genesis through every intermediate publication
event. Missing/reordered/duplicated signed epochs, reused nonces,
false conflict flags, mismatched signatures and stale external pins
cause failure, without changing either journal or releasing any
witness fence.

## Security limits

SQLite locks protect against ordinary concurrent writes on the same
host, not privileged file substitution or shared-nothing multi-host
race conditions. The signed epoch number is enforced to be increasing
**within the supplied archive**, but the verifier does not have an
independently protected global monotonic counter. Attackers able
to restore both older journal copies, a previous complete signed
archive **and** matching old external pins can still obtain a
self-consistent positive response.

This is not a deployed remote transparency log, trusted hardware
counter, operator physical-independence proof, global writer
revocation proof or evidence that game code ran on Nintendo Switch.

Success always retains:
`independent_physical_storage_proved=false`,
`trusted_global_monotonic_counter_proved=false`,
`old_complete_history_with_old_pins_excluded=false`,
`all_hidden_equivocations_discovered=false`,
`witness_fence_retirement_authorized=false` and
`witness_fence_retired=false`.

The 20 synthetic tests cover complete signed histories, frozen
conflicts, missing epochs, tampering, nonce replay, pinned tips,
distinct mirrors and a demonstration of the residual old-history
replay threat. This stage never retires a witness fence.
