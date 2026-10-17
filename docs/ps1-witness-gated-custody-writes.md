# Stage 259 — signed witness guard for custodian reserve and deposit

Stage 258 introduced an opt-in signed recovery witness gate for two-admin
administrative recovery. Ordinary custody reservations and deposits could
still proceed without consulting that witness, even when the custodian
had been rolled back behind the independently retained recovery journal.

Stage 259 adds the same **exact independent witness continuity check**
to the *custodian's own* reservation and deposit transactions. The
additional optional witness_head parameter is evaluated by
check_locked() **after BEGIN IMMEDIATE**, before any mutation and while
the custody SQLite writer lock is still held.

The witness guard validates the complete original custodian checkpoint
history, all stage-256 administrative recovery events and their exact
historical custody receipt references. It refuses shorter, forked or
unwitnessed later recovery histories. Both new reservations and
conditional reserved checkpoint deposits require an exact match.

## New opt-in mutual-TLS server mode

Use serve-once-witness-guarded in
tools/audit_record_custodian_tls.py to enforce this check on the server
without changing the existing stage-251/254 client wire protocol:

    python3 -m tools.audit_record_custodian_tls serve-once-witness-guarded \
      /custodian-private/anchors.sqlite \
      /custodian-private/signing-key.pem \
      /custodian-private/server-cert.pem \
      /custodian-private/server-key.pem \
      /custodian-private/trusted-client-ca.pem \
      PINNED_CLIENT_TLS_LEAF_SHA256 \
      /witness-private/recovery-witness.sqlite \
      /custodian-private/current-witness-signed.json \
      /custodian-private/trusted-witness-public.pem \
      TRUSTED_WITNESS_PUBLIC_PEM_SHA256 \
      --custodian-tag wild_arms_custodian_01 \
      --witness-tag independent_recovery_witness \
      --host 127.0.0.1 --port 38481

Before binding the listener, the guarded server authenticates a signed,
independently retained witness high-water using an out-of-band trusted
public PEM fingerprint. The witness database must be independently
initialized and signed, including a signed genesis for the very first
administrative recovery, as defined in stage 258.

During an authenticated incoming request, the server passes the
authenticated witness head into the existing stage-254 reserve and
reserved deposit code. Their exact event-prefix comparison runs **inside
the same custody SQLite transaction as the write**.

A signed witness head with count zero is valid only against a custodian
with no recovery events. After any administrative recovery, the witness
operator must record and sign its new event *before the next guarded
reservation or deposit*. This is an intentional fail-closed barrier.

The existing server mode serve-once remains available for backwards
compatibility and can bypass the witness guard. The new mode does not
alter or automatically protect other direct SQLite or legacy commands.
For deployments requiring witness enforcement, exclude those bypasses
using independent OS accounts, access controls and service provisioning.

## Failure behavior

- Missing witness DB, invalid private receipt, wrong public-key fingerprint,
  false signature or stale signed head: the guarded server refuses to
  start accepting requests.
- Current custodian recovery history truncated, forked, malformed or
  disconnected from original checkpoint receipts: the guarded reserve
  and deposit both refuse without changing custody SQLite state.
- Recovery committed on the custodian but not yet witnessed: the next
  guarded reserve and deposit refuse until an independent witness
  append and fresh signature has been obtained.
- Two simultaneous guarded reservation writers: only one succeeds due
  to BEGIN IMMEDIATE and the existing single-owner token check.
- Disconnect after a guarded reserved deposit commits: the existing
  exact-token immediate-next-round idempotent retry still works when the
  same signed witness head remains current.

## Remaining boundaries

The signed witness receipt is authenticated *before* the custody
transaction; the separately managed witness may advance meanwhile.
SQLite serializes mutations in the custody database, but there is no
cross-database atomic commit or witness lease. A production service
would need an independently authenticated live witness protocol with
atomic expected-head admission and safe key rotation.

A standalone signed receipt cannot establish that it is globally latest
without consulting independently retained state. This reference mode
still accesses an independently protected witness SQLite DB or a
trusted copy, and therefore **does not yet meet** the future goal of
network-only proof delivery without that database. No independent
production witness has been deployed.

The new test suite uses synthetic PlayStation capture metadata and
temporary TLS/Ed25519 keys over loopback. It does not verify original
Wild Arms PS1 execution, game assets, authentic structure offsets or
a playable Nintendo Switch native port.
