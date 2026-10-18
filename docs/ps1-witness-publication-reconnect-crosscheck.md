# Stage 264B — reconnect cross-check of a pinned keeper and two live authorities

This research-stage, **read-only** checker compares three distinct kinds of
evidence after an operator reconnects to its checkpoint keeper:

1. The latest locally audited Stage 263Z SQLite checkpoint must exactly match
   the independent operator's pinned generation, complete signed-pair SHA-256,
   event-chain head SHA-256, event count and scope.
2. The complete archived signed Stage 263X replies for authority A and B must
   hash to the pinned Stage 263Y pair digest, verify under independently pinned
   Ed25519 authority keys, include the separately recorded source challenges
   and exactly match the keeper's stored source sequence numbers.
3. Each live source must answer a **new, separate 128-bit nonce** over HTTPS
   with a matching domain-separated Ed25519 signature on the same externally
   authenticated Stage 263W publication tuple. Both live sequence numbers
   must be at least their individually stored sequence floor. The whole
   check fails when even one source is unavailable or diverges.

Two complete SQLite read transactions surround the network exchange.
Differences between pre- and post-network database snapshots reject the
result, including a legitimate concurrent advancement. No database mutation,
CAS replay, receipt upload or witness-fence retirement is implemented.

The verifier is
tools/audit_record_witness_publication_reconnect_crosscheck.py.
Keys, notary pins, archived signed envelopes and source URLs are operator
enrollment inputs. Authority A and B must have different IDs, DNS hostnames
and DER Ed25519 key material; both notaries must use distinct keys, for four
different enrolled roles.

## Example command (all source endpoints are placeholders)

    python3 -m tools.audit_record_witness_publication_reconnect_crosscheck \
      /operator-private/checkpoints.db \
      --scope private-wild-arms-publication-mirrors \
      --expected-generation EXTERNAL_GENERATION \
      --expected-pair-pin EXTERNAL_SIGNED_PAIR_SHA256 \
      --expected-event-head EXTERNAL_CHAIN_HEAD_SHA256 \
      --expected-count LATEST_COUNT \
      --expected-head-sha256 HEAD_SHA256 \
      --expected-history-sha256 HISTORY_SHA256 \
      --expected-witness-sha256 WITNESS_SHA256 \
      --expected-bundle-sha256 NOTARY_BUNDLE_SHA256 \
      --source-a-url https://authority-a.example.org/heads/current \
      --source-a-id independent-authority-a \
      --source-a-public /external/source-a.pem \
      --source-a-pin SOURCE_A_PUBLIC_PEM_SHA256 \
      --archived-a-signed /external/archive-a.json \
      --archived-a-nonce ARCHIVED_NONCE_A \
      --notary-a-public /external/notary-a.pem \
      --notary-a-pin NOTARY_A_PUBLIC_PEM_SHA256 \
      --source-b-url https://authority-b.example.net/heads/current \
      --source-b-id independent-authority-b \
      --source-b-public /external/source-b.pem \
      --source-b-pin SOURCE_B_PUBLIC_PEM_SHA256 \
      --archived-b-signed /external/archive-b.json \
      --archived-b-nonce ARCHIVED_NONCE_B \
      --notary-b-public /external/notary-b.pem \
      --notary-b-pin NOTARY_B_PUBLIC_PEM_SHA256

CLI exit codes: 0 means a valid, locally consistent cryptographic
observation, 1 means conflict/invalid evidence, and 2 means source
unavailability. JSON output is redacted and never includes the raw signed
envelopes or private key files.

## Essential limits

The fresh signed envelopes intentionally have *different* challenges and
may have different signature bytes and sequence numbers from the archived
ones. Requiring the fresh envelope SHA to equal the archived pair digest
would be incorrect. The signed **underlying Stage 263W head tuple** is the
invariant; sequences are checked against source-specific stored floors.

An honest authority may sign the current head at the *same* sequence number;
this is not a new publication event, so a non-decreasing floor is appropriate.
It is not evidence that a head is globally latest. If both authorities
serve the same stale head matching an outdated externally supplied tuple,
this stage alone cannot detect it. The upstream independently authenticated
Stage 263V/W/Y archive transition remains a prerequisite.

Different domain names and keys do NOT prove physical, operational or
administrative independence. This repository provisions no real authority,
operator-controlled monotonic external store or remotely trusted keeper.
Two SQLite snapshots from one host do not make the keeper physically
independent. A rollback of the DB together with all independent pins can
mislead the checker.

All successful reports keep these flags false:
external_monotonic_pin_storage_proved,
physical_authority_independence_proved,
remote_global_latest_head_proved,
automatic_cas_retry_authorized,
witness_fence_retirement_authorized,
witness_fence_retired, and native_switch_game_build_verified.

CI uses only synthetic signatures and simulated HTTPS responses. It does
not demonstrate live independent service deployment or Switch emulation.
