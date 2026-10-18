# Stage 263M — two-independent-admin replay-head checkpoints

Stage 263L added a private hash-linked SQLite replay ledger for signed
observer-run claims, with an expected externally retained (count, head)
on each enrollment. That detects ordinary replay or rollback **only
when the operator supplies the current external head**. Stage 263M
adds an independently verified checkpoint signed by *two different*
Ed25519 administrator public keys, pinning an exact inspected ledger
head and referring to the preceding checkpoint's independently
retained digest.

This is an observational **read-only** verification. It neither signs
on behalf of administrators nor modifies the ledger, custody DB,
witness DB, running processes or witness fence.

## Independent two-admin signing workflow

After Stage 263L `enroll` returns a new count/head, two
separately controlled administrators each verify that value against
their own independent evidence channel, agree on a unique
128-bit (32 lowercase hex character) checkpoint nonce, and sign:

```json
{
  "schema": "wild-arms-ps1-two-admin-replay-head-claim-v1",
  "admin_role": "admin-a",
  "checkpoint_tag": "private-wild-arms-ledger",
  "ledger_schema": "wild-arms-ps1-observer-run-replay-ledger-v1",
  "ledger_count": 1,
  "ledger_head_sha256": "AN_ACTUAL_64_CHARACTER_LOWERCASE_HEX_SHA256",
  "prior_checkpoint_sha256": "INDEPENDENTLY_RETAINED_PRIOR_CHECKPOINT_HASH",
  "checkpoint_nonce": "32_CHARACTER_RANDOM_LOWERCASE_HEX_NONCE",
  "witness_fence_retirement_authorized": false
}
```

The example is explanatory: replace placeholders with valid values
before signing. The second administrator signs identical fields except
`admin_role="admin-b"`. The tags, exact sequence/head, prior
checkpoint hash and nonce MUST match between both statements.
For the first checkpoint, use
`tools.audit_record_witness_replay_head_checkpoint.ANCHOR_GENESIS`
as the prior anchor. Each signature must be created **offline, on
separate operator-controlled machines**, over domain-separated
`DOMAIN + _canonical(body)` using pinned Ed25519 public keys.
The tool does not handle administrator private keys.

The signed envelopes have the same canonical format as the other
research witness tools: `{"schema": SCHEMA, "body": BODY,
"signature_hex": LOWERCASE_ED25519_SIGNATURE}`. Each administrator
must independently check the intended body before signing.

After both signatures exist, independently compute the checkpoint
digest from their exact signed envelope bytes:

```python
from tools.audit_record_witness_replay_head_checkpoint import checkpoint_digest

checkpoint_hash = checkpoint_digest(signed_admin_a_bytes,
                                    signed_admin_b_bytes)
```

**Store that digest as the new latest trusted checkpoint through a
channel separate from the custody/replay-journal host.** Do not
automatically accept an untrusted service's computed value as proof
of current escrow. The verified digest is domain-separated and binds
both signed envelopes in their designated roles.

## Read-only verification CLI

```sh
python3 -m tools.audit_record_witness_replay_head_checkpoint \
  /independent-private/observer-replay.sqlite \
  /independent-private/admin-a-signed-head.json \
  /independent-private/admin-a-public.pem PINNED_ADMIN_A_PEM_SHA256 \
  /independent-private/admin-b-signed-head.json \
  /independent-private/admin-b-public.pem PINNED_ADMIN_B_PEM_SHA256 \
  --checkpoint-tag private-wild-arms-ledger \
  --prior-checkpoint-sha256 EXTERNALLY_RETAINED_PRIOR_CHECKPOINT_SHA256 \
  --latest-checkpoint-sha256 EXTERNALLY_RETAINED_LATEST_CHECKPOINT_SHA256
```

Verification requires:

- Both *distinct*, pinned Ed25519 public keys authenticate their
  domain-separated claim envelopes. Distinctness compares actual
  decoded public-key DER bytes, not merely possibly reformatted PEM
  file hashes.
- Each envelope has exactly the expected fields, safe
  `witness_fence_retirement_authorized=false`, correct signing role,
  identical journal count/head/scope/nonce and exactly the required
  predecessor checkpoint hash.
- The independently retained latest checkpoint SHA-256 equals the
  domain-separated digest of **both entire signed envelopes**.
- The replay journal exists as a private, securely owned SQLite
  object. Under `BEGIN IMMEDIATE`, the verifier audits the full
  Stage 263L event hash chain and matches the signed count/head.
  The transaction is rolled back, without a write or fence release.

Signed checkpoints are **not** privileged tokens for reconciliation:
successful verification always asserts
`continuous_external_head_escrow_proved=false`,
`historical_replay_with_old_pins_excluded=false`,
`hardware_backed_rollback_prevention_proved=false`,
`tool_execution_independently_proved=false`,
`witness_fence_retirement_authorized=false` and
`witness_fence_retired=false`.

## Threat boundary and limitations

Two independent signatures make it harder for one compromised signing
identity to forge a **new** approved head, but do not by themselves
prevent rollback of the ledger with replay of **old, valid** signed
checkpoints. If an attacker can substitute both the old database and
an older "latest" checkpoint pin, that old pair can still pass. A
persistent independent off-host pointer to the true latest digest,
validated by a real second party, remains mandatory.

The verifier cannot independently prove that administrators signed on
different physical machines, that the signing operators saw genuine
host observations, or that a current live service's write paths were
permanently revoked. An administrator may also knowingly sign a false
head. A private SQLite file and signed head are not a TPM monotonic
counter, secure transparency log, consensus quorum or proof of
privileged host integrity.

The synthetic tests use locally generated Ed25519 administrator keys
and temporary SQLite fixtures. They do **not** establish production
host quiescence, PS1 execution, or playable Nintendo Switch gameplay.
No unresolved witness fence is retired by this stage.
