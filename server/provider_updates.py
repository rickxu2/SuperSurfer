"""Opt-in, idle-only maintenance of installed provider runtimes.

Never authenticates, runs a model prompt or installs a missing provider. Native
updaters own their installation policy; pinned/custom paths remain user-managed.
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import urllib.request
from urllib.parse import urlparse
import zipfile

from .cli_backends import PROVIDERS, executable, provider_name
from .conversations import BridgeError

REGISTRY = 'https://raw.githubusercontent.com/agentclientprotocol/registry/refs/heads/main/antigravity-acp/agent.json'
INTERVAL = 6 * 3600
VERSION = re.compile(r'\b\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?\b')


def run(command, cwd, timeout=120, output=False):
    # No inherited project cwd, shell, stdin, agent/tool environment or raw logs.
    env = {k: v for k, v in os.environ.items() if not k.startswith('SUPERSURFER_AGENT_') and k != 'CLAUDECODE'}
    env['PATH'] = os.pathsep.join(p for p in env.get('PATH', '').split(os.pathsep) if Path(p).is_absolute())
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=log if output else subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
            raise BridgeError('Provider updater timed out. Its outcome is uncertain; check the installed version before retrying.')
        if proc.returncode:
            raise BridgeError('The official updater did not complete. Its install policy, permissions or network may require attention; no fallback command was run.')
        log.seek(0)
        return log.read(1024 * 1024).decode('utf-8', errors='replace') if output else ''


def download(url, destination, limit):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in {'raw.githubusercontent.com', 'dl.google.com'}:
        raise ValueError('Unsupported official download source')
    with urllib.request.urlopen(url, timeout=30) as response, destination.open('wb') as target:
        if urlparse(response.url).hostname != parsed.hostname or urlparse(response.url).scheme != 'https':
            raise ValueError('Unexpected download redirect')
        size = 0
        deadline = time.monotonic() + 180
        while chunk := response.read(1024 * 1024):
            if time.monotonic() > deadline:
                raise ValueError('Official download exceeded its time bound')
            size += len(chunk)
            if size > limit:
                raise ValueError('Official download exceeds the supported bound')
            target.write(chunk)


def antigravity_update(binary, temporary):
    """Checksum verified official ACP pair, then atomic managed launcher switch."""
    home = Path.home()
    managed = home / '.local/lib/antigravity-acp'
    launcher = home / '.local/bin/agy_acp_server.par'
    current = Path(binary).resolve()
    if not current.is_relative_to(managed.resolve()) or not launcher.is_symlink() or launcher.resolve() != current:
        raise BridgeError('Antigravity has a custom installation. Update it through its owner; no launcher was changed.')
    meta = temporary / 'agent.json'
    download(REGISTRY, meta, 65536)
    registry = json.loads(meta.read_text())
    version = registry.get('version', '')
    if registry.get('id') != 'antigravity-acp' or not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid official registry version')
    os_name = {'Darwin': 'darwin', 'Linux': 'linux'}.get(platform.system())
    arch = {'arm64': 'aarch64', 'aarch64': 'aarch64', 'x86_64': 'x86_64', 'AMD64': 'x86_64'}.get(platform.machine())
    entry = registry.get('distribution', {}).get('binary', {}).get(f'{os_name}-{arch}')
    if not entry or entry.get('cmd') != './agy_acp_server.par':
        raise BridgeError('No supported official Antigravity ACP build for this host.')
    before = current.parent.name
    # Do not downgrade a user-selected newer runtime.
    if re.fullmatch(r'\d+\.\d+\.\d+', before) and tuple(map(int, version.split('.'))) <= tuple(map(int, before.split('.'))):
        return before, before
    digest = entry.get('sha256', '')
    if not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('Missing official archive checksum')
    archive = temporary / 'runtime.zip'
    download(entry['archive'], archive, 400 * 1024 * 1024)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise ValueError('Official archive checksum mismatch')
    destination = managed / version
    if destination.exists():
        raise BridgeError('An existing Antigravity version directory needs inspection; it was not overwritten.')
    with tempfile.TemporaryDirectory(prefix='.update-', dir=managed) as staging:
        stage = Path(staging)
        with zipfile.ZipFile(archive) as bundle:
            # Extract only the fixed server/helper pair; reject links, traversal,
            # duplicates and oversized members before writing executable files.
            names = ['agy_acp_server.par', 'localharness_external']
            if any(bundle.namelist().count(name) != 1 for name in names):
                raise ValueError('Official archive is missing its matching runtime/helper pair')
            for name in names:
                info = bundle.getinfo(name)
                if info.file_size > 800 * 1024 * 1024 or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Unsupported archive member')
                with bundle.open(info) as source, (stage / name).open('wb') as target:
                    shutil.copyfileobj(source, target)
                (stage / name).chmod(0o755)
        # Validate native identity and logout before activating; no auth/session.
        from .antigravity import AntigravityBridge
        from .cli_backends import ProtocolProcess
        def deny(value, connection):
            if 'method' in value and 'id' in value:
                connection.respond(value['id'], 'Runtime validation does not authorize client actions.', error=True)
        args, env = AntigravityBridge.runtime_command(str(stage / names[0]), os.environ)
        connection = ProtocolProcess(args, str(temporary), env, deny)
        try:
            init = connection.call('initialize', {'protocolVersion': 1, 'clientCapabilities': {},
                'clientInfo': {'name': 'supersurfer-runtime-check', 'version': '1'}}, timeout=20)
            if (init.get('agentInfo', {}).get('name') != 'antigravity-acp'
                    or init['agentInfo'].get('version') != version
                    or not any(a.get('id') == 'oauth-personal' for a in init.get('authMethods', []))
                    or not isinstance(init.get('agentCapabilities', {}).get('auth', {}).get('logout'), dict)):
                raise ValueError('Downloaded runtime identity mismatch')
        finally:
            connection.close()
        if launcher.resolve() != current:
            raise BridgeError('Antigravity launcher changed during download; no activation performed.')
        os.rename(stage, destination)
        # TemporaryDirectory cleanup tolerates a directory moved into the final location.
    next_link = launcher.with_name('.agy-acp-update-' + str(os.getpid()))
    try:
        next_link.symlink_to(destination / 'agy_acp_server.par')
        if launcher.resolve() != current:
            raise BridgeError('Antigravity launcher changed before activation.')
        os.replace(next_link, launcher)
    finally:
        next_link.unlink(missing_ok=True)
    return before, version


class ProviderUpdates:
    def __init__(self, service):
        self.service = service
        self.lock = threading.RLock()
        self.thread = None
        self.closed = False
        self.data = service.store.get('provider_updates', {'enabled': False, 'next_check': None, 'providers': {}})
        for row in self.data.get('providers', {}).values():
            if row.get('status') == 'working':
                row.update(status='unconfirmed', note='Previous update was interrupted. Check the installed version; no immediate retry was made.')
        self.data['working'] = False

    def status(self):
        with self.lock:
            return copy.deepcopy(self.data)

    def _save(self):
        if not self.closed:
            self.service.store.put('provider_updates', self.data)

    def configure(self, enabled):
        if self.closed or self.service.read_only:
            raise BridgeError('Runtime updates cannot be configured in a read-only or closing workspace.', 403)
        if not isinstance(enabled, bool):
            raise ValueError('enabled must be boolean')
        with self.lock:
            self.data['enabled'] = enabled
            if enabled and not self.data.get('next_check'):
                self.data['next_check'] = time.time()
            self._save()
        self.tick()
        return self.status()

    def tick(self):
        with self.lock:
            if self.data.get('enabled') and (self.data.get('next_check') or 0) <= time.time():
                self.start()

    def start(self, force=False):
        with self.lock:
            if self.closed or self.service.read_only:
                raise BridgeError('Runtime updates are unavailable in a read-only or closing workspace.', 403)
            if self.thread and self.thread.is_alive():
                return self.status()
            self.data.update(working=True, last_check=time.time(), next_check=time.time() + INTERVAL)
            self._save()
            self.thread = threading.Thread(target=self._check, args=(force,), name='supersurfer-provider-updates', daemon=True)
            self.thread.start()
            return self.status()

    def _check(self, force=False):
        router = self.service.codex
        try:
            for backend in PROVIDERS:
                if self.closed or self.service.read_only:
                    break
                previous = self.data['providers'].get(backend, {})
                if not force and previous.get('status') != 'deferred' and previous.get('observed_at', 0) + INTERVAL > time.time():
                    continue
                lock = router.account_locks[backend]
                if not lock.acquire(blocking=False):
                    self._record(backend, status='deferred', note='Provider is busy; retry after its active turns finish.')
                    continue
                try:
                    bridge = router._require_account_idle(backend)
                    if getattr(bridge, '_login', {}).get('status') == 'working':
                        raise BridgeError('Provider sign-in is still working.', 409)
                    if os.environ.get('SUPERSURFER_' + backend.upper()) or backend == 'antigravity' and os.environ.get('ANTIGRAVITY_HARNESS_PATH'):
                        self._record(backend, status='managed_externally', note='Explicit runtime override is pinned; update it through its owner.')
                        continue
                    try:
                        binary = executable(backend)
                    except BridgeError:
                        self._record(backend, status='not_installed', note='Not installed; automatic updates never install missing providers.')
                        continue
                    self._record(backend, status='working', note='Checking the official updater…')
                    with tempfile.TemporaryDirectory(prefix='provider-update-') as folder:
                        cwd = Path(folder)
                        if backend == 'antigravity':
                            before, after = antigravity_update(binary, cwd)
                        else:
                            before = self._version(binary, cwd)
                            verb = 'upgrade' if backend == 'opencode' else 'update'
                            help_text = run([binary, '--help'], cwd, timeout=15, output=True)
                            help_text = re.sub(r'\x1b\[[0-9;]*m', '', help_text)
                            prefix = r'(?:opencode\s+)?' if backend == 'opencode' else ''
                            if not re.search(r'(?m)^\s*' + prefix + verb + r'(?:\||\s|\[)', help_text):
                                self._record(backend, status='unsupported', version=before, note='This CLI does not advertise its official updater. Update through its installation owner.')
                                continue
                            run([binary, verb], cwd)
                            after = self._version(executable(backend), cwd)
                        if self.closed:
                            break
                        changed = before != after
                        if changed:
                            # The idle provider lock also excludes sends/login/logout.
                            # Reopen its private process lazily; native auth remains native.
                            bridge.close()
                            with router.lock:
                                router.bridges.pop(backend, None)
                            self.service._model_defaults_cache.clear()
                            if backend == 'codex':
                                with self.service.model_lock:
                                    self.service._models_cache = None
                                    self.service._models_checked_at = 0
                                    self.service._models_error = None
                        self._record(backend, status='updated' if changed else 'current', version=after,
                                     previous_version=before, note='Runtime updated. Refresh models; reconnect Google if requested.' if changed else 'Official updater completed; installed version is unchanged.')
                except BridgeError as error:
                    self._record(backend, status='deferred' if error.status == 409 else 'failed', note=str(error))
                except Exception:
                    self._record(backend, status='failed', note='Runtime update could not be verified. Existing credentials and conversations were not changed; no fallback was run.')
                finally:
                    lock.release()
        finally:
            with self.lock:
                self.data['working'] = False
                # Busy providers retry on the next idle minute; completed providers
                # are skipped until their own six-hour deadline.
                if any(r.get('status') == 'deferred' for r in self.data['providers'].values()):
                    self.data['next_check'] = time.time() + 60
                self._save()

    def _version(self, binary, cwd):
        value = VERSION.search(run([binary, '--version'], cwd, timeout=15, output=True))
        if not value:
            raise BridgeError('Installed CLI did not return a recognized version; no update was started.')
        return value.group()

    def _record(self, backend, **fields):
        with self.lock:
            self.data['providers'][backend] = {**self.data['providers'].get(backend, {}), **fields, 'observed_at': time.time()}
            self._save()

    def close(self):
        with self.lock:
            self.closed = True
        if self.thread:
            self.thread.join(timeout=2)
