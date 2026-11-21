from contextlib import nullcontext, redirect_stdout
import hashlib
import io
from ipaddress import IPv4Address
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_own_menu import DIGESTS, Session
import guided
import ethernet
import subprocess
from receipt import Receipt


HOST = IPv4Address('192.0.2.25')
IDENTITY = hashlib.sha256(b'test-only').hexdigest()


class GuidedTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / 'state'
        self.store = Receipt(self.directory)
        self.session = Session(other=True)
        digests = patch.object(guided.menu, 'BASELINE_DIGESTS', DIGESTS)
        digests.start()
        self.addCleanup(digests.stop)
        connection = patch.object(guided.menu, 'open_session', side_effect=lambda host, source: nullcontext(self.session))
        self.connection = connection.start()
        self.addCleanup(connection.stop)
        route = patch.object(guided, 'wired_route', return_value=None)
        self.route = route.start()
        self.addCleanup(route.stop)

    def run_action(self, action, confirm_pending=False, host=HOST, identity=IDENTITY, confirm_write=None):
        enabled, _ = guided.transact(
            action, host, identity, self.directory, lambda: confirm_pending,
            confirm_write or (lambda current, original, desired: True),
        )
        return enabled

    def test_round_trip_restores_original_and_preserves_trainer(self):
        self.assertTrue(self.run_action('apply'))
        self.assertFalse(self.store.load(HOST, IDENTITY)['original_enabled'])
        self.assertTrue(self.run_action('apply'))
        self.assertEqual(self.session.writes, [(guided.menu.OWN_KEY, 1)])
        self.assertFalse(self.run_action('rollback'))
        self.assertFalse(self.run_action('rollback'))
        self.assertEqual(self.session.writes, [(guided.menu.OWN_KEY, 1), (guided.menu.OWN_KEY, 0)])
        other_offset = guided.menu.CONFIG['preserved_other_menu_offset']
        self.assertEqual(self.session.blocks['CarFuncAdap'][other_offset], 1)

    def test_already_enabled_state_is_preserved(self):
        self.session = Session(own=True)
        self.assertTrue(self.run_action('apply'))
        self.assertTrue(self.run_action('rollback'))
        self.assertEqual(self.session.writes, [])

    def test_rollback_does_not_undo_external_change_after_noop_apply(self):
        self.session = Session(own=True)
        self.assertTrue(self.run_action('apply'))
        self.session = Session(own=False)
        with self.assertRaisesRegex(ValueError, 'changed outside'):
            self.run_action('rollback')
        self.assertEqual(self.session.writes, [])

    def test_durable_pending_receipt_precedes_write(self):
        original_send = self.session.sendall

        def send(request):
            receipt = self.store.load(HOST, IDENTITY)
            self.assertEqual(receipt['phase'], 'apply_pending')
            self.assertFalse(receipt['original_enabled'])
            original_send(request)

        self.session.sendall = send
        self.assertTrue(self.run_action('apply'))
        self.assertEqual(self.store.load(HOST, IDENTITY)['phase'], 'applied')

    def test_uncertain_apply_refuses_new_apply_and_recovers_after_confirmation(self):
        original_send = self.session.sendall

        def interrupt_after_send(request):
            original_send(request)
            raise OSError('simulated disconnect')

        self.session.sendall = interrupt_after_send
        with self.assertRaises(OSError):
            self.run_action('apply')
        self.session.sendall = original_send
        self.connection.reset_mock()
        with self.assertRaisesRegex(ValueError, 'previous write is uncertain'):
            self.run_action('apply')
        with self.assertRaises(guided.ChangeCancelled):
            self.run_action('rollback')
        self.connection.assert_not_called()
        self.assertFalse(self.run_action('rollback', confirm_pending=True))
        self.assertEqual(self.store.load(HOST, IDENTITY)['phase'], 'restored')

    def test_uncertain_rollback_recovers_without_repeating_completed_write(self):
        self.assertTrue(self.run_action('apply'))
        original_send = self.session.sendall

        def interrupt_after_send(request):
            original_send(request)
            raise OSError('simulated disconnect')

        self.session.sendall = interrupt_after_send
        with self.assertRaises(OSError):
            self.run_action('rollback')
        self.assertEqual(self.store.load(HOST, IDENTITY)['phase'], 'rollback_pending')
        self.session.sendall = original_send
        self.assertFalse(self.run_action('rollback', confirm_pending=True))
        self.assertEqual(len(self.session.writes), 2)

    def test_pending_receipt_write_failure_blocks_device_write(self):
        save = Receipt.save

        def fail_pending(store, receipt):
            if receipt['phase'] == 'apply_pending':
                raise OSError('simulated storage failure')
            save(store, receipt)

        with patch.object(Receipt, 'save', fail_pending):
            with self.assertRaises(OSError):
                self.run_action('apply')
        self.assertEqual(self.session.writes, [])
        self.assertEqual(self.store.load(HOST, IDENTITY)['phase'], 'prepared')

    def test_missing_damaged_and_mismatched_receipts_block_connection(self):
        with self.assertRaisesRegex(ValueError, 'No recovery receipt'):
            self.run_action('rollback')
        self.connection.assert_not_called()
        self.run_action('apply')
        self.connection.reset_mock()
        with self.assertRaisesRegex(ValueError, 'different address or head-unit identifier'):
            self.run_action('rollback', host=IPv4Address('192.0.2.26'))
        with self.assertRaisesRegex(ValueError, 'different address or head-unit identifier'):
            self.run_action('rollback', identity='different-identity')
        self.store.path.write_bytes(b'{')
        with self.assertRaisesRegex(ValueError, 'receipt is unreadable'):
            self.run_action('rollback')
        self.connection.assert_not_called()

    def test_second_local_transaction_cannot_open_a_connection(self):
        with self.store.lock():
            with self.assertRaisesRegex(ValueError, 'state folder'):
                self.run_action('apply')
        self.connection.assert_not_called()

    def test_guided_manual_confirmation_precedes_network(self):
        with patch('builtins.input', side_effect=['tr', 'hayır']), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'iptal'):
                guided.run('apply', HOST, self.directory, None)
        self.connection.assert_not_called()

    def test_guided_inspect_is_read_only_and_creates_no_receipt(self):
        with patch('builtins.input', side_effect=['yes']), redirect_stdout(io.StringIO()):
            guided.run('inspect', HOST, self.directory, 'en')
        self.assertEqual(self.session.writes, [])
        self.assertFalse(self.directory.exists())

    def test_guided_apply_uses_owner_supplied_ipv4(self):
        answers = ['', 'yes', str(HOST), 'UNIT-01', 'yes']
        with patch('builtins.input', side_effect=answers), redirect_stdout(io.StringIO()) as output:
            guided.run('apply', None, self.directory, None)
        self.connection.assert_called_once_with(HOST, None)
        self.assertIn('currently Off', output.getvalue())
        self.assertIn('setting: On', output.getvalue())
        self.assertNotIn(b'UNIT-01', self.store.path.read_bytes())

    def test_default_ip_and_verified_windows_source_reach_read(self):
        source = IPv4Address('192.168.1.10')
        self.route.return_value = ('Ethernet', source)
        with patch('builtins.input', side_effect=['yes', '']), redirect_stdout(io.StringIO()) as output:
            guided.run('inspect', None, self.directory, 'en')
        self.route.assert_called_once_with(guided.DEFAULT_HOST)
        self.connection.assert_called_once_with(guided.DEFAULT_HOST, source)
        self.assertIn('Ethernet (192.168.1.10)', output.getvalue())

    def test_failed_windows_route_stops_before_connecting(self):
        self.route.side_effect = ValueError('No Ethernet')
        with patch('builtins.input', side_effect=['yes']), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'could not verify a direct Ethernet connection'):
                guided.run('inspect', HOST, self.directory, 'en')
        self.connection.assert_not_called()

    def test_windows_query_acquires_source_only_from_valid_output(self):
        result = subprocess.CompletedProcess([], 0, stdout='{"name":"Ethernet","address":"192.168.1.10"}')
        with patch.object(ethernet.sys, 'platform', 'win32'), patch.object(ethernet.subprocess, 'run', return_value=result) as invoke:
            self.assertEqual(ethernet.wired_route(guided.DEFAULT_HOST), ('Ethernet', IPv4Address('192.168.1.10')))
            self.assertIn("-RemoteIPAddress '192.168.1.4'", invoke.call_args.args[0][-1])
            result.stdout = '{}'
            with self.assertRaisesRegex(ValueError, 'Could not verify'):
                ethernet.wired_route(guided.DEFAULT_HOST)

    def test_first_install_decline_does_not_write_or_leave_a_receipt(self):
        with patch('builtins.input', side_effect=['evet', 'UNIT-01', '']), redirect_stdout(io.StringIO()) as output:
            with self.assertRaisesRegex(ValueError, 'ayarları değişmedi'):
                guided.run('apply', HOST, self.directory, 'tr')
        self.assertIn('şu anda Kapalı', output.getvalue())
        self.assertEqual(self.session.writes, [])
        self.assertFalse(self.store.path.exists())

    def test_rollback_decline_leaves_saved_operation_available(self):
        self.assertTrue(self.run_action('apply'))

        def decline(current, original, desired):
            self.assertEqual((current, original, desired), (True, False, False))
            return False

        with self.assertRaises(guided.ChangeCancelled):
            self.run_action('rollback', confirm_write=decline)
        self.assertEqual(self.store.load(HOST, IDENTITY)['phase'], 'applied')
        self.assertEqual(self.session.writes, [(guided.menu.OWN_KEY, 1)])

    def test_state_is_checked_again_after_confirmation(self):
        def confirm_after_external_change(current, original, desired):
            self.assertEqual((current, original, desired), (False, False, True))
            blocks = bytearray(self.session.blocks['CarFuncAdap'])
            blocks[guided.menu.OWN_OFFSET] = 1
            self.session.blocks['CarFuncAdap'] = bytes(blocks)
            return True

        with self.assertRaisesRegex(ValueError, 'changed after the initial read'):
            self.run_action('apply', confirm_write=confirm_after_external_change)
        self.assertEqual(self.store.load(HOST, IDENTITY)['phase'], 'prepared')
        self.assertEqual(self.session.writes, [])

    def test_already_enabled_skips_final_confirmation(self):
        self.session = Session(own=True)
        with patch('builtins.input', side_effect=['yes', 'UNIT-01']), redirect_stdout(io.StringIO()) as output:
            guided.run('apply', HOST, self.directory, 'en')
        self.assertIn('already matches', output.getvalue())
        self.assertEqual(self.session.writes, [])


if __name__ == '__main__':
    unittest.main()
