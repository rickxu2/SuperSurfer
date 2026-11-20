import json
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile
import hashlib

from server.provider_updates import ProviderUpdates, antigravity_update
from server.conversations import BridgeError


class Memory:
    def __init__(self): self.data={}
    def get(self,k,d=None): return self.data.get(k,d)
    def put(self,k,v): self.data[k]=json.loads(json.dumps(v))


class UpdatesTests(unittest.TestCase):
    def setUp(self):
        self.closed=[];self.busy=set()
        self.bridges={p:SimpleNamespace(_login={},close=lambda p=p:self.closed.append(p)) for p in ('codex','claude','cursor','opencode','antigravity')}
        def idle(p):
            if p in self.busy: raise BridgeError('Active provider turn',409)
            return self.bridges[p]
        self.router=SimpleNamespace(account_locks={p:threading.RLock() for p in self.bridges},_require_account_idle=idle,bridges=dict(self.bridges),lock=threading.RLock())
        self.s=SimpleNamespace(store=Memory(),codex=self.router,read_only=False,_model_defaults_cache={'old':1},model_lock=threading.RLock(),_models_cache={'old':1},_models_checked_at=100,_models_error=None)
        self.u=ProviderUpdates(self.s)
    def tearDown(self):self.u.close()
    def wait(self):
        if self.u.thread:self.u.thread.join(5);self.assertFalse(self.u.thread.is_alive())
    def installed(self,p):
        if p!='codex':raise BridgeError('Missing')
        return '/official/bin/codex'
    def test_opt_in_persisted_schedule_and_idle_defer(self):
        self.busy.add('codex')
        with patch('server.provider_updates.executable',side_effect=self.installed),patch('server.provider_updates.run') as run:
            self.u.tick();run.assert_not_called()
            self.u.configure(True);self.wait();run.assert_not_called()
        data=self.u.status();self.assertTrue(data['enabled']);self.assertEqual(data['providers']['codex']['status'],'deferred');self.assertLess(data['next_check']-time.time(),61)
        self.u.configure(False);self.assertFalse(self.s.store.data['provider_updates']['enabled'])
    def test_native_update_uses_fixed_commands_and_recycles_only_changed_idle_provider(self):
        results=iter(['codex-cli 0.164.0','Commands:\n update Update Codex','', 'codex-cli 0.170.0'])
        with patch('server.provider_updates.executable',side_effect=self.installed),patch('server.provider_updates.run',side_effect=lambda *a,**k:next(results)) as run:
            self.u.start(force=True);self.wait()
        self.assertEqual([c.args[0] for c in run.call_args_list],[['/official/bin/codex','--version'],['/official/bin/codex','--help'],['/official/bin/codex','update'],['/official/bin/codex','--version']])
        self.assertEqual(self.closed,['codex']);self.assertNotIn('codex',self.router.bridges);self.assertEqual(self.s._model_defaults_cache,{})
        self.assertEqual(self.u.status()['providers']['codex']['version'],'0.170.0')
    def test_current_and_unsupported_do_not_reset_connections(self):
        for help_text,status in [('Commands:\n update Update','current'),('Commands:\n exec Run','unsupported')]:
            with self.subTest(status=status),patch('server.provider_updates.executable',side_effect=self.installed),patch('server.provider_updates.run',side_effect=lambda cmd,*a,**k: help_text if '--help' in cmd else '0.164.0'):
                self.u.start(force=True);self.wait();self.assertEqual(self.u.status()['providers']['codex']['status'],status)
        self.assertFalse(self.closed)
    def test_failure_is_sanitized_bounded_and_not_replayed(self):
        with patch('server.provider_updates.executable',side_effect=self.installed),patch('server.provider_updates.run',side_effect=OSError('SECRET_TOKEN')) as run:
            self.u.configure(True);self.wait();self.u.tick();self.assertEqual(run.call_count,1)
        self.assertNotIn('SECRET',json.dumps(self.u.status()));self.assertFalse(self.closed)
    def test_override_and_pending_login_never_run_updaters(self):
        self.bridges['claude']._login={'status':'working'}
        with patch.dict(os.environ,{'SUPERSURFER_CODEX':'/pinned/codex'}),patch('server.provider_updates.executable',side_effect=BridgeError('missing')),patch('server.provider_updates.run') as run:
            self.u.start(force=True);self.wait();run.assert_not_called()
        self.assertEqual(self.u.status()['providers']['codex']['status'],'managed_externally');self.assertEqual(self.u.status()['providers']['claude']['status'],'deferred')
    def test_readonly_rejects_configuration_and_checks_without_writes(self):
        self.s.read_only=True
        for f in (lambda:self.u.configure(True),self.u.start):
            with self.assertRaises(BridgeError):f()
        self.assertFalse(self.s.store.data)
    def test_deferred_retry_does_not_reupdate_recent_completed_tools(self):
        self.u.data['providers']['codex']={'status':'current','observed_at':time.time()}
        with patch('server.provider_updates.executable',side_effect=BridgeError('missing')),patch('server.provider_updates.run') as run:
            self.u._check();run.assert_not_called()
        self.assertEqual(self.u.status()['providers']['codex']['status'],'current')
    def test_managed_registry_bad_checksum_does_not_switch_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);root=home/'.local/lib/antigravity-acp';old=root/'1.4.5/agy_acp_server.par';old.parent.mkdir(parents=True);old.write_text('old');link=home/'.local/bin/agy_acp_server.par';link.parent.mkdir(parents=True);link.symlink_to(old)
            def download(url,path,limit):
                if path.name=='agent.json':path.write_text(json.dumps({'id':'antigravity-acp','version':'1.5.0','distribution':{'binary':{'darwin-aarch64':{'cmd':'./agy_acp_server.par','sha256':'0'*64,'archive':'https://dl.google.com/runtime.zip'}}}}))
                else:path.write_bytes(b'invalid archive')
            with patch('server.provider_updates.Path.home',return_value=home),patch('server.provider_updates.platform.system',return_value='Darwin'),patch('server.provider_updates.platform.machine',return_value='arm64'),patch('server.provider_updates.download',side_effect=download):
                with self.assertRaisesRegex(ValueError,'checksum'):antigravity_update(str(old),home)
            self.assertEqual(link.resolve(),old.resolve());self.assertFalse((root/'1.5.0').exists())

    def test_registry_pair_verified_before_atomic_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp).resolve();root=home/'.local/lib/antigravity-acp';old=root/'1.4.5/agy_acp_server.par';old.parent.mkdir(parents=True);old.write_text('old');link=home/'.local/bin/agy_acp_server.par';link.parent.mkdir(parents=True);link.symlink_to(old)
            bundle=home/'source.zip'
            with zipfile.ZipFile(bundle,'w') as archive:
                archive.writestr('agy_acp_server.par','new');archive.writestr('localharness_external','matching helper');archive.writestr('../unrelated','not extracted')
            digest=hashlib.sha256(bundle.read_bytes()).hexdigest()
            def download(url,path,limit):
                if path.name=='agent.json':path.write_text(json.dumps({'id':'antigravity-acp','version':'1.5.0','distribution':{'binary':{'darwin-aarch64':{'cmd':'./agy_acp_server.par','sha256':digest,'archive':'https://dl.google.com/runtime.zip'}}}}))
                else:path.write_bytes(bundle.read_bytes())
            connection=SimpleNamespace(call=lambda method,params,timeout:{'agentInfo':{'name':'antigravity-acp','version':'1.5.0'},'authMethods':[{'id':'oauth-personal'}],'agentCapabilities':{'auth':{'logout':{}}}},close=lambda:None)
            with patch('server.provider_updates.Path.home',return_value=home),patch('server.provider_updates.platform.system',return_value='Darwin'),patch('server.provider_updates.platform.machine',return_value='arm64'),patch('server.provider_updates.download',side_effect=download),patch('server.cli_backends.ProtocolProcess',return_value=connection):
                self.assertEqual(antigravity_update(str(old),home),('1.4.5','1.5.0'))
            self.assertEqual(link.resolve(),root/'1.5.0/agy_acp_server.par');self.assertEqual(old.read_text(),'old');self.assertEqual(link.resolve().with_name('localharness_external').read_text(),'matching helper');self.assertFalse((home.parent/'unrelated').exists())

    def test_each_native_tool_uses_its_advertised_command(self):
        for backend,verb,help_text in [('codex','update',' update Update'),('claude','update',' update|upgrade Update'),('cursor','update',' update Update'),('opencode','upgrade',' opencode upgrade [target] Upgrade')]:
            with self.subTest(backend=backend):
                self.u.data['providers']={}
                def installed(p):
                    if p!=backend:raise BridgeError('missing')
                    return '/official/bin/'+p
                with patch('server.provider_updates.executable',side_effect=installed),patch('server.provider_updates.run',side_effect=lambda cmd,*a,**k:help_text if '--help' in cmd else '1.2.3') as run:
                    self.u.start(force=True);self.wait()
                self.assertIn(['/official/bin/'+backend,verb],[c.args[0] for c in run.call_args_list]);self.assertEqual(self.u.status()['providers'][backend]['status'],'current')
