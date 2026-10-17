# Stage 251 — mutual TLS 1.3 reference custodian channel

Stages 248–250 provide durable monotonic custodian state, recovery after lost
receipts, one-at-a-time verifier admission, and Ed25519-signed custody
confirmations. Stage 251 adds **actual encrypted, mutually authenticated
transport** in an opt-in **one-connection reference server/client**:
`tools/audit_record_custodian_tls.py`.

## What the reference channel enforces

- TLS **1.3 only**, full certificate-chain validation against configured
  trusted CA certificates, and **mutual** client/server certificates.
- Strict TLS hostname validation by the verifier and SHA-256 pins of the
  **exact DER peer leaf certificate** at *both* ends.
- Client verifies the server's DER certificate pin **before sending the
  original checkpoint**. A forged or misconfigured identity is rejected.
- Canonical, length-prefixed JSON requests/responses with a **1 MiB maximum
  frame**, strict fields, and random 128-bit request IDs echoed back by the
  response. A response for a different request is rejected.
- The server calls the stage-248 custodian `deposit` in a transaction,
  including its existing monotonic-history and idempotence constraints.
  It also supports `latest` to retrieve the newest committed checkpoint.
- The response carries the exact committed private checkpoint plus a
  separately **Ed25519-signed** stage-250 receipt. The client checks the
  custodian identity and externally pinned Ed25519 public key; it also
  checks that the signed receipt binds to the exact returned checkpoint.
- For a `deposit`, the returned checkpoint must include all the historical
  commitments in the submitted checkpoint. A repeat after a lost reply
  returns the same latest committed custodian round without duplicating it.
- Private receipt/checkpoint outputs use exclusive mode-0600 file creation
  and cannot silently overwrite previously returned files.

**The TLS certificate and Ed25519 signing key serve distinct purposes.**
Both identities must be securely provisioned; neither derives its trusted
pin from untrusted data received in the same request.

## Certificates and independent provisioning

Before starting the example, provision under **separate custodian and
verifier accounts** (not done by the repository):

1. A trusted CA or approved CA chain for client authentication at the
   custodian, and separately for server authentication at the verifier.
2. A TLS 1.3 server certificate with subjectAlternativeName matching the
   exact `tls_hostname` given by the verifier.
3. A TLS client certificate for the verifier.
4. The SHA-256 of the server's DER *leaf* certificate at the verifier, and
   the SHA-256 of the client's DER leaf at the custodian. These must be
   obtained from separately trusted enrollment, never a handshake with an
   untrusted peer.
5. The custodian's **separately generated Ed25519 key** and the verifier's
   out-of-band trusted PEM SHA-256 pin from stage 250.

Keep client/server private keys mode-0600 in mode-0700 private directories.
Any CA PEM passed to the reference CLI is also kept in a private directory.

In a private provisioning script, the exact DER pin can be computed with
`openssl x509 -in tls-leaf.pem -outform DER | sha256sum` and delivered
independently to the other party. **This command is not itself enrollment
or authentication.**

## Example custodian command

On an independently controlled custodian machine/account, make the
one-shot reference listener accessible only on a trusted interface. The
default is loopback. A remote deployment needs proper firewalling, process
supervision, audit logging, rate limiting and policy enforcement.

```sh
python3 -m tools.audit_record_custodian_tls serve-once \
  /custodian-private/anchors.sqlite \
  /custodian-private/ed25519-signing-key.pem \
  /custodian-private/tls-server.pem \
  /custodian-private/tls-server-key.pem \
  /custodian-private/trusted-client-ca.pem \
  TRUSTED_CLIENT_LEAF_DER_SHA256 \
  --custodian-tag wild_arms_custodian_01 \
  --host 127.0.0.1 --port 38481
```

The reference server handles **one connection** then exits, including
when authentication fails. It is not a production daemon.

## Verifier fetch and deposit

The verifier uses its own TLS certificate/private key, trusted server CA,
server TLS leaf pin, pinned Ed25519 public key and expected custodian tag:

```sh
python3 -m tools.audit_record_custodian_tls latest \
  127.0.0.1 38481 localhost \
  /verifier-private/tls-client.pem \
  /verifier-private/tls-client-key.pem \
  /verifier-private/trusted-server-ca.pem \
  TRUSTED_SERVER_LEAF_DER_SHA256 \
  /verifier-private/custodian-ed25519-public.pem \
  TRUSTED_CUSTODIAN_ED25519_PEM_SHA256 \
  /verifier-private/signed-latest-001.json \
  /verifier-private/checkpoint-latest-001.json \
  --custodian-tag wild_arms_custodian_01
```

For `deposit`, use the same arguments with the command name changed to
`deposit` and add the private stage-246 checkpoint offer as the final
positional argument. The server deposits only a stage-246 checkpoint that
passes bounded canonical validation and monotonic custody checks.

Run a new `serve-once` instance for every `latest` or `deposit`.
Every client call uses a newly generated request ID; replies only match
that invocation. Authentication and integrity are provided by TLS 1.3,
pins and Ed25519, not the request ID alone.

After retrieving the signed receipt and checkpoint, the verifier can use
the stage-250 signed stage-249 `ack` interface to validate its pending
state. **This stage does not automatically call `ack`**. The signed
stage-250 interface itself still reads a local custodian DB, so deployments
without shared state or trusted replication require another small adapter.
Do not claim end-to-end remote admission without that integration.

## Failure and replay behavior

| Event | Behavior |
|---|---|
| Server/client certificate not CA-validated or leaf pin mismatch | TLS connection rejected; checkpoint never sent by a verifier with incorrect server pin |
| Wrong signed-custodian Ed25519 key/tag | Response rejected even though TLS succeeded |
| Oversized/truncated frame or invalid JSON/base64 | Fail-closed, no private payload in public errors |
| Response from a different request ID | Refused |
| Older checkpoint offer after newer custody commit | Rejected by stage-248 high-water check |
| Network drops after deposit commit but before reply | Retrying the **same exact offer** is idempotent |
| Receipt/key rotated without advance provisioning | Rejected until verifier is safely reconfigured |

## Unresolved deployment requirements

**No remote custodian has actually been deployed or connected.** The CI
tests create temporary CA/client/server certificates and Ed25519 keys
and communicate over **local loopback** with an intentionally one-shot
test server. The project includes no public keys, secrets, game binaries,
hardware capture artifacts or operational network endpoints.

This is not a production service: no certificate expiration/rotation,
CRL/OCSP policy, key revocation, pinned-key rollover, automatic reconnect
queue, remote high-water admission adapter, authenticated persistent
append-only transparency log, load shedding, service availability
guarantee or hardware-backed custodian has been built. A compromised
custodian can still sign false receipts and can roll back its own state.
The older verifier interfaces remain available and may bypass mandatory
signed remote communication.

All original PlayStation execution claims and actual Wild Arms structure
sizes remain unverified. No native Nintendo Switch game build was
confirmed by this stage.
