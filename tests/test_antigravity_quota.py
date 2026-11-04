"""Native CLI metadata only: no OAuth, ACP session, agent prompt or billing."""
import json
import subprocess
import unittest
from unittest.mock import patch

from server import usage
import test_antigravity as agy_fixture


def report(fraction=0.75):
    return {"status": "SUCCESS", "conversation_id": "", "num_turns": 0,
            "response": "DO_NOT_PUBLISH_RESPONSE", "usage": {"total_tokens": 99999},
            "command": {"name": "usage", "data": {"secret": "DO_NOT_PUBLISH_SECRET", "groups": [
                {"name": "Gemini Models", "buckets": [{"remaining_fraction": fraction, "window": "weekly", "reset_time": "2026-11-11T02:24:22Z"}]},
                {"name": "Claude and GPT models", "buckets": [{"remaining_fraction": 0, "window": "weekly", "reset_time": None}]}]}}}


class QuotaNormalizationTests(unittest.TestCase):
    def test_groups_zero_timestamp_and_allowlist(self):
        value = usage.antigravity_quota(report())
        self.assertEqual([75, 0], [w['remaining_percent'] for w in value['windows']])
        self.assertEqual(10080, value['windows'][0]['window_minutes'])
        self.assertIsNotNone(value['windows'][0]['resets_at'])
        self.assertIsNone(value['windows'][1]['resets_at'])
        self.assertNotIn('DO_NOT_PUBLISH', json.dumps(value))
        self.assertNotIn('tokens', json.dumps(value))
        self.assertIn('can differ', value['note'])

    def test_reject_agent_results_text_and_invalid_fractions(self):
        for change in ({'num_turns': 1}, {'num_turns': False}, {'conversation_id': 'a-session'},
                       {'status': 'ERROR'}, {'command': {}}, {'command': None}):
            with self.subTest(change=change):
                self.assertEqual('unavailable', usage.antigravity_quota({**report(), **change})['status'])
        for value in (None, True, '0.5', -1, float('nan'), float('inf'), 2):
            candidate = report(value)
            candidate['command']['data']['groups'] = candidate['command']['data']['groups'][:1]
            self.assertEqual([], usage.antigravity_quota(candidate)['windows'])
        self.assertEqual('unavailable', usage.antigravity_quota({'response': '99% remaining'})['status'])


class NativeQuotaTests(unittest.TestCase):
    def setUp(self):
        self.fixture = agy_fixture.AntigravityTests()
        self.fixture.setUp()
        self.bridge = self.fixture.bridge

    def tearDown(self):
        self.fixture.tearDown()

    @staticmethod
    def replies(data=None):
        return [subprocess.CompletedProcess([], 0, '1.4.12\n', ''),
                subprocess.CompletedProcess([], 0, json.dumps(data or report()), '')]

    def test_safe_commands_isolated_cwd_cache_and_force_refresh(self):
        with patch('server.antigravity.subprocess.run', side_effect=self.replies() + self.replies(report(.5))) as run:
            first = self.bridge.quota()
            self.assertEqual(first, self.bridge.quota())
            self.assertEqual(2, run.call_count)
            self.assertEqual(50, self.bridge.quota(refresh=True)['windows'][0]['remaining_percent'])
        for i, call in enumerate(run.call_args_list):
            self.assertEqual(['--version'] if i % 2 == 0 else ['-p', '/usage', '--output-format', 'json', '--disable-slash-commands=false'], call.args[0][1:])
            self.assertEqual(self.bridge.state_dir, call.kwargs['cwd'])
            self.assertEqual(subprocess.DEVNULL, call.kwargs['stdin'])
            self.assertFalse(any(k.startswith('SUPERSURFER_AGENT_') for k in call.kwargs['env']))
        self.assertTrue(self.bridge.account()['login_required'], 'CLI metadata cannot authenticate ACP')
        self.assertEqual([], self.fixture.wire())
        self.assertIsNone(usage.consumption(self.bridge)['tokens'])

    def test_old_unknown_and_future_major_versions_never_receive_usage_prompt(self):
        for version in ('1.0.1', '1.1.10', '2.0.0', 'not-agy', '1.4.12-preview', ''):
            with patch('server.antigravity.subprocess.run', return_value=subprocess.CompletedProcess([], 0, version, '')) as run:
                self.assertEqual('unavailable', self.bridge.quota(refresh=True)['status'])
                self.assertEqual(1, run.call_count)

    def test_native_failure_keeps_timestamped_stale_data_and_hides_errors(self):
        with patch('server.antigravity.subprocess.run', side_effect=self.replies()):
            first = self.bridge.quota()
        with patch('server.antigravity.subprocess.run', side_effect=OSError('DO_NOT_PUBLISH_SECRET')):
            stale = self.bridge.quota(refresh=True)
        self.assertTrue(stale['stale'])
        self.assertEqual(first['windows'], stale['windows'])
        self.assertEqual(first['observed_at'], stale['observed_at'])
        self.assertNotIn('DO_NOT_PUBLISH', json.dumps(stale))

    def test_failed_malformed_or_model_response_is_unavailable(self):
        for response in (subprocess.CompletedProcess([], 1, '', 'DO_NOT_PUBLISH'),
                         subprocess.CompletedProcess([], 0, 'not json', ''),
                         subprocess.CompletedProcess([], 0, json.dumps({**report(), 'num_turns': 1}), '')):
            with patch('server.antigravity.subprocess.run', side_effect=[self.replies()[0], response]):
                self.assertEqual('unavailable', self.bridge.quota(refresh=True)['status'])
        with patch('server.antigravity.subprocess.run', side_effect=subprocess.TimeoutExpired('agy', 5)):
            self.assertEqual('unavailable', self.bridge.quota(refresh=True)['status'])


if __name__ == '__main__':
    unittest.main()
