# Stage 263L — independently pinned, single-use observer-run replay journal

Stage 263K verifies **eight Ed25519-signed operator CLAIMS** that bind
report bytes, source-code hashes, original request and stop-session
nonce to one composite. Its run nonces were checked only **within one
bundle**: an already-signed run could be presented again in another
submission.

Stage 263L adds a **separate, non-expiring, private SQLite replay
ledger**, which intentionally **has no witness-fence unlock or reset
operation**.

## Journal model and trust boundary

Create the journal on an independent operator-controlled filesystem.
It must not be the custody/witness SQLite database or a replica
controlled by the old writer. A new `init` is permitted only if the
file does not exist, using exclusive creation. An absent or corrupt
journal is never silently recreated by `inspect` or `enroll`.
The journal and its parent directory must be private.

The journal uses one immutable-by-application row per **eight-claim
bundle**. It stores sequence, hash of the previous event, exact
composite SHA-256, independently pinned tool-source index SHA-256,
observer public-key SHA-256, all eight report kinds with exact signed
claim SHA-256 and run nonce, and a domain-separated event SHA-256.

Each `enroll` begins with Stage 263K verification (all reports,
source-byte pins and signatures), then acquires a single
`BEGIN IMMEDIATE` SQLite lock. Under that lock it audits the
**entire existing sequence/hash chain** before checking:

- An **externally retained** expected event count and latest head
  SHA-256 match the actual journal;
- None of the eight `(observer_public_key_sha256, run_nonce)` pairs
  has ever appeared in a previous enrolled bundle;
- The entire composite file SHA-256 was not already published;
- All eight claims have unique nonces and valid signatures in the
  same original stop-session context.

On success, one chained event is inserted and the transaction commits.
On conflict, the transaction rolls back. Appending the second bundle
with a stale expected head, or replaying a nonce with a freshly signed
otherwise valid claim, must fail. The journal performs no custody or
witness DB writes.

## Operator sequence

1. Independently designate and secure a **new** journal path, outside
   the custodian. Create with `init` and retain its returned
   `ledger_event_count=0` and `ledger_head_sha256` on a **separate
   trusted storage channel**.
2. Run `enroll` with all Stage 263K source/report/signature inputs,
   exactly the stored `--expected-count` and `--expected-head`.
3. After a successful commit, **independently escrow the new count
   and head** before allowing any later enrollment. Do not trust an
   output printed by a potentially compromised custody host as its
   own external escrow.
4. Use `inspect` with the escrowed values for independent read-only
   verification. A mismatch is an integrity incident, not a reason
   to initialize again.

Initialize (prints a redacted genesis head):

```sh
python3 -m tools.audit_record_witness_run_replay_ledger init \
  /independent-private/observer-replay.sqlite
```

Read-only inspection:

```sh
python3 -m tools.audit_record_witness_run_replay_ledger inspect \
  /independent-private/observer-replay.sqlite \
  --expected-count EXTERNALLY_ENROLLED_COUNT \
  --expected-head EXTERNALLY_ENROLLED_HEAD_SHA256
```

Enrollment requires all Stage 263K files, pins and eight named
`--<kind>-report`, `--<kind>-tool-source`, and
`--<kind>-signed-run` arguments, with `kind` one of
`preflight`, `quarantine`, `cgroup`, `revocation`,
`binary`, `interpreted`, `launchers`, `activation`:

```sh
python3 -m tools.audit_record_witness_run_replay_ledger enroll \
  /independent-private/observer-replay.sqlite \
  /private/composite.json PINNED_COMPOSITE_SHA256 \
  /private/source-index.json PINNED_SOURCE_INDEX_SHA256 \
  /private/observer-public.pem PINNED_OBSERVER_PUBLIC_PEM_SHA256 \
  --observer-tag independent-supervisor \
  --expected-count EXTERNALLY_ENROLLED_COUNT \
  --expected-head EXTERNALLY_ENROLLED_HEAD_SHA256 \
  --preflight-report /private/preflight.json \
  --preflight-tool-source /private/preflight-tool.py \
  --preflight-signed-run /private/preflight-signed-run.json \
  ... [repeat all three options for the other seven kinds]
```

Here the ellipsis is explanatory only, not a literal CLI argument.
The CLI outputs no report contents, private tokens or signing keys.

## What the tool does not establish

The statement **“independently retained latest head” is an operator
requirement, not a technical guarantee provided by this process**.
SQLite can be copied, rolled back, replaced, modified with privileged
SQL or restored from an older backup. A properly escrowed later
count/head detects that rollback when it is supplied to `inspect`
or `enroll`. If an attacker can also rewrite or substitute the
external count/head, a fabricated history can pass internal checks.

This journal is not an append-only hardware-backed record, TPM
counter, remote consensus quorum, distributed durable ledger or
authenticated evidence of actual process execution. An operator can
sign a false observation, and the journal can only show that a
specific **claim** was accepted once. It also cannot prevent new
processes from accessing the custody SQLite in the future.

A positive response always sets these flags to false:

- `independent_head_escrow_proved`
- `permanent_rollback_prevention_proved`
- `tool_execution_independently_proved`
- `witness_fence_retirement_authorized`
- `witness_fence_retired`
- `native_switch_game_build_verified`

**No uncertain negative outcome is reconciled and no witness fence is
retired.** CI tests are synthetic SQLite and signed-claim fixtures,
not proof of Linux production quiescence or gameplay on Switch.
