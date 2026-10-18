# Stage 263U — comparison of independently pinned signed mirror archives

Stage 263T validates one complete history of two-admin Ed25519
witnesses for the exact publication events in two private journals.
Stage 263U compares **two** such supplied histories. Each has
independently supplied SHA-256 commitments for its complete archive
file and its latest signed witness-pair digest.

`tools.audit_record_witness_publication_archive_compare` runs the
full Stage 263T validation separately for each input archive against
the same independently pinned Stage 263Q journal pair. This includes
every historical event SHA-256, signatures and administrator keys,
round numbering, predecessor links, nonces, and conflict-freeze state.

The verifier then compares **every exact signed envelope** at every
epoch, and rejects any divergence even if both histories have valid
signatures and internally consistent SHA-256 chains. A different
signature nonce at the genesis epoch, carried through later
legitimately signed successor epochs, is an example of a conflict
between two individually verifiable histories.

## Usage

```sh
python3 -m tools.audit_record_witness_publication_archive_compare \
  /archive-a/publications.sqlite \
  /archive-b/publications.sqlite \
  /operator-a/signed-history.json INDEPENDENTLY_PINNED_HISTORY_A_SHA256 \
  /operator-b/signed-history.json INDEPENDENTLY_PINNED_HISTORY_B_SHA256 \
  --a-count PINNED_MIRROR_A_COUNT \
  --a-head PINNED_MIRROR_A_HEAD_SHA256 \
  --b-count PINNED_MIRROR_B_COUNT \
  --b-head PINNED_MIRROR_B_HEAD_SHA256 \
  --admin-a-public /operator-a/admin-public.pem \
  --admin-a-public-pin PINNED_ADMIN_A_PUBLIC_PEM_SHA256 \
  --admin-b-public /operator-b/admin-public.pem \
  --admin-b-public-pin PINNED_ADMIN_B_PUBLIC_PEM_SHA256 \
  --scope private-wild-arms-publication-mirrors \
  --first-latest-witness-sha256 EXTERNAL_ARCHIVE_A_LATEST_SIGNED_PAIR_SHA256 \
  --second-latest-witness-sha256 EXTERNAL_ARCHIVE_B_LATEST_SIGNED_PAIR_SHA256
```

All supplied files must be private. File SHA-256 and latest witness
digests must be retained through operator-controlled independent
channels, not computed only from a potentially compromised custody
machine. Both journals and archives are **read-only**; no publishing,
reconciliation or unlocking occurs.

A positive response asserts only that both supplied archives
independently pass Stage 263T validation and contain the same entire
sequence of exact signed epochs.

## Residual threats

- Two independently pinned files do **not** prove physically separate
  storage or independence of the operators who supplied them.
- The verifier does not search other archives or determine whether
  withheld, conflicting signed copies exist.
- If an attacker replaces both journals and both archives with older
  valid copies **and** also substitutes old external current pins,
  the old histories may still verify as matching.
- Comparing two snapshots is not a distributed consensus protocol or
  a trusted global monotonic counter. Each Stage 263T validation
  reopens local SQLite snapshots; no cross-archive remote atomicity
  is asserted.
- A signed claim does not prove authentic process execution, durable
  Linux writer revocation, valid PS1 game traces, or Switch gameplay.

Every success explicitly keeps
`separate_archive_storage_proved=false`,
`all_conflicting_signed_archives_discovered=false`,
`externally_enrolled_tips_are_globally_latest_proved=false`,
`synchronized_old_archives_and_old_pins_excluded=false`,
`witness_fence_retirement_authorized=false`,
`witness_fence_retired=false`.

The 12 synthetic regressions cover matching genesis, nonempty and
conflict-frozen histories; two genuinely valid but conflicting
signatures; invalid/missing external pins, wrong key bindings,
incomplete archives, shared mirror paths, tampered signatures,
confidential CLI output and the explicit rollback limitation.
This stage does not release an indeterminate witness fence.
