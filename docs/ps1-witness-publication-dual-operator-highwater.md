# Stage 264C — independently signed two-operator historical high-watermarks

The Stage 264B fresh HTTPS cross-check can confirm that a local SQLite
checkpoint, an archived signed pair and two freshly signed online authority
replies all agree on the **same** head. If an attacker rolls back the keeper,
both online authorities and the operator's supplied expected head together,
this can still produce apparent agreement.

Stage 264C provides a separate *historical floor*, using two explicitly
enrolled, externally signed Ed25519 operator certificates. The research
verifier lives at
tools/audit_record_witness_publication_dual_operator_highwater.py.

## Trust boundary and enrollment

Two separate operators must maintain distinct Ed25519 private signing keys,
identifiers and an **independently authenticated, latest** signed checkpoint
certificate. Each signed body contains:

- Stable scope and operator identifier.
- Observer-specific monotonically increasing seal sequence.
- Exact checkpoint generation, full pair SHA-256 and chained event head SHA-256.
- Publication event count and both external source sequence numbers.
- An explicit false witness-fence release authorization.

The client requires each certificate's **exact bytes** to match its own
independently retained SHA-256, plus its public PEM SHA-256 pin and minimum
observer seal sequence. It verifies each domain-separated Ed25519 signature
and requires the two certificates agree on the *same historical state*.
Both operators' keys must be distinct; when combined with the Stage 264B
live-source cross-check, four additional authority/notary keys can be checked
for six distinct DER identities.

The local keeper's complete SQLite event chain is audited in two read-only
transactions. Its current head must match the separately supplied current
expected generation, pair digest and chain head. The certified historical
generation must be present **exactly** in the chain with identical event
head, pair hash, event count and both source sequences. The observed current
head may be *newer*, but never older, than that certified floor; current
counters may not roll back beneath it.

If both online authorities and the keeper agree on an old snapshot, but
the independently retained signed floor refers to a later generation, this
check rejects the old state. Tests exercise that specific coordinated rollback
with a valid older SQLite database, correctly signed old source replies,
and independently enrolled newer operator certificates.

## Read-only CLI (symbolic example)

    python3 -m tools.audit_record_witness_publication_dual_operator_highwater \
      /operator-private/checkpoints.db \
      --scope private-wild-arms-publication-mirrors \
      --expected-generation INDEPENDENT_CURRENT_GENERATION \
      --expected-pair-pin INDEPENDENT_CURRENT_PAIR_SHA256 \
      --expected-event-head INDEPENDENT_CURRENT_CHAIN_HEAD_SHA256 \
      --operator-a-id offhost-highwater-a \
      --operator-a-public /external/operator-a.pem \
      --operator-a-pin OPERATOR_A_PEM_SHA256 \
      --signed-a-checkpoint /external/operator-a-signed.json \
      --external-a-sha256 OPERATOR_A_LATEST_ENVELOPE_SHA256 \
      --external-a-sequence-floor OPERATOR_A_LATEST_SEAL_SEQUENCE \
      --operator-b-id offhost-highwater-b \
      --operator-b-public /external/operator-b.pem \
      --operator-b-pin OPERATOR_B_PEM_SHA256 \
      --signed-b-checkpoint /external/operator-b-signed.json \
      --external-b-sha256 OPERATOR_B_LATEST_ENVELOPE_SHA256 \
      --external-b-sequence-floor OPERATOR_B_LATEST_SEAL_SEQUENCE

Exit 0 means the signatures and local chain meet these **externally
provided** constraints; exit 1 means mismatch or insufficient evidence.
There is no enrollment, writing, recovery or fence-retirement command.

The Python helper verify_with_live_sources() additionally executes the full
Stage 264B two-source live cross-check between **two** signed historical
floor observations and rejects head mismatches across the operations.
It accepts fully specified Stage 264B reconnect parameters; it does not
weaken or replace that stage's HTTPS and signature requirements.

## What this does NOT prove

Two source names and two operator signatures are not proof of different
physical hosts, administrators, storage domains, independent operator
actions, honest timestamps, or globally newest external history. There is
**no production authority or operator-signing infrastructure deployed** in
this repository. If both operator private keys or their latest out-of-band
envelope pins and seal-sequence floors are compromised or rolled back,
a coordinated attack could furnish older, valid certificates. The
certificate body intentionally contains no trusted clock, so it is a
monotonic *conditional* floor, not a secure time oracle.

This stage does not validate full Stage 263V/W PS1 history by itself; that
remains a separate independently authenticated prerequisite. It does not
implement an independent append-only transparency service, trusted
hardware monotonic counter, remote CAS, automatic retries, custody
changes or a Nintendo Switch game build.

In all reports: witness_fence_retirement_authorized=false,
witness_fence_retired=false, automatic_cas_retry_authorized=false,
globally_latest_publication_proved (or
global_latest_publication_proved)=false,
externally_retained_pins_are_latest_proved=false, and
coordinated_rollback_with_compromised_external_pins_excluded=false.
CI uses simulated signed certificates and local databases only.
