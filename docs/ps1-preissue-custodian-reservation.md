# Stage 254 — recoverable pre-issue custodian reservation

Stages 251–253 established mutually authenticated TLS 1.3 transport, pinned
Ed25519 custody receipts, pending local checkpoint acknowledgment and
single-winner custody compare-and-swap. Previously **two different
verifiers could both issue locally** against the same signed custodian
head, then one would lose the CAS race when depositing its pending
checkpoint. Stage 254 adds an **opt-in exclusive, durable reservation of
the current custodian head before a verifier creates a new challenge**.

## Admission sequence

Use `tools/audit_record_remote_reserved_issue.py issue`, supplying
the same verifier SQLite and TLS/client/key/pin arguments as stage 252
`audit_record_remote_admission.py issue`.

1. Fetch the current exact checkpoint and Ed25519-signed receipt through
   mutually authenticated TLS. Compare them to the local receipt gate.
2. Inside the verifier's SQLite `BEGIN IMMEDIATE`, persist a new random
   **128-bit reservation token** and the expected custody sequence and
   prior receipt-chain hash, **before any reservation network request**.
   Existing unfinished intent for the same head is reused.
3. Submit a `reserve` request over TLS, binding the authenticated previous
   custody head and this exact token to the request ID.
4. Custodian `reserve()` obtains its SQLite `BEGIN IMMEDIATE` write
   lock and atomically accepts **only one unique token for the currently
   committed custody head**. A repeat with the same token is idempotent;
   a competing verifier with another token receives a refusal and has
   not yet issued a challenge.
5. Once the signed custody response confirms the expected version, the
   verifier creates a new challenge using the existing stage-249
   transaction and stores its pending checkpoint marker atomically.
6. `audit_record_remote_reserved_issue.py ack` reads the local pending
   checkpoint **and original token**, then performs a
   `deposit-reserved` over TLS. The custodian checks the exact
   expected head, token ownership and logical checkpoint continuity
   inside the *same* SQLite transaction that commits the new custody
   checkpoint. It marks that reservation committed.
7. A lost response can be retried with the same token, previous head and
   checkpoint bytes. Only an exact replay of that immediately next
   committed round is accepted. Once local `ack` succeeds, the next
   issue may replace the old committed reservation with a new token for
   the now-current custody head.

The token is **never printed** in the public CLI result. The custodian
stores only a SHA-256 hash over a dedicated domain prefix and the token's
raw 128 bits. The verifier stores the token in its private SQLite file
alongside the expected custody head so network/OS crashes after
reservation do not destroy recovery credentials.

## New network actions

The existing one-shot `audit_record_custodian_tls.py serve-once` now
supports two additional requests:

- `reserve`: authenticated expected sequence + previous receipt hash,
  exact 128-bit token, **no checkpoint payload**.
- `deposit-reserved`: all custody CAS fields plus the same token and
  exact checkpoint bytes. It is impossible for a different token or a
  legacy unreserved deposit to displace an **active** reservation.

The ordinary `latest` and legacy conditional `deposit` endpoints
continue to exist. Legacy deposits cannot bypass a live reservation, but
they can still be used where there is *no active reservation*; old
verifier interfaces are NOT automatically forced to reserve a head.

## Reference invocation

First bootstrap a verifier already at a trusted custodian checkpoint
using the stage-252 remote bootstrap command, with the custodian's
one-shot server available.

Then issue a challenge with:

```sh
python3 -m tools.audit_record_remote_reserved_issue issue \
  /verifier-private/sessions.sqlite \
  127.0.0.1 38481 localhost \
  /verifier-private/tls-client.pem \
  /verifier-private/tls-client-key.pem \
  /verifier-private/trusted-server-ca.pem \
  PINNED_SERVER_LEAF_DER_SHA256 \
  /verifier-private/custodian-ed25519-public.pem \
  PINNED_CUSTODIAN_ED25519_PUBLIC_PEM_SHA256 \
  --custodian-tag wild_arms_custodian_01
```

Start a new custodian `serve-once` listener for each request. A
successful `issue` requires **two** separate network requests (latest
then reserve). After the verifier has persisted a pending challenge,
start another listener and call the same command with `ack` instead
of `issue`. The `ack` call deposits the pending checkpoint using
the reservation token and verifies the signed reply. If the request or
reply is lost, run `ack` again with the *same local database state*.
The custodian does not duplicate a round.

## Crash and contention behavior

| Interruption | Recovery |
|---|---|
| Before local intent commit | Nothing sent to custodian |
| Local intent committed, network reserve fails | Retry issue; reuse the exact saved token |
| Custodian reserve committed, reply lost | Retry issue; server returns idempotent reservation |
| Custodian reserve succeeds, local issue fails | Retry issue if the local gate is still ready; token retained |
| Local challenge committed, response lost | New issue blocked by pending marker; retrieve operator diagnostics, do not expose historical nonce |
| Custodian reserved deposit committed, reply lost | Retry ack with same token/checkpoint |
| Custodian reserved checkpoint acknowledged locally | Next reservation uses the newest signed custody head |
| Another verifier reserves the same head | Competing token rejected **before issuing a challenge** |
| Another verifier tries an unreserved deposit during live reservation | Refused without changing custody |

## Limitations

**Reservations intentionally do not expire automatically.** Expiring a
reservation based on an unauthenticated or rollbackable wall clock could
allow a new verifier to take over while the first still believes it owns
the head. If the first verifier loses its private SQLite reservation
token permanently, that custodian head remains blocked until a separately
trusted, audited operator reconciliation protocol is implemented.
No unsafe automatic cancellation or timeout override is provided.

Reservation ownership is tied to a secret token on an authenticated TLS
connection, not to an independent hardware identity or remote attestation.
The project still provides a one-shot reference server, not a
production independently deployed, highly available custodian. A
compromised custodian, coordinated rollback, compromised verifier,
misprovisioned keys or bypass via unguarded interfaces remain outside
this protection. There is no cross-database atomic transaction. Two
different clients can both create **local intent** records, but only
one can reserve the remote head and actually issue a new challenge via
this specific opt-in interface.

**Acceptance remains a separate stage-252 workflow** and is not yet
required to reserve a remote head prior to accepting evidence; complete
mandatory reservation enforcement must also include acceptance and
decommissioning legacy bypass commands. This stage only claims
pre-issue safety through `remote_reserved_issue`.

The new tests use synthetic verifier states and locally generated TLS
and Ed25519 keys, with loopback sockets only. No original PlayStation
runtime execution, game structure measurement, proprietary assets or
native Nintendo Switch playable build is verified.
