# Stage 258 — signed witness gate for administrative recovery

Stage 257 detects a rollback only when a witness verification is requested explicitly. Stage 258 adds **an opt-in guarded administrative recovery**. The current independently signed recovery high-water is checked in the same custodian SQLite BEGIN IMMEDIATE transaction as retirement of the orphaned reservation.

## Independent signed genesis

Before the first administrative recovery, the independent witness operator must explicitly initialize its private database and sign its empty head:

    python3 -m tools.audit_record_recovery_witness initialize /witness-private/recovery-witness.sqlite
    python3 -m tools.audit_record_recovery_witness sign /witness-private/recovery-witness.sqlite /witness-private/private-ed25519.pem /witness-private/genesis-signed.json --witness-tag witness01

The empty signed head has recovery count 0 and the domain-specific GENESIS hashes. Merely placing a database in a different directory does not establish independent control. The verifying operator must provision the public PEM fingerprint independently of the incoming signed receipt.

## Guarded administrative recovery

After the usual two independent stage-256 administrator approvals, use the new recover-guarded subcommand with the same arguments as recover, followed by these four arguments:

- The separately controlled independent witness SQLite database path.
- A private **current signed witness receipt** (signed Ed25519 envelope).
- The pinned witness public PEM path.
- Its externally trusted exact-file SHA-256 fingerprint.

Include the expected --witness-tag. The guarded interface authenticates the exact independently retained witness head, verifies its signer and freshness relative to that witness database, then opens the custodian writer transaction.

Within the **same local transaction** it validates the full custody ledger, checks every administrative recovery event against the original retained custody checkpoint receipt, and requires an **exact** match to the signed witnessed journal prefix. Any rollback, divergence, missing event, or unacknowledged newer event blocks retirement. The two-admin approvals and exact orphan ownership are also checked before the atomic commit.

A successful guarded recovery leaves one new administrative recovery event in the custodian database, which the witness has not yet acknowledged. Before any subsequent guarded recovery, the independently administered operator must perform stage 257's capture, record and sign workflow, delivering the new signed current witness receipt.

The witness cannot be silently reinitialized: the initialize operation checks a preexisting event sequence and does not delete or reset it.

## Error handling and limitations

Missing witness enrollment, substituted public keys, bad signature, stale signed receipt, truncated journal, fork, unsafe private input and conflicting concurrent recovery all fail closed without retiring the orphaned reservation. The original recovery CLI remains available for backward compatibility and **bypasses the witness guard**; operators must isolate older administrative entry points and direct SQLite writes to rely on the new interface.

The witness is separately authenticated **before** entering the custodian transaction. Another independently controlled witness writer could advance its head after that check. The custody-journal check and its local update are SQLite-atomic, but there is **no cross-database atomic commit, authenticated witness lease or guaranteed global linearizability**. A future independent custodian/witness deployment must enforce these access and sequencing rules on the server, not merely in an opt-in CLI.

This is synthetic auditing infrastructure: neither real original PlayStation execution nor a playable native Nintendo Switch Wild Arms game build is certified. No private game image, production signing key or personally identifying log is committed to the repository.
