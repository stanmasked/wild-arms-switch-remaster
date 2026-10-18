# Stage 263O — three independently endorsed registry escrow receipts

Stage 263N keeps a private SQLite register of the accepted Stage 263M
two-administrator checkpoint head. This eliminates concurrent forks
**inside that one file**, assuming its externally pinned latest head is
correct. It cannot prove that off-host operators have received that
new head or that the host has not presented different heads to them.

Stage 263O adds **read-only, three-of-three signed escrow comparison**.
All three registered escrow operator keys must endorse the exact same
registry count, head SHA-256, latest accepted checkpoint SHA-256, scope,
128-bit round nonce and previous escrow checkpoint digest. The
operator supplies a separately retained digest of the three **full
signed receipt files**.

## Independent operator signing

Create exact unsigned claim bodies using
`tools.audit_record_witness_escrow_quorum.make_body` with role
`escrow-a`, `escrow-b` or `escrow-c`. The body includes the
versioned schema, role, accepted registry schema, checkpoint scope,
registry event count, registry head digest, latest accepted checkpoint
digest, previous independently retained escrow digest, common round
nonce and `witness_fence_retirement_authorized=false`.

For the first escrow round at registry genesis, the predecessor
MUST be `ESCROW_GENESIS`; the registry count/head and accepted
checkpoint must also equal their known genesis values. For subsequent
rounds, every signer must obtain the same **independently retained
previous bundle digest**. These requirements do not prove that the
claimed "latest" pin really came from an independent channel.

Each operator signs the domain-separated canonical body with a
separate Ed25519 private key using the existing envelope format
`{schema,body,signature_hex}`. The verifier only accepts operator
public keys and their out-of-band PEM SHA-256 pins. It does not
read or create operator private keys.

The three whole-envelope SHA-256 values are combined into one
domain-separated `bundle_digest`, in fixed escrow-a / escrow-b /
escrow-c roles. Retain this bundle digest **outside the registry host
and separate from the custody service**.

## Read-only verification

All thirteen flags and pins should be supplied directly from the
independent operator's archive; do not derive them from the untrusted
host's own files.

```sh
python3 -m tools.audit_record_witness_escrow_quorum \
  /independent-private/accepted-checkpoints.sqlite \
  --checkpoint-tag private-wild-arms-ledger \
  --prior-escrow-sha256 PREVIOUS_INDEPENDENT_ESCROW_HASH \
  --latest-escrow-sha256 THREE_SIGNED_RECEIPTS_BUNDLE_SHA256 \
  --expected-count EXTERNALLY_RETAINED_REGISTRY_COUNT \
  --expected-head EXTERNALLY_RETAINED_REGISTRY_HEAD_SHA256 \
  --expected-checkpoint EXTERNALLY_RETAINED_LAST_CHECKPOINT_SHA256 \
  --escrow-a-signed /operator-a/receipt.json \
  --escrow-a-public /operator-a/public.pem \
  --escrow-a-public-sha256 TRUSTED_A_PEM_SHA256 \
  --escrow-b-signed /operator-b/receipt.json \
  --escrow-b-public /operator-b/public.pem \
  --escrow-b-public-sha256 TRUSTED_B_PEM_SHA256 \
  --escrow-c-signed /operator-c/receipt.json \
  --escrow-c-public /operator-c/public.pem \
  --escrow-c-public-sha256 TRUSTED_C_PEM_SHA256
```

The tool rejects missing or swapped signatures, wrong key pins,
different signed head values, different nonce, predecessor or scope,
duplicate signers (including one Ed25519 DER key repackaged as two
PEM files), invalid receipt fields, a mismatched independently pinned
bundle, missing registry, unexpected schema or corrupted event chain.

After checking every signature, the verifier reads the **entire
accepted checkpoint chain** inside a single BEGIN IMMEDIATE
transaction and compares the exact registry triple and scope
against all three signed receipts and external enrollment. The
transaction rolls back and performs no registry or witness writes.
No signing keys, process command lines or private custody material
are returned.

## Unresolved security limitations

This is three-of-three validation of the receipts **provided to the
verifier**, not a network service and not an authenticated search of
all possible off-host archives. One or more operators may have
signed a conflicting receipt and withheld it. There is no remote
publication protocol, independent physical storage attestation,
append-only hardware escrow or distributed consensus.

Restoring an earlier valid registry **and** an earlier set of valid
three-way receipts **and** the corresponding external "latest" pin
can still pass. The checker does not prove continuous receipt
freshness, detect unprovided signed equivocations or defend against
a compromise of all signing identities.

Successful checks explicitly return FALSE for
`independent_physical_archive_storage_proved`,
`all_possible_conflicting_receipts_discovered`,
`continuous_escrow_freshness_proved`,
`historical_replay_with_old_pins_excluded`,
`global_writer_revocation_proved`,
`witness_fence_retirement_authorized`, and
`witness_fence_retired`.

The 18 synthetic regressions use local Ed25519 and SQLite fixtures
and are not proof of a live production system, PlayStation execution,
or Nintendo Switch game build. PR remains Draft. No negative-outcome
witness-fence release has been implemented.
