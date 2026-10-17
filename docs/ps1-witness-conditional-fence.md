# Stage 261 — durable conditional witness fencing

Stage 260 fetched a **fresh, signed** independent witness head but allowed
the witness to advance between its reply and the custodian's local SQLite
commit. Stage 261 adds a **reference two-phase head fence**:

1. Read the current independently signed complete recovery prefix over
   mutual TLS, with a new 128-bit network challenge.
2. Issue an independent **conditional claim**: the witness requires the
   same recovery event count and independent witness-chain hash. In its
   private SQLite BEGIN IMMEDIATE transaction it stores a single durable
   fence owner (domain-separated token SHA-256), SHA-256 of the complete
   authenticated custody request, and the witnessed head version.
3. Only then allow the custody server to execute its stage-259
   reserve/deposit. Its own SQLite BEGIN IMMEDIATE rechecks every
   witnessed recovery event before committing.
4. **After the custody transaction completes** (successful commit or
   rollback), send a separately authenticated **release** request.
   The witness deletes the fence only if the owner token and original
   custody request digest still match.

Both remote claim and release use mutual TLS 1.3, pinned peer leaf
certificates and Ed25519-signed responses binding the action, request
challenge, witness identity, fence owner and custody request digest.
A signed response from another challenge, another request or another
fence cannot be accepted.

While the fence exists, the independent witness's normal recovery
`record()` operation refuses any append under the **same SQLite writer
lock**. This closes the ordinary witness-record race that remained after
stage 260. Multiple simultaneous custody requests cannot both acquire
different owners; only exact duplicate claims are idempotent.

## Reference operations

For the independently administered witness, continue running the
stage-260 one-shot witness listener for each incoming operation:

    python3 -m tools.audit_record_remote_recovery_witness serve-once \
      /witness-private/recovery-witness.sqlite \
      /witness-private/signing-key.pem \
      /witness-private/server-cert.pem \
      /witness-private/server-key.pem \
      /witness-private/client-ca.pem PINNED_CUSTODIAN_CLIENT_LEAF_SHA256 \
      --witness-tag witness01 --port 38491

On the custodian, use the new mode:

    python3 -m tools.audit_record_custodian_tls serve-once-remote-witness-fenced \
      /custodian-private/anchors.sqlite \
      /custodian-private/signing-key.pem \
      /custodian-private/server-cert.pem \
      /custodian-private/server-key.pem \
      /custodian-private/client-ca.pem PINNED_VERIFIER_LEAF_SHA256 \
      witness.example.invalid 38491 witness.example.invalid \
      /custodian-private/witness-tls-client-cert.pem \
      /custodian-private/witness-tls-client-key.pem \
      /custodian-private/witness-trusted-ca.pem \
      PINNED_WITNESS_SERVER_LEAF_SHA256 \
      /custodian-private/pinned-witness-ed25519-public.pem \
      PINNED_WITNESS_ED25519_PUBLIC_PEM_SHA256 \
      --custodian-tag custody01 --witness-tag witness01 --port 38481

A single modifying custody request requires **three separately served
witness TCP connections** in this reference implementation: fresh head,
claim and release. Read-only custody latest requests do not claim a
fence.

## Interrupted operations and limitations

Fences **never expire automatically**. If the custodian crashes after
claim but before release, the witness remains locked, and subsequent
recovery recording or custody writes through the fenced route refuse.
The operator must investigate whether the original custody write
committed, then reconcile the original request ID, token and digest
through an independently authorized recovery process. Stage 261 does
not yet implement administrative clearing of an abandoned fence.

If the custodian SQL write commits but network release fails, the
custodian must not claim overall success to the verifier. Its existing
exact reserved-deposit replay logic supports retry after an
administratively reconciled fence. The durability of the fence favors
safety over availability.

This is **not** a cross-database atomic commit. Witness state can still
change through privileged direct SQLite edits, legacy administration
or a witness operator bypassing the guarded record() function. The
custodian's older server modes and direct Python APIs also remain
available. These must be restricted by OS credentials and service
exposure for the fence to become an enforced operational requirement.

The new fencing server is a one-shot reference, not a deployed
independent service with persistent liveness, distributed transactions,
immutable storage, hardware identity, key rotation or automatic crash
reconciliation. All tests use temporary keys, synthetic data and
loopback TLS. No real original Wild Arms PlayStation execution or
playable Nintendo Switch remaster is demonstrated.
