"""Provider observations survive restarts without double counting or invented zeros."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from server import usage
from server.codex import CodexBridge
from server.conversations import BridgeError
import test_cli_backends as cli_fixture
import test_backend_routing as routing_fixture
import test_conversations as conversation_fixture


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = cli_fixture.CliBackendTests()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def test_claude_quota_control_never_sends_a_prompt_or_loads_a_session(self):
        result = {'rate_limits_available': True, 'rate_limits': {
            'five_hour': {'utilization': 25, 'resets_at': '2026-10-26T23:00:00Z'},
            'seven_day': {'utilization': 100, 'resets_at': None}, 'secret': 'NEVER_PUBLISH'}}
        source = cli_fixture.FAKE.replace("'response':{}}})", "'response':" + repr(result) + "}})")
        self.fixture.binary.write_text('#!' + cli_fixture.sys.executable + '\n' + source)
        value = self.fixture.bridge().quota()
        self.assertEqual([75, 0], [x['remaining_percent'] for x in value['windows']])
        self.assertIsNotNone(value['windows'][0]['resets_at'])
        self.assertNotIn('NEVER_PUBLISH', json.dumps(value))
        records = self.fixture.records()
        self.assertEqual(['initialize', 'get_usage'], [x['request']['subtype'] for x in records if x.get('type') == 'control_request'])
        self.assertTrue(records[-1]['request']['skip_behaviors'])
        self.assertFalse(any(x.get('type') == 'user' for x in records))
        self.assertEqual('unavailable', usage.claude_quota({'rate_limits_available': False})['status'])

    def test_antigravity_parses_only_native_quota_section_and_preserves_zero(self):
        report = ("### Session Usage\n- **Session total:** 123,456 tokens\n"
                  "- **Bogus:** 99% remaining\n\n### Quota Limits\n"
                  "- **Gemini Models**\n  - **Weekly:** 0% remaining (resets Nov 11, 2026, 02:31 UTC)\n"
                  "- **Other models**\n  - **Weekly:** 100% remaining\n"
                  "  - **Requests:** 1,234 units remaining\n"
                  "  - **Disabled:** Disabled\n  - **Broken:** 101% remaining\n"
                  "  - **Unknown:** Available\n  - **Negative:** -1% remaining")
        data = usage.antigravity_quota(report)
        self.assertEqual([0, 100, None], [w.get('remaining_percent') for w in data['windows']])
        self.assertEqual(1234, data['windows'][2]['remaining_units'])
        self.assertEqual(1794364260, data['windows'][0]['resets_at'])
        self.assertIsNone(data['windows'][1]['resets_at'])
        for report in (None, {}, '', '### Session Usage\n- **Session total:** 0 tokens',
                       '### Quota Limits\n- Unable to retrieve quota status (SECRET)', 'x'*32001):
            data = usage.antigravity_quota(report)
            self.assertEqual('unavailable', data['status'])
            self.assertIsNone(data['observed_at'])
            self.assertNotIn('SECRET', json.dumps(data))

    def test_account_tokens_are_allowlisted_zero_is_known_and_not_host_consumption(self):
        self.assertIsNone(usage.account_tokens({}))
        value = usage.account_tokens({'summary': {'lifetimeTokens': 0, 'secret': 'NEVER_PUBLISH'}})
        self.assertEqual(0, value['value'])
        self.assertIn('across clients', value['scope'])
        self.assertNotIn('NEVER_PUBLISH', json.dumps(value))
        self.assertIsNone(usage.account_tokens({'summary': {'lifetimeTokens': '0'}}))

    def test_opencode_export_is_owned_sanitized_replay_safe_and_optional(self):
        bridge = self.fixture.bridge('opencode')
        info = {'id': 'ses_usage', 'cost': .23, 'tokens': {'input': 10, 'output': 3, 'reasoning': 2, 'cache': {'read': 5, 'write': 1}}}
        response = SimpleNamespace(returncode=0, stdout=json.dumps({'info': info, 'messages': [{'text': 'NEVER_PERSIST_TRANSCRIPT'}]}))
        with patch('server.opencode.subprocess.run', return_value=response) as run:
            bridge.observe_usage('ses_usage', str(self.fixture.repo))
            bridge.observe_usage('ses_usage', str(self.fixture.repo))
        self.assertEqual(['export', 'ses_usage', '--sanitize'], run.call_args.args[0][1:])
        self.assertEqual(21, usage.consumption(bridge)['tokens']['value'])
        self.assertEqual(.23, usage.consumption(bridge)['cost_usd']['value'])
        with patch('server.opencode.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps({'info': {**info, 'id': 'foreign', 'cost': 999}}))):
            bridge.observe_usage('ses_usage', str(self.fixture.repo))
        self.assertEqual(.23, usage.consumption(bridge)['cost_usd']['value'])
        self.assertNotIn('NEVER_PERSIST_TRANSCRIPT', json.dumps(usage.consumption(bridge)))
        with patch('server.opencode.subprocess.run', side_effect=OSError('unavailable')):
            bridge.observe_usage('ses_usage', str(self.fixture.repo))
        self.assertEqual(21, usage.consumption(bridge)['tokens']['value'])

    def test_claude_stream_result_replay_resume_and_restart(self):
        source = cli_fixture.FAKE.replace("'session_id':session})\n  elif v.get('type')=='control_response'", "'session_id':session,'usage':{'input_tokens':10,'output_tokens':3,'cache_read_input_tokens':2},'total_cost_usd':0.25})\n  elif v.get('type')=='control_response'")
        self.assertNotEqual(source, cli_fixture.FAKE)
        self.fixture.binary.write_text('#!' + cli_fixture.sys.executable + '\n' + source)
        bridge = self.fixture.bridge()
        scope = 'experiment:usage'
        for i in range(2):
            bridge.send(scope, 'hello')
            self.fixture.wait(lambda: not bridge.chat(scope)['busy'])
            self.assertEqual('completed', bridge.chat(scope)['status'])
        data = usage.consumption(bridge)
        self.assertEqual(30, data['tokens']['value'])
        self.assertEqual(.25, data['cost_usd']['value'])
        # The same native result arriving twice does not add another turn/sample.
        chat = bridge._chats[scope]
        usage.claude_result(bridge, chat, {'usage': {'input_tokens': 10, 'output_tokens': 3, 'cache_read_input_tokens': 2}, 'total_cost_usd': .25})
        self.assertEqual(30, usage.consumption(bridge)['tokens']['value'])
        bridge.close()
        restarted = self.fixture.bridge()
        self.assertEqual(data['cost_usd']['value'], usage.consumption(restarted)['cost_usd']['value'])
        self.assertEqual(30, usage.consumption(restarted)['tokens']['value'])

    def test_acp_context_occupancy_is_not_consumption_and_cost_is_idempotent(self):
        for provider in ('cursor', 'opencode'):
            bridge = self.fixture.bridge(provider)
            self.assertIsNone(usage.consumption(bridge)['tokens'])
            chat = {'thread_id': 'session-usage'}
            for amount in (.1, .1, .2, 0):
                usage.acp_update(bridge, chat, {'used': 53000, 'size': 200000, 'cost': {'currency': 'USD', 'amount': amount}})
            self.assertEqual(.2, usage.consumption(bridge)['cost_usd']['value'])
            self.assertIsNone(usage.consumption(bridge)['tokens'])
            usage.acp_update(bridge, chat, {'cost': {'currency': 'EUR', 'amount': 100}})
            self.assertEqual(.2, usage.consumption(bridge)['cost_usd']['value'])

    def test_codex_cumulative_thread_tokens_include_post_turn_event_and_persist(self):
        bridge = CodexBridge(self.fixture.root / 'codex', lambda scope: {})
        self.fixture.bridges.append(bridge)
        chat = bridge._new_chat('experiment:usage', {})
        chat['thread_id'] = 'thread-1'
        bridge._chats[chat['scope']] = chat
        for count in (0, 100, 100, 200):
            bridge._event('thread/tokenUsage/updated', {'threadId': 'thread-1', 'tokenUsage': {'total': {'totalTokens': count}, 'last': {'totalTokens': 50}}})
        self.assertEqual(200, usage.consumption(bridge)['tokens']['value'])
        self.assertIsNone(usage.consumption(bridge)['cost_usd'])
        bridge._event('thread/tokenUsage/updated', {'threadId': 'unowned', 'tokenUsage': {'total': {'totalTokens': 10000}}})
        self.assertEqual(200, usage.consumption(bridge)['tokens']['value'])

    def test_quota_zero_unknown_sanitization_and_multiple_windows(self):
        self.assertEqual('unavailable', usage.quota({})['status'])
        data = usage.quota({'rateLimitsByLimitId': {'codex': {'primary': {'usedPercent': 100, 'resetsAt': 1800000000}, 'secondary': {'usedPercent': 0}, 'secret': 'NEVER_PUBLISH'}}})
        self.assertEqual([0, 100], [x['remaining_percent'] for x in data['windows']])
        self.assertNotIn('NEVER_PUBLISH', json.dumps(data))
        credits = usage.quota({'rateLimits': {'credits': {'balance': '12.50', 'unlimited': False, 'token': 'NEVER_PUBLISH'}}})
        self.assertEqual(12.5, credits['windows'][0]['remaining_credits'])
        self.assertNotIn('NEVER_PUBLISH', json.dumps(credits))
        bridge = self.fixture.bridge()
        for bad in (True, '0.3', float('inf'), -1, float('nan'), 10**500):
            usage.record(bridge, 'cost_usd', 'bad', bad, 'test')
        self.assertIsNone(usage.consumption(bridge)['cost_usd'])
        usage.record(bridge, 'cost_usd', 'zero', 0, 'test')
        self.assertEqual(0, usage.consumption(bridge)['cost_usd']['value'])


class UsageRoutingTests(unittest.TestCase):
    def test_quota_failure_does_not_sign_out_or_erase_consumption(self):
        fixture = routing_fixture.ProviderServiceTests()
        fixture.setUp()
        try:
            bridge = fixture.service.codex.provider('codex')
            usage.record(bridge, 'tokens', 'thread', 123, 'fixture')
            with patch.object(bridge, 'installed', return_value=True), patch.object(bridge, 'account', return_value={'account': {'type': 'chatgpt'}, 'login_required': False}), patch.object(bridge, '_rpc', side_effect=BridgeError('PRIVATE_FAILURE')):
                result = fixture.service.codex.account('codex')
            self.assertFalse(result['login_required'])
            self.assertEqual('unavailable', result['usage']['quota']['status'])
            self.assertEqual(123, result['usage']['consumption']['tokens']['value'])
            self.assertNotIn('PRIVATE_FAILURE', json.dumps(result))
        finally:
            fixture.tearDown()


class ManualCreationTests(unittest.TestCase):
    def test_provider_creation_is_idle_atomic_idempotent_scoped_and_durable(self):
        fixture = conversation_fixture.ConversationTests()
        fixture.setUp()
        try:
            service = fixture.service
            fields = {'experiment_id': fixture.exp['id'], 'project_id': 'p1', 'name': 'UI developer', 'backend': 'claude', 'request_id': 'create-usage-test-0001'}
            first = service.action('experiment.agent.create', fields)
            second = service.action('experiment.agent.create', fields)
            self.assertEqual(first['scope'], second['scope'])
            self.assertEqual(2, len(second['agents']))
            self.assertEqual('claude', service.store.chat_settings(first['scope'])['backend'])
            self.assertEqual([], service.codex.sent)
            self.assertTrue(all(op == 'status' for op, _ in fixture.manager.calls))
            for extra in ({'project_id': 'foreign'}, {'backend': 'invalid'}, {'request_id': 'short'}, {'name': ''}, {'role': 'manager'}, {'name': 'changed'}):
                with self.assertRaises(ValueError):
                    service.action('experiment.agent.create', {**fields, **extra})
            self.assertEqual(2, len(service.experiment_agents(fixture.exp['id'])['agents']))
            service.read_only = True
            with self.assertRaises(ValueError):
                service.action('experiment.agent.create', fields)
            service.close()
            fixture.open_service()
            self.assertEqual(first['scope'], fixture.service.action('experiment.agent.create', fields)['scope'])
            self.assertEqual('claude', fixture.service.store.chat_settings(first['scope'])['backend'])
        finally:
            fixture.tearDown()
