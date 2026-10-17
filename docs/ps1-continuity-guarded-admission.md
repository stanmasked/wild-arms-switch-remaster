# Stage 247 — continuity-locked verifier admission (opt-in)

Stages 245 and 246 respectively implemented atomic one-time acceptance in a
private SQLite file and a **read-only** audit against an externally retained
snapshot. Stage 247 adds a separate `tools/audit_record_guarded_admission.py`
interface that **refuses to issue or accept** when the verifier's database
no longer contains every historical commitment in a supplied checkpoint.

**This is an opt-in gate.** The earlier `audit_record_atomic_verifier.py`
`issue` and `accept` commands still exist for compatibility and DO NOT
check the external checkpoint. To enforce this protection, the verifier
operator must restrict access to the old commands and use only the stage-247
commands in its operational workflow.

## How the gate works

Every guarded operation requires an existing stage-245 SQLite database **and**
an existing private stage-246 checkpoint retained by another trustworthy
custodian. There is intentionally **no fallback** to an empty checkpoint
or automatic creation of a replacement state.

1. Read and strictly validate the checkpoint file (mode 0600, private
   verifier-owned parent directory; no symbolic links).
2. Start SQLite `BEGIN IMMEDIATE`: only one writer can proceed at once.
3. Read and validate **issued and accepted rows from the same locked
   transaction** using stage-246 commitment code, including
   `PRAGMA integrity_check`, `foreign_key_check`, unique digest and
   row-count constraints.
4. Before mutating state, require *all* historical issued and accepted
   commitments from the checkpoint to remain present. If missing/changed,
   the operation **rolls back and fails closed**.
5. If continuity is intact, issue a fresh CSPRNG nonce with expiry or
   atomically accept complete stage-243 evidence and consume its issued
   nonce with the same stage-245 uniqueness constraints.
6. Commit the operation to SQLite; **the checkpoint is not updated
   automatically**.

This prevents one verifier instance from issuing/accepting through this
interface against a database demonstrably older than the supplied anchor,
even when a second concurrent writer is active. Reusing captured streams
or one-time nonces is also refused.

## Private usage

Set up the stage-245 verifier database in a private mode-0700 directory
and create at least one stage-246 checkpoint (bootstrap). Prefer a clean
trusted bootstrap. The first bootstrap cannot itself be anchored by an
older checkpoint; operational admission must not start until the trusted
custodian has retained this initial checkpoint.

```sh
python3 -m tools.audit_record_guarded_admission issue \
  /private/verifier/captures.sqlite \
  /independent-private-store/checkpoint-001.json \
  --ttl-seconds 300
```

The command prints the newly issued one-use nonce for **private delivery**
to the capture recorder, and nothing from old sessions.

After capture:

```sh
python3 -m tools.audit_record_guarded_admission accept \
  /private/verifier/captures.sqlite \
  /independent-private-store/checkpoint-001.json \
  /private/WildArms.bin \
  /private/disc-inventory.json \
  /private/temporal-slot-snapshots.json \
  /private/capture-manifest.json \
  /private/before-watch.jsonl \
  /private/after-snapshot.jsonl \
  /private/session-provenance.json \
  /private/before-receipt.json \
  /private/after-receipt.json
```

Acceptance does not print any session nonce, game memory values, debugger
identity, path or SHA-256 evidence digest. Both commands reject absent,
malformed, symlinked or non-private checkpoint files.

Exit codes:

- **0**: a guarded challenge was committed, or evidence was accepted once.
- **1**: previous history is missing, or the supplied capture fails
  eligibility (spent/missing/expired nonce, duplicate streams, conflicting
  internally consistent claims).
- **2**: malformed/private unreadable input or invalid SQLite schema/history;
  no secrets appear in the public error report.

## External checkpoint refresh — unresolved two-resource commit

This gate checks state against an **existing externally retained checkpoint**
but does **not** securely refresh that checkpoint after each SQLite commit.
This is intentional: SQLite cannot atomically commit an independently
administered append-only or remote trust anchor.

Any legitimate issuance or acceptance **after the latest trusted checkpoint**
may be lost during a database rollback without this comparison detecting
that loss. The custodian must periodically or synchronously receive a newer
checkpoint produced by stage 246 and authenticate its receipt **outside
the verifier process**. A future protocol will need durable cross-resource
commit receipts, an authoritative high-water mark and recovery rules for
crashes after the database commit but before checkpoint acknowledgment.

A malicious verifier-account user can still forge the checkpoint, replace
both database and checkpoint, bypass the opt-in gate via older commands,
or tamper with the local clock. Filesystem permissions alone do not
authenticate a checkpoint or protect against same-account compromise.
No network attestation, secure counter, trusted hardware, original PS1
execution, game structure size or Nintendo Switch native build is certified.
CI uses synthetic data only.
