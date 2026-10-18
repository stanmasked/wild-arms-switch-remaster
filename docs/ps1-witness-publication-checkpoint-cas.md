# Stage 263Z — conditional checkpoint store and independent readback (research)

Stage 263Y authenticates two separately signed previous publication heads
and observes strict progression to two newly challenged current heads.
It returns a **proposed** SHA-256 of the two new complete signed envelopes.
Stage 263Z adds a **local reference implementation of a checkpoint keeper**,
tools/audit_record_witness_publication_checkpoint_cas.py, for an *operator
who is separate from the custody host* to hold and advance that digest.

This tool is not a deployed remote witness service. Its local SQLite database
does **not** establish real administrative, machine, or failure-domain
independence from the custodian. Production deployment and external trusted
enrollment remain out of scope.

## Trust enrollment

A separate trusted operator must authenticate the Stage 263Y initial signed
pair, scope, last event count, and both authority sequence numbers. Compute
the versioned enrollment hash with enrollment_digest(), and retain its SHA-256
**outside** the new database, along with subsequent checkpoint pins.
Require a private writable directory accessible only to that operator. The
tool refuses to silently create a missing database during inspection or
advancement. Initial creation is explicit, exclusive, and mode 0600.

Example initialization (symbolic placeholders):

    python3 -m tools.audit_record_witness_publication_checkpoint_cas \
      init /operator-private/checkpoints.db \
      --scope private-wild-arms-publication-mirrors \
      --initial-pin TRUSTED_STAGE_Y_SIGNED_PAIR_SHA256 \
      --initial-count INITIAL_EVENT_COUNT \
      --initial-sequence-a INITIAL_SIGNED_SOURCE_A_SEQUENCE \
      --initial-sequence-b INITIAL_SIGNED_SOURCE_B_SEQUENCE \
      --external-enrollment-pin TRUSTED_ENROLLMENT_SHA256

Initialization writes a genesis event with a chained SHA-256, followed by a
singleton head. SQLite user_version distinguishes the expected research
schema. The keeper performs a complete bounded chain audit on every
inspection or conditional advancement.

Every subsequent operator action MUST supply three independently retained
expectations: generation number, latest signed pair SHA-256, and latest
checkpoint event-chain SHA-256. These values cannot be recovered by merely
trusting the local database being inspected.

## Strict compare-and-swap / separate-connection readback

The operator independently verifies Stage 263V, 263W and Stage 263Y,
retains the exact Stage Y output JSON bytes and their SHA-256, and
submits those exact bytes to the keeper. The keeper checks the exact report
SHA, its versioned schema, fixed safety flags and expected record fields.
A Stage 263Y report is **not itself a signature**; a bare SHA of untrusted
bytes is **not** authenticated provenance. The operator must independently
verify the underlying signed evidence before pinning the Stage Y report.

Within one SQLite BEGIN IMMEDIATE transaction, the keeper:

1. Audits the entire append-only local hash chain, sealed schema and current
   singleton head.
2. Compares generation, signed-pair hash and event-chain head with the exact
   independently retained expected values, failing closed on mismatch.
3. Requires the proposed signed-pair digest differs from the prior digest,
   the event count increases, and **both** source sequence numbers strictly
   increase. Rejects any authorization to retire a witness fence.
4. Appends a domain-separated SHA-256 chained event and updates the singleton
   head using a conditional SQL UPDATE that checks its three old fields.
   Either both changes commit atomically or neither commits.

After commit, it reopens the database on a distinct connection and
revalidates the entire chain and exact new generation/pair/event SHA-256.
If the readback is different because a concurrent process already advanced
the head, it fails closed: **do not interpret failure as proof the earlier
commit did not happen**. Independently reconcile the operator's latest pin.
A successful report contains the newly committed event head and the
readback result; it never contains private keys or signed envelopes.

Example:

    python3 -m tools.audit_record_witness_publication_checkpoint_cas \
      advance /operator-private/checkpoints.db \
      --expected-generation PREVIOUS_GENERATION \
      --expected-pair-pin PREVIOUS_SIGNED_PAIR_SHA256 \
      --expected-event-head PREVIOUS_EVENT_CHAIN_SHA256 \
      --report-file /operator-private/verified-stage-y-report.json \
      --independent-report-pin VERIFIED_EXACT_REPORT_SHA256

The operator MUST then persist and reread the new generation, signed-pair
SHA-256, and event-head SHA-256 from an independent **trustworthy** location
before using them as future rollback-protection inputs. The keeper cannot
enforce that important external step.

Read-only inspect, also requiring the three outside expectations:

    python3 -m tools.audit_record_witness_publication_checkpoint_cas \
      inspect /operator-private/checkpoints.db \
      --expected-generation TRUSTED_GENERATION \
      --expected-pair-pin TRUSTED_SIGNED_PAIR_SHA256 \
      --expected-event-head TRUSTED_EVENT_CHAIN_SHA256

## Hard security limits

- Local SQLite integrity and its hash chain do **not** prevent a privileged
  operator from restoring an old valid database together with old external
  inputs. No TPM monotonic counter, externally audited log, quorum or
  hardware-backed trusted storage is implemented.
- Separate SQLite connections and synchronous FULL are useful durability
  precautions, but do **not** prove survival of sudden power loss, malicious
  host replacement, backup rollback, or durable recording outside this host.
- Physical and administrative independence, challenge freshness, authority
  honesty and global latestness must be independently established by
  deployed systems. No live source is deployed in this repository.
- The Stage 263Z keeper **does not itself** reauthenticate the Stage 263Y
  source signatures or Stage 263V/W history. Merely pinning arbitrary report
  bytes would not be a secure operational process.
- Repository CI exercises **synthetic SQLite fixtures** and concurrent local
  requests only, not external deployment, Nintendo Switch emulation, or
  production custody recovery.

Every successful result retains witness_fence_retirement_authorized=false,
witness_fence_retired=false, native_switch_game_build_verified=false,
independent_operator_or_host_proved=false,
rollback_protection_without_external_pins_proved=false, and
physical_durability_proved=false. Stage 263Z has no interface for deleting
records, resetting the journal, or freeing an indeterminate witness fence.
