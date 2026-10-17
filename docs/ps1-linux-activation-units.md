# Stage 263I — independently enrolled systemd activation-unit audit

A stopped and persistently masked `custodian-writer.service` is not
necessarily a full inventory of its activation paths. systemd socket,
timer and path units can cause the service to be started in ways an
operator might miss. This stage adds a separate, **read-only** unit
inventory for the **enrolled** activation paths.

`tools.audit_record_linux_activation_units` reads selected systemd
system units only. It does **not** mask, unmask, stop, start, reload
or modify services. It cannot retire an indeterminate witness fence.

## Enrollment

Independently provision one private canonical JSON file whose exact
SHA-256 digest is retained outside the custody service:

```json
{"activation_units":["custodian-writer.path","custodian-writer.socket","custodian-writer.timer"],"schema":"wild-arms-ps1-systemd-activation-unit-inventory-v1","service":"custodian-writer.service"}
```

The file must use UTF-8 ASCII-compatible compact JSON with sorted keys,
a final newline, sorted and unique activation units, and 0600
operator-only permissions. The scan refuses an empty catalogue,
unknown unit suffixes, duplicates and a wrong external hash pin.

Only `.socket`, `.timer` and `.path` units are accepted by the
tool. Other possible activation routes are explicitly **outside
coverage**, not implicitly safe.

## Checks

For the enrolled service and every enrolled activation unit, the audit
uses a bounded `/usr/bin/systemctl --system show` call with a fixed
property list and no shell:

- `LoadState=masked`, `UnitFileState=masked`, not `masked-runtime`.
- `ActiveState=inactive`, `SubState=dead`, `CanStart=no`.
- `NeedDaemonReload=no`, `Job=0`, `FragmentPath=/dev/null`.
- For the service, `MainPID=0` and `ControlPID=0`.
- Explicit `TriggeredBy` relationships on the service must be
  contained in the independently enrolled activation list.
- Explicit `Triggers` relationships on enrolled activation units
  may point only to the designated service.

The tool reads the complete enrolled set twice. A changed property,
unregistered **observed** trigger, active job, failed systemd command,
missing/duplicate/unexpected property or unit identity mismatch causes
a safe refusal. It does not silently treat a runtime-only mask or
unloaded but enabled unit as safe.

Systemd may report **empty trigger relationship fields for masked
units**. This does **not** prove the full dependency graph has been
enumerated. A positive report therefore does not set any
`activation_graph_complete` flag to true.

## Invocation

```sh
python3 -m tools.audit_record_linux_activation_units \
  /witness-private/known-systemd-activators.json \
  INDEPENDENTLY_PINNED_MANIFEST_SHA256
```

The CLI prints only a redacted JSON report, no unit list, raw
systemd properties, secrets or custody request. It has no database
write path. Exit 0 means the **enrolled** service and activation units
passed two local observations. Exit 1 means an observed contradiction
or integrity conflict; exit 2 means invalid inputs or OS failure.

Even for exit 0, the result sets:

- `activation_graph_complete_proved=false`
- `unlisted_systemd_generators_excluded=false`
- `future_activation_prevented=false`
- `witness_fence_retirement_authorized=false`
- `witness_fence_retired=false`

## Boundaries and next work

systemd generators, aliases, transient units, timers outside the
enrolled list, other services, user-service managers, sockets,
udev rules, cron, container supervisors and newly installed
units are not excluded. The observer's systemd state can change
immediately after either read. Privileged operators can unmask units,
restart processes, replace the systemd database or change the
mount namespace.

This is a **point-in-time negative observation**, not durable
service revocation, not an independently authenticated complete
service inventory, not hardware-enforced anti-rollback, and not
permission to retire a witness fence for an uncertain operation.

The 16 regression tests use mocked systemd property output.
No live production services, PS1 execution or Nintendo Switch
gameplay are attested by this stage.
