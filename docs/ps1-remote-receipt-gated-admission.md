# Stage 252 — remote receipt-gated admission without a local custodian SQLite copy

The stage-251 TLS channel authenticates the reference custodian's TLS 1.3
server certificate and the stage-250 Ed25519 receipt, but the older
stage-249 `issue`/`accept`/`ack` commands still read the **custodian's
SQLite database locally**. Stage 252 adds the opt-in
`tools/audit_record_remote_admission.py` adapter, which requires only the
**local verifier SQLite file and a mutually authenticated remote TLS
custodian endpoint**.

## Security boundaries and data flow

The adapter obtains `latest` over the stage-251 connection using all
these independently provisioned verifier inputs:

- Expected TLS hostname, trusted server CA and pinned SHA-256 of server's
  DER leaf certificate.
- Verifier client TLS certificate and private key.
- A pinned SHA-256 of the custodian's Ed25519 **public PEM** and the
  expected custodian identity tag.

It validates the remote checkpoint, verifies the signed receipt's
identity, sequence and hash, then reconstructs an authenticated in-memory
custody-head record with the exact stage-248 receipt-chain digest.
**No local custodian SQLite copy is required or opened.**

The existing stage-249 functions now expose
`bootstrap_with_latest`, `issue_with_latest`,
`accept_with_latest` and `acknowledge_with_latest` internally. Their
SQLite `BEGIN IMMEDIATE`, pending-state, nonce uniqueness, evidence
validation and digest semantics are unchanged. Original local commands
remain available and backward compatible.

For **bootstrap**, the remote checkpoint must match the entire local
verifier data state before the one-row gate can be created.

For **issue/accept**, the verifier first retrieves an authenticated
remote head, then the local transaction requires that the verifier's
acknowledged sequence, receipt digest and exact logical checkpoint equal
that head and that **no pending operation exists**. If valid, issue or
capture acceptance commits **together with a pending checkpoint hash**.

For **ack**, the adapter reads the pending marker and canonical
checkpoint from a single local read transaction, verifies that its
digest equals the previously committed pending hash, then sends the
exact checkpoint via the remote `deposit` operation. The stage-248
custodian commits or idempotently replays the checkpoint and returns a
signed latest receipt over TLS. Only after this confirmation does
`acknowledge_with_latest` consume the local pending marker under
`BEGIN IMMEDIATE`.

If no pending marker exists, `ack` fetches the latest remote head and
performs an **idempotent acknowledgment recovery**, without depositing
another checkpoint.

## CLI workflow

All four commands require one verifier database path, the remote
endpoint's host, port, expected TLS hostname, client certificate/key,
trusted server CA, trusted DER server certificate SHA-256, pinned
custodian Ed25519 public PEM and its trusted full-file SHA-256, and
`--custodian-tag`. There is **no custodian SQLite path** argument.

Bootstrap an already initialized stage-245 database whose exact
checkpoint has been remotely deposited by stage 251:

```sh
python3 -m tools.audit_record_remote_admission bootstrap \
  /private/verifier/sessions.sqlite \
  127.0.0.1 38481 localhost \
  /private/verifier/tls-client.pem \
  /private/verifier/tls-client-key.pem \
  /private/verifier/trusted-custodian-ca.pem \
  PINNED_TLS_SERVER_DER_SHA256 \
  /private/verifier/custodian-ed25519-public.pem \
  PINNED_ED25519_PUBLIC_PEM_SHA256 \
  --custodian-tag wild_arms_custodian_01
```

Use the same arguments with `issue`, `accept` or `ack` in place
of `bootstrap`. The `accept` command takes the nine familiar stage-249
private evidence paths (disc, inventory, temporal claim, binding
manifest, before and after streams, provenance and two receipts) after
the signing-public-key SHA-256 and before the required custodian tag.

**Important:** stage-251's server is a one-request `serve-once`
reference listener. Each command requires the custodian to have started
a separate listener instance. There is no production daemon or automated
reconnect queue. Operators should not assume this example is a safe
24/7 custodian server.

Exit codes: **0** operation committed or idempotent acknowledgment,
**1** blocked on pending state or mismatching remote high-water state,
**2** malformed local evidence, unavailable remote channel, certificate/
signature error or corrupted SQLite. Only a newly **issued** nonce is
displayed; private stream digests, keys, old nonces and memory values are
never emitted.

## Loss and recovery matrix

| Interruption | Safe behavior |
|---|---|
| During `issue/accept` fetch | No local modification |
| After local issue/accept commit | Pending marker durable; further admission blocked |
| During `ack` before remote deposit commit | Pending remains; retry `ack` |
| After deposit commit but before authenticated reply | Custodian has the new checkpoint, pending remains; repeat identical `ack` idempotently |
| After local acknowledgment commit but before CLI reply | No pending marker; repeat `ack` fetches latest remote head |
| Different remote checkpoint or forged signed receipt | Reject, do not release pending |
| Local pending checkpoint tampered | Refuse deposit, leaving pending marker |
| Custodian advanced independently | Verifier rejects stale local high-water; operator must reconcile external state |

## Remaining limits

This **eliminates the need for a local custodian DB copy** in the new
admission interface. It does **not** implement a global distributed
transaction, real remote custodian provisioning, persistent custodian
daemon, independent key enrollment, revocation/rotation, monitoring or
production-safe multi-client admission.

Between retrieving the latest remote checkpoint and committing the local
verifier transaction, an independent custodian writer could advance the
remote history. An **exclusive-writer operational policy** or a stronger
remote compare-and-swap/lease protocol is needed to guarantee strict
cross-system linearizability. Also, a single malicious operator controlling
both verifier and custodian can still forge/roll back the entire history
despite TLS and Ed25519. This stage does not protect old interfaces
(stage-245, stage-247, stage-249, stage-250) that bypass this opt-in path.

All tests use synthetic checkpoints, temporary test keys and TLS loopback
connections only. Original Wild Arms PS1 execution, structural record
size, game-assets authenticity and any playable native Nintendo Switch
game build remain unverified.
