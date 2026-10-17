"""Stage 263I: read-only systemd socket/timer/path activation inventory.

A privately enrolled set of activation units is checked twice along with its
target custody service. No host state changes, service mask or fence retirement
are implemented. An absent trigger relationship is NOT proof of inventory
completeness; this observation can never authorize negative recovery.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import re
import subprocess

try:
    from .audit_record_linux_writer_inventory import (
        _canonical, _strict_json, _private_bytes, _SHA256,
    )
except ImportError:
    from audit_record_linux_writer_inventory import (
        _canonical, _strict_json, _SHA256,
    )
try:
    from .audit_record_linux_interpreted_writers import _private_bytes
    from .audit_record_linux_writer_revocation import (
        _unit, _parse_unit, _read_systemd, PROPERTIES as SERVICE_PROPERTIES,
        RevocationConflict,
    )
except ImportError:
    from audit_record_linux_interpreted_writers import _private_bytes
    from audit_record_linux_writer_revocation import (
        _unit, _parse_unit, _read_systemd, PROPERTIES as SERVICE_PROPERTIES,
        RevocationConflict,
    )

SCHEMA = 'wild-arms-ps1-systemd-activation-unit-inventory-v1'
REPORT_SCHEMA = 'wild-arms-ps1-systemd-activation-observation-v1'
DOMAIN = b'wild-arms-ps1-systemd-activation-observation-v1\x00'
MAX_MANIFEST = 8192
MAX_UNITS = 64
MAX_PROPERTY_OUTPUT = 4096
_UNIT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.@-]{0,120}\.(?:socket|timer|path)\Z')
UNIT_TYPES = ('.socket', '.timer', '.path')
ACTIVATION_PROPERTIES = (
    'Id','LoadState','UnitFileState','ActiveState','SubState',
    'CanStart','NeedDaemonReload','Job','FragmentPath','Triggers',
)
SERVICE_EDGE_PROPERTIES = SERVICE_PROPERTIES + ('TriggeredBy',)
EXPECTED = {
    'LoadState':'masked', 'UnitFileState':'masked',
    'ActiveState':'inactive', 'SubState':'dead', 'CanStart':'no',
    'NeedDaemonReload':'no', 'Job':'0', 'FragmentPath':'/dev/null',
}


class ActivationConflict(RevocationConflict):
    """An enrolled activation route is active, unmasked, or changed."""


def _manifest(raw, trusted_sha256):
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_MANIFEST
            or type(trusted_sha256) is not str
            or not _SHA256.fullmatch(trusted_sha256)):
        raise ValueError('invalid bounded systemd activation manifest')
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), trusted_sha256):
        raise ActivationConflict('independent activation manifest pin mismatch')
    data = _strict_json(raw)
    if (type(data) is not dict
            or set(data) != {'schema','service','activation_units'}
            or data['schema'] != SCHEMA
            or raw != _canonical(data)):
        raise ValueError('noncanonical systemd activation manifest')
    service = _unit(data['service'])
    entries = data['activation_units']
    if (type(entries) is not list or not 0 < len(entries) <= MAX_UNITS):
        raise ValueError('at least one bounded activation unit required')
    units = []
    for name in entries:
        if type(name) is not str or not _UNIT.fullmatch(name) or '..' in name:
            raise ValueError('invalid systemd activation unit name')
        units.append(name)
    if units != sorted(set(units)):
        raise ValueError('activation unit names must be sorted and unique')
    return service, tuple(units)


def _decode_properties(raw, fields, requested):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_PROPERTY_OUTPUT:
        raise ActivationConflict('missing or oversized systemd unit inspection')
    try:
        lines = raw.decode('ascii').splitlines()
    except UnicodeError as exc:
        raise ActivationConflict('invalid systemd unit encoding') from exc
    props = {}
    for line in lines:
        field, sep, value = line.partition('=')
        if not sep or field not in fields or field in props:
            raise ActivationConflict('duplicate, unknown or malformed unit field')
        props[field] = value
    if set(props) != set(fields) or props['Id'] != requested:
        raise ActivationConflict('incomplete or mismatched systemd unit identity')
    for field, expected in EXPECTED.items():
        if props[field] != expected:
            raise ActivationConflict('systemd unit remains activatable')
    if 'SubState' in props and props['SubState'] != 'dead':
        raise ActivationConflict('activation unit is not dead')
    return props


def _unit_names(value):
    if type(value) is not str or len(value) > 2048:
        raise ActivationConflict('oversized systemd dependency list')
    names = value.split() if value else []
    if len(names) > MAX_UNITS:
        raise ActivationConflict('oversized systemd activation dependency list')
    if len(set(names)) != len(names):
        raise ActivationConflict('duplicate systemd dependency')
    return tuple(sorted(names))


def _read_activation(unit):
    if not _UNIT.fullmatch(unit):
        raise ValueError('invalid activation unit')
    cmd = ['/usr/bin/systemctl','--system','show','--no-pager']
    for name in ACTIVATION_PROPERTIES:
        cmd.extend(('-p', name))
    cmd.extend(('--', unit))
    process = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, timeout=8, check=False,
        env={'LC_ALL':'C','LANG':'C','PATH':'/usr/bin:/bin'})
    if process.returncode != 0:
        raise ActivationConflict('systemd activation state not readable')
    return process.stdout


def _read_service(unit):
    cmd = ['/usr/bin/systemctl','--system','show','--no-pager']
    for name in SERVICE_EDGE_PROPERTIES:
        cmd.extend(('-p', name))
    cmd.extend(('--', _unit(unit)))
    process = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, timeout=8, check=False,
        env={'LC_ALL':'C','LANG':'C','PATH':'/usr/bin:/bin'})
    if process.returncode != 0:
        raise ActivationConflict('systemd service state not readable')
    return process.stdout


def observe(raw, pin, *, reader=_read_activation, service_reader=_read_service):
    service, units = _manifest(raw, pin)
    allowed = set(units)

    def capture():
        service_props = _decode_properties(
            service_reader(service), SERVICE_EDGE_PROPERTIES, service)
        if service_props['MainPID'] != '0' or service_props['ControlPID'] != '0':
            raise ActivationConflict('target service still has a process')
        # A present unregistered activation relationship is explicitly
        # rejected; missing metadata does NOT prove no hidden triggers.
        observed_service_edges = _unit_names(service_props['TriggeredBy'])
        if any(edge not in allowed for edge in observed_service_edges):
            raise ActivationConflict('unknown systemd activation dependency')
        states = {}
        for name in units:
            state = _decode_properties(
                reader(name), ACTIVATION_PROPERTIES, name)
            targets = _unit_names(state['Triggers'])
            if any(target != service for target in targets):
                raise ActivationConflict('activation unit targets unknown service')
            states[name] = state
        return service_props, states

    before_service, before = capture()
    after_service, after = capture()
    if before_service != after_service or before != after:
        raise ActivationConflict('systemd activation graph changed during scan')
    item = {
        'schema': REPORT_SCHEMA,
        'service': service,
        'activation_manifest_sha256': hashlib.sha256(raw).hexdigest(),
        'activation_units': units,
        'systemd_service': before_service,
        'systemd_activation_units': before,
    }
    return {
        'schema': REPORT_SCHEMA,
        'observation_sha256': hashlib.sha256(
            DOMAIN + _canonical(item)).hexdigest(),
        'enrolled_service_masked_and_inactive': True,
        'enrolled_activation_units_masked_and_inactive': True,
        'all_enrolled_activation_units_checked_twice': True,
        'unregistered_observed_trigger_edges_rejected': True,
        'activation_graph_complete_proved': False,
        'unlisted_systemd_generators_excluded': False,
        'future_activation_prevented': False,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
        'native_switch_game_build_verified': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private_systemd_activation_manifest', type=Path)
    parser.add_argument('independent_manifest_sha256')
    args = parser.parse_args(argv)
    result = {'schema': REPORT_SCHEMA,
              'witness_fence_retirement_authorized': False,
              'witness_fence_retired': False}
    try:
        result.update(observe(
            _private_bytes(args.private_systemd_activation_manifest, MAX_MANIFEST),
            args.independent_manifest_sha256))
        code = 0
    except (ActivationConflict, RevocationConflict):
        result['activation_state_conflict'] = True
        code = 1
    except (OSError, ValueError, TypeError, KeyError, UnicodeError,
            subprocess.SubprocessError):
        result['valid_input'] = False
        code = 2
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
