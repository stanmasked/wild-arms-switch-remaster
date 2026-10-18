# Stage 263S — two independently signed mirror snapshot witnesses

This stage adds a read-only two-administrator Ed25519 check for the
**same, fully verified** pair of Stage 263R publication-intake mirrors.
The signatures authenticate the administrators' *claims*, not the
physical location of journals or the latest state of an independent
remote service.

## Independent operator procedure

After independently inspecting both Stage 263Q journals, operators
prepare two canonical unsigned claim bodies with
`tools.audit_record_witness_publication_mirror_witness.make_body`.
The roles must be `mirror-admin-a` and `mirror-admin-b`.
Each body records the identical:

- Enrollment scope and operator-agreed observation epoch.
- Publication event count and complete chain-head SHA-256.
- Whether the journals are frozen due to signed equivocation.
- SHA-256 of the preceding externally stored signed witness bundle.
- Common 128-bit lowercase hex nonce.
- Explicit `witness_fence_retirement_authorized=false`.

At epoch zero, the claim must bind the empty genesis history, the
unfrozen state and the fixed `WITNESS_GENESIS` predecessor.
Do not use epoch zero for a subsequent observation.

Sign each complete body with separately controlled Ed25519 private
keys using the already established domain-separated envelope
`{schema,body,signature_hex}` of
`audit_record_witness_fence_reconciliation._sign`.
The verifier never accepts private keys and does not create
administrator signatures.

Compute `witness_digest(signed_admin_a, signed_admin_b)` over the
**complete signed envelope bytes**, then independently retain
the digest and predecessor through a separate operator-controlled
channel. A digest printed by the same custody host is **not**
independent enrollment. The epoch is operator supplied; the
verifier cannot establish globally increasing epoch order.

## Verification CLI

```sh
python3 -m tools.audit_record_witness_publication_mirror_witness \
  /archive-a/publications.sqlite \
  /archive-b/publications.sqlite \
  --a-count PINNED_A_EVENT_COUNT \
  --a-head PINNED_A_HEAD_SHA256 \
  --b-count PINNED_B_EVENT_COUNT \
  --b-head PINNED_B_HEAD_SHA256 \
  --admin-a-signed /archive-a/admin-a-signed-witness.json \
  --admin-a-public /archive-a/admin-a-public.pem \
  --admin-a-public-pin PINNED_ADMIN_A_PUBLIC_SHA256 \
  --admin-b-signed /archive-b/admin-b-signed-witness.json \
  --admin-b-public /archive-b/admin-b-public.pem \
  --admin-b-public-pin PINNED_ADMIN_B_PUBLIC_SHA256 \
  --scope private-wild-arms-publication-mirrors \
  --prior-witness-sha256 INDEPENDENT_PREVIOUS_WITNESS_SHA256 \
  --latest-witness-sha256 INDEPENDENT_LATEST_WITNESS_SHA256
```

The verifier authenticates both role-specific statements against
**distinct decoded DER Ed25519 public key material** and their
independently pinned PEM SHA-256. Signed epoch, count, head,
conflict-frozen state, predecessor, nonce and scope must match
exactly. The full two-envelope digest must match a separately
retained SHA-256.

It then reruns the entire Stage 263R mirror check, including
independent count/head pins, full chain equality, avoidance of
same-inode aliases, and equality of conflict-frozen states. Signed
event count, head and conflict state must match the observed result.

The verifier performs no changes to either journal, accepted
checkpoint registry, witness/custody SQLite, signing-key records or
release conditions. Every success explicitly retains:

- `independent_physical_witness_storage_proved=false`
- `observation_epoch_is_globally_monotonic_proved=false`
- `continuous_freshness_or_rollback_exclusion_proved=false`
- `hidden_conflicting_witnesses_excluded=false`
- `witness_fence_retirement_authorized=false`
- `witness_fence_retired=false`

## Limitations

This is still an **operator-driven offline claim verifier**.
An attacker with an older valid mirror pair, both older signatures
and corresponding older *external* pins can present a self-consistent
rollback. Signatures alone do not establish an authenticated globally
current version, a secure monotonic counter or remote append-only
transparency service. The verifier cannot prove the signers are on
separate machines, that old conflicting signatures do not exist, or
that independent archives remain continuously available.

The 16 synthetic tests cover correct genesis and advanced/frozen
snapshots, scope/nonce/pin tampering, conflicting administrators,
substituted public keys, rewrapped PEM identities, stale local mirrors,
wrong epoch constraints and private CLI reporting. These tests do
not demonstrate PS1 gameplay or a playable Nintendo Switch build.
