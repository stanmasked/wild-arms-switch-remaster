"""Synthetic stage-263I systemd socket/timer/path activation regressions."""
import contextlib
import hashlib
import io
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from tools import audit_record_linux_activation_units as app

SERVICE = 'custodian-writer.service'
UNITS = (
    'custodian-writer.path',
    'custodian-writer.socket',
    'custodian-writer.timer',
)


class SystemdActivationTests(unittest.TestCase):
    def setUp(self):
        self.names = UNITS
        self.raw = app._canonical({
            'schema': app.SCHEMA, 'service': SERVICE,
            'activation_units': list(self.names),
        })
        self.pin = hashlib.sha256(self.raw).hexdigest()
        self.calls = []
        self.service_calls = 0
        self.changes = {}
        self.service_changes = {}
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def state(self, name):
        body = {
            'Id': name, 'LoadState': 'masked', 'UnitFileState': 'masked',
            'ActiveState': 'inactive', 'SubState': 'dead', 'CanStart': 'no',
            'NeedDaemonReload': 'no', 'Job': '0',
            'FragmentPath': '/dev/null', 'Triggers': SERVICE,
        }
        body.update(self.changes.get(name, {}))
        return (''.join(f'{k}={body[k]}\n'
                        for k in app.ACTIVATION_PROPERTIES)).encode('ascii')

    def service(self):
        body = {
            'Id': SERVICE, 'LoadState': 'masked', 'UnitFileState': 'masked',
            'ActiveState': 'inactive', 'SubState': 'dead', 'CanStart': 'no',
            'NeedDaemonReload': 'no', 'Job': '0', 'FragmentPath': '/dev/null',
            'MainPID': '0', 'ControlPID': '0',
            'TriggeredBy': ' '.join(UNITS),
        }
        body.update(self.service_changes)
        return (''.join(f'{k}={body[k]}\n'
                        for k in app.SERVICE_EDGE_PROPERTIES)).encode('ascii')

    def reader(self, unit):
        self.calls.append(unit)
        return self.state(unit)

    def sreader(self, unit):
        self.assertEqual(unit, SERVICE)
        self.service_calls += 1
        return self.service()

    def run_observe(self, *, raw=None, pin=None, reader=None, service_reader=None):
        content = self.raw if raw is None else raw
        return app.observe(
            content,
            self.pin if pin is None else pin,
            reader=self.reader if reader is None else reader,
            service_reader=self.sreader if service_reader is None else service_reader)

    def test_masked_activation_is_observation_not_release(self):
        output = self.run_observe()
        self.assertEqual(self.calls, list(UNITS)*2)
        self.assertEqual(self.service_calls, 2)
        self.assertTrue(output['all_enrolled_activation_units_checked_twice'])
        for key in ('activation_graph_complete_proved',
                    'future_activation_prevented',
                    'witness_fence_retirement_authorized',
                    'witness_fence_retired'):
            self.assertFalse(output[key])

    def test_runtime_only_mask_or_enabled_unit_fails(self):
        for state in ('masked-runtime', 'enabled', 'static'):
            with self.subTest(state=state):
                self.changes = {UNITS[1]: {'UnitFileState': state}}
                with self.assertRaises(app.ActivationConflict):
                    self.run_observe()

    def test_active_socket_or_timer_fails(self):
        for field, value in (('ActiveState','active'), ('SubState','listening'),
                             ('Job','77'), ('CanStart','yes'),
                             ('NeedDaemonReload','yes')):
            with self.subTest(field=field):
                self.changes = {UNITS[1]: {field:value}}
                with self.assertRaises(app.ActivationConflict):
                    self.run_observe()

    def test_unmasked_or_running_service_fails(self):
        for field, value in (('UnitFileState','enabled'), ('ActiveState','active'),
                             ('MainPID','42'), ('ControlPID','43')):
            with self.subTest(field=field):
                self.service_changes = {field:value}
                with self.assertRaises(app.ActivationConflict):
                    self.run_observe()

    def test_unknown_triggeredby_service_edge_refused(self):
        self.service_changes = {
            'TriggeredBy':' '.join(UNITS)+' outsider.socket',
        }
        with self.assertRaises(app.ActivationConflict):
            self.run_observe()

    def test_activation_triggering_another_service_refused(self):
        self.changes = {UNITS[1]: {'Triggers':'other.service'}}
        with self.assertRaises(app.ActivationConflict):
            self.run_observe()

    def test_empty_trigger_metadata_is_not_called_complete(self):
        self.service_changes = {'TriggeredBy':''}
        self.changes = {name:{'Triggers':''} for name in UNITS}
        output = self.run_observe()
        self.assertFalse(output['activation_graph_complete_proved'])
        self.assertFalse(output['unlisted_systemd_generators_excluded'])

    def test_changed_unit_state_between_scans_refused(self):
        counter = [0]
        def changing(unit):
            if unit == UNITS[-1]:
                counter[0] += 1
                if counter[0] == 2:
                    return self.state(unit).replace(
                        b'Triggers='+SERVICE.encode(),
                        b'Triggers=')
            return self.state(unit)
        with self.assertRaises(app.ActivationConflict):
            self.run_observe(reader=changing)

    def test_changed_service_edge_between_scans_refused(self):
        def changed(unit):
            self.service_calls += 1
            if self.service_calls == 2:
                self.service_changes['TriggeredBy'] = UNITS[0]
            return self.service()
        with self.assertRaises(app.ActivationConflict):
            self.run_observe(service_reader=changed)

    def test_missing_or_duplicate_unit_property_refused(self):
        sample = self.state(UNITS[0])
        bad = [sample + b'Id=' + UNITS[0].encode() + b'\n',
               sample.replace(b'FragmentPath=/dev/null\n', b''),
               sample + b'BadField=yes\n', b'']
        for data in bad:
            with self.subTest(data=data[-20:]):
                with self.assertRaises(app.ActivationConflict):
                    self.run_observe(reader=lambda unit: data)

    def test_manifest_wrong_pin_or_reordering_refused(self):
        with self.assertRaises(app.ActivationConflict):
            self.run_observe(pin='f'*64)
        altered = app._canonical({
            'schema':app.SCHEMA, 'service':SERVICE,
            'activation_units':list(reversed(UNITS)),
        })
        with self.assertRaises(ValueError):
            self.run_observe(raw=altered, pin=hashlib.sha256(altered).hexdigest())

    def test_duplicate_or_illegal_activation_names_refused(self):
        for entries in ([UNITS[0],UNITS[0]], ['hack.mount'],
                        ['../secret.socket'], ['bad;touch.socket'], []):
            with self.subTest(entries=entries):
                raw = app._canonical({
                    'schema':app.SCHEMA,'service':SERVICE,
                    'activation_units':entries,
                })
                with self.assertRaises(ValueError):
                    self.run_observe(raw=raw,
                                     pin=hashlib.sha256(raw).hexdigest())

    def test_duplicate_or_overlong_dependencies_refused(self):
        for edge in (UNITS[0]+' '+UNITS[0], 'x'*2049):
            self.service_changes = {'TriggeredBy':edge}
            with self.assertRaises(app.ActivationConflict):
                self.run_observe()

    def test_noncanonical_json_and_unknown_schema_refused(self):
        for raw in (self.raw[:-1],
                    self.raw.replace(b'unit-inventory-v1',
                                     b'unit-inventory-v0')):
            with self.assertRaises(ValueError):
                self.run_observe(raw=raw, pin=hashlib.sha256(raw).hexdigest())

    def test_cli_output_does_not_expose_unit_names_or_unlock(self):
        manifest = Path(self.tmp.name)/'activation.json'
        manifest.write_bytes(self.raw)
        manifest.chmod(0o600)
        expected = {
            'schema': app.REPORT_SCHEMA,
            'witness_fence_retired': False,
            'witness_fence_retirement_authorized': False,
        }
        with patch.object(app, 'observe', return_value=expected):
            with contextlib.redirect_stdout(out := io.StringIO()):
                code = app.main([str(manifest), self.pin])
        self.assertEqual(code, 0)
        report = json.loads(out.getvalue())
        self.assertFalse(report['witness_fence_retired'])
        self.assertNotIn(SERVICE, out.getvalue())
        self.assertNotIn(UNITS[0], out.getvalue())

    def test_malformed_service_identity_refused(self):
        with self.assertRaises(app.ActivationConflict):
            self.run_observe(service_reader=lambda unit:
                             self.service().replace(
                                 b'Id='+SERVICE.encode(),
                                 b'Id=other.service'))


if __name__ == '__main__':
    unittest.main()
