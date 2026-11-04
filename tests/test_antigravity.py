"""Offline wire tests for Google's official ACP shape; no Google account calls."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from server.antigravity import AntigravityBridge
from server.conversations import BridgeError


FAKE = r'''
import json,os,sys
from pathlib import Path
def emit(v): print(json.dumps(v),flush=True)
def record(v):
 with open(os.environ['SS_TEST_WIRE'],'a') as f:f.write(json.dumps(v)+'\n')
record({'args':sys.argv[1:],'cwd':os.getcwd(),'capability':os.environ.get('SUPERSURFER_AGENT_CAPABILITY'),'helper':os.environ.get('ANTIGRAVITY_HARNESS_PATH')})
session='session-antigravity'
options=[{'id':'model','category':'model','options':[{'value':'gemini-test','name':'Gemini test'}]}, {'id':'mode','category':'mode','options':[{'value':'default'},{'value':'yolo'}]}]
current=None
for line in sys.stdin:
 v=json.loads(line);record(v);m=v.get('method');p=v.get('params',{});key=v.get('id')
 if m=='initialize':
  emit({'jsonrpc':'2.0','id':key,'result':{'protocolVersion':1,'agentInfo':{'name':'antigravity-acp','title':'Google Antigravity','version':os.environ.get('SS_AGY_VERSION','1.4.5')},'agentCapabilities':{'loadSession':not os.environ.get('SS_AGY_NO_RESUME')},'authMethods':[{'id':'oauth-personal'}]}})
 elif m=='authenticate':
  emit({'jsonrpc':'2.0','id':key,**({'error':{'code':-32000,'message':'NEVER_EXPOSE_TOKEN'}} if os.environ.get('SS_AGY_FAIL_AUTH') else {'result':{}})})
 elif m in ('session/new','session/load'):
  if m=='session/load':emit({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':session,'update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':'HISTORICAL_REPLAY'}}}})
  emit({'jsonrpc':'2.0','id':key,'result':{'sessionId':'foreign-session' if m=='session/load' and os.environ.get('SS_AGY_WRONG_SESSION') else session,'configOptions':options[:1] if os.environ.get('SS_AGY_NO_MODE') else options}})
  if not os.environ.get('SS_AGY_NO_USAGE'):emit({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':session,'update':{'sessionUpdate':'available_commands_update','availableCommands':[{'name':'usage'}]}}})
 elif m=='session/set_config_option':emit({'jsonrpc':'2.0','id':key,'result':{}})
 elif m=='session/prompt':
  current=key;text=p['prompt'][0]['text'].split('User request:\n')[-1].splitlines()[0]
  if text=='/usage':
   if os.environ.get('SS_AGY_USAGE_CRASH'):os._exit(2)
   if os.environ.get('SS_AGY_USAGE_TOOL'):emit({'jsonrpc':'2.0','id':'unexpected-tool','method':'session/request_permission','params':{'sessionId':session}})
   report='### Session Usage\n- **Session total:** 1234 tokens\n\n### Quota Limits\n- **Gemini Models**\n  - **Weekly Limit Remaining:** 91% remaining (resets Nov 11, 2026, 02:31 UTC)'
   if os.environ.get('SS_AGY_USAGE_ERROR'):report='### Quota Limits\n- Unable to retrieve quota status (NEVER_EXPOSE_TOKEN)'
   emit({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':session,'update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':report}}}})
   emit({'jsonrpc':'2.0','id':key,'result':{'stopReason':'end_turn'}});continue
  if text=='crash':os._exit(2)
  if text=='hold':continue
  if text=='approval':
   emit({'jsonrpc':'2.0','id':'permission','method':'session/request_permission','params':{'sessionId':session,'toolCall':{'title':'Run tests','rawInput':{'command':'npm test','token':'NEVER_PERSIST_TOKEN'}},'options':[{'kind':'allow_once','optionId':'allow'},{'kind':'reject_once','optionId':'deny'},{'kind':'allow_always','optionId':'always'}]}});continue
  for t in ('Hello ','world'):emit({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':session,'update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':t}}}})
  emit({'jsonrpc':'2.0','id':key,'result':{'stopReason':'end_turn'}})
 elif key=='permission':emit({'jsonrpc':'2.0','id':current,'result':{'stopReason':'end_turn'}})
'''


class AntigravityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.binary = self.root / 'agy_acp_server.par'
        self.binary.write_text('#!' + sys.executable + '\n' + FAKE)
        self.binary.chmod(0o700)
        (self.root / 'localharness_external').touch()
        self.log = self.root / 'wire'
        self.env = patch.dict(os.environ, {'SUPERSURFER_ANTIGRAVITY': str(self.binary), 'SS_TEST_WIRE': str(self.log)})
        self.env.start()
        self.bridge = self.make_bridge()

    def make_bridge(self):
        return AntigravityBridge('antigravity', self.root / 'state', lambda scope: {
            'cwd': str(self.root), 'role': 'worker', 'name': scope,
            'mcp_servers': {'supersurfer': {'command': sys.executable, 'args': ['tools.py'], 'env': {'SCOPE': scope}}}})

    def tearDown(self):
        self.bridge.close()
        self.env.stop()
        self.tmp.cleanup()

    def wait(self, predicate):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.01)
        self.fail('Antigravity condition timed out')

    def wire(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def connect(self):
        self.assertEqual('provider', self.bridge.login()['type'])
        self.wait(lambda: self.bridge.account(refresh=True)['login']['status'] != 'working')
        self.assertFalse(self.bridge.account(refresh=True)['login_required'])

    def send(self, text='hello', **kwargs):
        self.bridge.send('manager', text, **kwargs)
        self.wait(lambda: not self.bridge.chat('manager')['busy'])
        return self.bridge.chat('manager')

    def test_polling_never_starts_oauth_and_send_requires_explicit_connection(self):
        for _ in range(2):
            self.assertTrue(self.bridge.account(refresh=True)['login_required'])
            self.bridge.models()
        self.assertEqual([], self.wire())
        with self.assertRaises(BridgeError):
            self.bridge.send('manager', 'hello')
        self.assertEqual([], self.bridge.chat('manager')['messages'])

    def test_google_oauth_and_dynamic_models_without_prompt_or_project_tools(self):
        self.connect()
        wire = self.wire()
        self.assertFalse(any(row.get('method') == 'session/prompt' for row in wire))
        auth = next(row['params'] for row in wire if row.get('method') == 'authenticate')
        self.assertEqual({'methodId': 'oauth-personal'}, auth)
        setup = next(row['params'] for row in wire if row.get('method') == 'session/new')
        self.assertEqual(str(self.root / 'state'), setup['cwd'])
        self.assertEqual([], setup['mcpServers'])
        self.assertEqual(['auto', 'gemini-test'], [row['id'] for row in self.bridge.models()['models']])
        self.assertFalse(self.bridge.account()['logout_supported'])
        with self.assertRaises(BridgeError):
            self.bridge.logout()

    def test_quota_uses_only_builtin_on_private_connection_and_caches(self):
        self.assertEqual('unavailable', self.bridge.quota()['status'])
        self.assertEqual([], self.wire())
        self.connect()
        before = len(self.wire())
        quota = self.bridge.quota()
        self.assertEqual(91, quota['windows'][0]['remaining_percent'])
        self.assertEqual(1794364260, quota['windows'][0]['resets_at'])
        quota['windows'].clear()
        self.assertEqual(1, len(self.bridge.quota()['windows']))
        reads = self.wire()[before:]
        self.assertEqual(['session/prompt'], [r.get('method') for r in reads])
        self.assertEqual([{'type': 'text', 'text': '/usage'}], reads[0]['params']['prompt'])
        self.assertEqual([], self.bridge.list_chats())
        self.assertIsNone(self.bridge.quota().get('account_tokens'))

    def test_unknown_runtime_or_missing_command_never_dispatches_usage(self):
        for env in ({'SS_AGY_VERSION': '1.4.6'}, {'SS_AGY_NO_USAGE': '1'}):
            with self.subTest(env=env), patch.dict(os.environ, env):
                self.connect()
                self.assertEqual('unavailable', self.bridge.quota()['status'])
        self.assertFalse(any(r.get('method') == 'session/prompt' for r in self.wire()))

    def test_failed_quota_never_reconnects_replays_or_exposes_error(self):
        with patch.dict(os.environ, {'SS_AGY_USAGE_CRASH': '1'}):
            self.connect()
        self.assertEqual('unavailable', self.bridge.quota()['status'])
        before = len(self.wire())
        self.assertEqual('unavailable', self.bridge.quota()['status'])
        self.assertEqual(before, len(self.wire()))
        self.assertEqual(1, sum(r.get('method') == 'session/prompt' for r in self.wire()))

    def test_native_quota_error_does_not_become_zero_or_leak(self):
        with patch.dict(os.environ, {'SS_AGY_USAGE_ERROR': '1'}):
            self.connect()
        quota = self.bridge.quota()
        self.assertEqual('unavailable', quota['status'])
        self.assertIsNone(quota['observed_at'])
        self.assertNotIn('NEVER_EXPOSE', json.dumps(quota))

    def test_quota_timeout_is_bounded_and_discards_channel(self):
        self.connect()
        connection = self.bridge._login_connection
        with patch.object(connection, 'call', side_effect=BridgeError('PRIVATE timeout')) as call:
            self.assertEqual('unavailable', self.bridge.quota()['status'])
        self.assertEqual(15, call.call_args.kwargs['timeout'])
        self.assertIsNotNone(connection.proc.poll())
        self.assertIsNone(self.bridge._quota_channel)
        self.assertNotIn('PRIVATE', json.dumps(self.bridge.quota()))

    def test_quota_rejects_unexpected_client_execution_and_discards_result(self):
        with patch.dict(os.environ, {'SS_AGY_USAGE_TOOL': '1'}):
            self.connect()
        self.assertEqual('unavailable', self.bridge.quota()['status'])
        reply = next(r for r in self.wire() if r.get('id') == 'unexpected-tool' and 'error' in r)
        self.assertEqual(-32601, reply['error']['code'])
        self.assertIsNone(self.bridge._quota_channel)

    def test_reconnect_drops_previous_account_quota_cache(self):
        self.connect()
        first = self.bridge._login_connection
        self.assertEqual('available', self.bridge.quota()['status'])
        with patch.dict(os.environ, {'SS_AGY_USAGE_ERROR': '1'}):
            self.connect()
        self.assertIsNot(first, self.bridge._login_connection)
        self.assertIsNotNone(first.proc.poll())
        self.assertEqual('unavailable', self.bridge.quota()['status'])

    def test_selected_model_native_mode_scoped_tools_and_streaming(self):
        self.connect()
        self.assertEqual('completed', self.send(model='gemini-test')['status'])
        wire = self.wire()
        self.assertEqual([], wire[0]['args'] if not sys.platform.startswith('linux') else wire[0]['args'][1:])
        session = [row['params'] for row in wire if row.get('method') == 'session/new'][-1]
        self.assertEqual([{'name': 'SCOPE', 'value': 'manager'}], session['mcpServers'][0]['env'])
        self.assertEqual(['ask_question'], session['_meta']['agy']['disabledTools'])
        methods = [row.get('method') for row in wire]
        self.assertLess(methods.index('session/set_config_option'), methods.index('session/prompt'))
        settings = [row['params'] for row in wire if row.get('method') == 'session/set_config_option']
        self.assertEqual(['default', 'gemini-test'], [row['value'] for row in settings])
        self.assertEqual('Hello world', [row['text'] for row in self.bridge.chat('manager')['messages'] if row['role'] == 'assistant'][-1])

    def test_failed_auth_is_sanitized_and_does_not_send_a_model_prompt(self):
        with patch.dict(os.environ, {'SS_AGY_FAIL_AUTH': '1'}):
            self.bridge.login()
            self.wait(lambda: self.bridge.account(refresh=True)['login']['status'] == 'failed')
        self.assertNotIn('NEVER_EXPOSE', json.dumps(self.bridge.account()))
        self.assertFalse(any(row.get('method') == 'session/prompt' for row in self.wire()))

    def test_unavailable_model_or_unverified_permissions_never_sends_prompt(self):
        self.connect()
        self.assertEqual('failed', self.send(model='wrong-model')['status'])
        with patch.dict(os.environ, {'SS_AGY_NO_MODE': '1'}):
            self.assertEqual('failed', self.send()['status'])
        self.assertFalse(any(row.get('method') == 'session/prompt' for row in self.wire()))

    def test_resume_keeps_session_and_suppresses_history_replay(self):
        self.connect()
        first = self.send()
        second = self.send()
        self.assertEqual(first['thread_id'], second['thread_id'])
        self.assertNotIn('HISTORICAL_REPLAY', json.dumps(second))
        self.assertTrue(any(row.get('method') == 'session/load' for row in self.wire()))
        with patch.dict(os.environ, {'SS_AGY_NO_RESUME': '1'}):
            self.assertEqual('failed', self.send()['status'])
        with patch.dict(os.environ, {'SS_AGY_WRONG_SESSION': '1'}):
            self.assertIn('different saved session', self.send()['error'])
        self.assertEqual(2, sum(row.get('method') == 'session/prompt' for row in self.wire()))
        self.bridge.close()
        self.bridge = self.make_bridge()
        self.assertEqual(first['thread_id'], self.bridge.chat('manager')['thread_id'])
        self.assertTrue(self.bridge.account()['login_required'])

    def test_ask_approvals_stop_and_yolo_choose_only_allow_once(self):
        self.connect()
        self.bridge.send('manager', 'approval')
        self.wait(lambda: bool(self.bridge.chat('manager')['approvals']))
        self.assertNotIn('NEVER_PERSIST', json.dumps(self.bridge.chat('manager')))
        self.bridge.stop('manager')
        self.wait(lambda: not self.bridge.chat('manager')['busy'])
        self.assertFalse(any(row['status'] == 'pending' for row in self.bridge.chat('manager')['approvals']))
        self.assertEqual('completed', self.send('approval', approval_mode='yolo')['status'])
        reply = next(row for row in self.wire() if row.get('id') == 'permission' and 'result' in row)
        self.assertEqual('allow', reply['result']['outcome']['optionId'])

    def test_uncertain_disconnect_is_never_replayed(self):
        self.connect()
        self.assertEqual('failed', self.send('crash')['status'])
        self.assertEqual(1, sum(row.get('method') == 'session/prompt' for row in self.wire()))


if __name__ == '__main__':
    unittest.main()
