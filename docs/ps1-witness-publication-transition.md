# Stage 263V — strict signed transition between two publication snapshots

Stage 263U compares two independently pinned archives representing the
**same** moment. Stage 263V checks a **different temporal relationship**:
an earlier accepted journal pair and signed witness history must be an
unchanged, strict prefix of a later accepted journal pair and signed
witness history.

This offline tool does not publish a checkpoint, renew an external pin,
reset journals, or unlock any custody/witness-fence condition.

## Required operator inputs

The operator supplies *four different* private SQLite journal files:
the old mirror pair A/B and the new mirror pair A/B. Duplicate
(device, inode) identities fail closed; path difference alone is
insufficient. The operator separately pins each pair's event count
and journal head SHA-256.

Two complete canonical Stage 263T signed-history files are required,
each with a separately retained SHA-256 of the entire file and a
separately retained SHA-256 of its last complete dual-admin signed
witness pair. Both administrator public keys and their pinned PEM
SHA-256 values must match the originally enrolled signer identities.

Command:

```sh
python3 -m tools.audit_record_witness_publication_transition \
  /operator-old/mirror-a.sqlite \
  /operator-old/mirror-b.sqlite \
  /operator-old/signed-history.json \
  /operator-new/mirror-a.sqlite \
  /operator-new/mirror-b.sqlite \
  /operator-new/signed-history.json \
  --old-count PINNED_OLD_EVENT_COUNT \
  --old-head PINNED_OLD_JOURNAL_HEAD_SHA256 \
  --old-history-sha256 PINNED_OLD_HISTORY_FILE_SHA256 \
  --old-latest-witness-sha256 PINNED_OLD_SIGNED_PAIR_SHA256 \
  --new-count PINNED_NEW_EVENT_COUNT \
  --new-head PINNED_NEW_JOURNAL_HEAD_SHA256 \
  --new-history-sha256 PINNED_NEW_HISTORY_FILE_SHA256 \
  --new-latest-witness-sha256 PINNED_NEW_SIGNED_PAIR_SHA256 \
  --admin-a-public /operator-a/admin-public.pem \
  --admin-a-public-pin PINNED_ADMIN_A_PEM_SHA256 \
  --admin-b-public /operator-b/admin-public.pem \
  --admin-b-public-pin PINNED_ADMIN_B_PEM_SHA256 \
  --scope private-wild-arms-publication-mirrors
```

## Invariants

Each independently pinned pair is first completely audited through
Stage 263T: local hash-linked event history, identical full event
rows between mirror A/B, all Ed25519 signatures and exact signed
predecessor envelope hashes for every historical epoch.

After both pass, Stage 263V requires:

- The new event count is strictly greater than the old event count.
- Both old journals are different files from both new journals, and
  no mirror file aliases another through a hard link.
- Every entire old publication event row equals the corresponding
  prefix row in the new journal.
- Every *exact byte sequence* for both administrators' signed epoch
  envelopes in the old archive is preserved in the new archive,
  without replacing a valid signed genesis or re-signing prior epochs.
- If the old snapshot is conflict-frozen, it cannot have a successor.
- The full new signed history is longer than the prior one; stale,
  missing or changed intermediate epochs fail closed.

The verifier performs **read-only** audits; it does not assemble one
cross-database transaction encompassing all four independent files.
A privileged attacker may substitute file contents between reads,
and remote hosts are not locked by the local SQLite transactions.

## Trust limitations

This tool validates only two **supplied** and independently pinned
points on a claimed timeline. It does not maintain or independently
retrieve a globally authenticated latest journal head. If an attacker
substitutes a *pair* of older yet mutually consistent snapshots along
with their valid signed histories and old external pins, a valid
strict advancement can still be demonstrated without reflecting
the real latest state.

Accordingly every success returns:

`independently_trusted_latest_head_proved=false`;
`old_plus_new_pins_cannot_both_be_replayed_proved=false`;
`independent_physical_archival_custody_proved=false`;
`globally_discovered_equivocations_proved=false`;
`witness_fence_retirement_authorized=false`;
`witness_fence_retired=false`;
`native_switch_game_build_verified=false`.

The 13 synthetic tests include valid one- and three-event
advancements, valid-but-conflicting signed genesis replacement,
stale or missing intermediate epochs, wrong pins, path aliasing,
malformed SQLite headers and private redacted CLI output.
No witness fence is retired by this stage.
