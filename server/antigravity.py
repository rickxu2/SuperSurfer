"""Google's official Antigravity ACP runtime, not an agy CLI wrapper.

Only an explicit Connect action starts OAuth. Credentials stay in Google's
runtime/keychain; polling never reads tokens or silently opens a browser.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import sys
import threading

from .cli_backends import CliBridge, ProtocolProcess, executable
from .conversations import BridgeError


class AntigravityBridge(CliBridge):
    def __init__(self, *args, **kwargs):
        self._authenticated = False
        self._login = {"status": "idle"}
        self._login_connection = None
        self._login_worker = None
        self._catalog = []
        super().__init__(*args, **kwargs)

    @staticmethod
    def runtime_command(binary, env):
        env = {k: v for k, v in env.items() if not k.startswith("SUPERSURFER_AGENT_")}
        helper = Path(binary).with_name("localharness_external.exe" if sys.platform == "win32" else "localharness_external")
        if "ANTIGRAVITY_HARNESS_PATH" not in env and helper.is_file():
            env["ANTIGRAVITY_HARNESS_PATH"] = str(helper)
        # Matches Google's ACP registry, including the Linux launcher argument.
        return [binary, *(["--uid="] if sys.platform.startswith("linux") else [])], env

    @staticmethod
    def authenticate(connection, init):
        if not any(item.get("id") == "oauth-personal" for item in init.get("authMethods", [])):
            raise BridgeError("This Antigravity runtime does not support Google personal-account sign-in. Install the official ACP runtime.")
        # Never fall back to an API key or enterprise billing. The native runtime
        # reuses its own cached Google sign-in and owns any refresh/consent flow.
        return connection.call("authenticate", {"methodId": "oauth-personal"}, timeout=300)

    def _read_account(self):
        try:
            executable(self.backend)
        except BridgeError as exc:
            return {"backend": self.backend, "installed": False, "account": None,
                    "login_required": True, "logout_supported": False,
                    "error": str(exc) + " Antigravity needs agy_acp_server.par and its matching localharness_external helper, not just agy."}
        return {"backend": self.backend, "installed": True,
                "account": {"type": self.backend, "authMethod": "oauth-personal"} if self._authenticated else None,
                "login_required": not self._authenticated, "logout_supported": False,
                "login": copy.deepcopy(self._login), "error": self._login.get("error"),
                "note": ("Google account connected. Model access follows your Antigravity plan."
                         if self._authenticated else
                         "Connect to verify Google's cached sign-in, or finish sign-in in the workspace host's browser. Reconnect after a workspace service restart.")}

    def login(self):
        binary = executable(self.backend)
        with self._account_lock:
            if self._closed:
                raise BridgeError("The workspace is closing; reconnect before signing in.")
            if not self._login_worker or not self._login_worker.is_alive():
                self._login = {"status": "working"}
                self._account_cache = None
                self._login_worker = threading.Thread(target=self._connect, args=(binary,), daemon=True,
                                                      name="supersurfer-antigravity-login")
                self._login_worker.start()
        return {"backend": self.backend, "type": "provider", "note": "Complete Google sign-in in the workspace host's browser. Cached sign-in may complete automatically."}

    def _connect(self, binary):
        connection = None
        try:
            args, env = self.runtime_command(binary, os.environ)
            # This private setup session has no project context, MCP tools or
            # model prompts. It reads the runtime's advertised model selectors.
            def event(value, source):
                if "method" in value and "id" in value:
                    source.respond(value["id"], "Setup does not authorize tool execution.", error=True)
            connection = ProtocolProcess(args, str(self.state_dir), env, event)
            with self._account_lock:
                if self._closed:
                    return
                self._login_connection = connection
            init = connection.call("initialize", {"protocolVersion": 1, "clientCapabilities": {},
                                                   "clientInfo": {"name": "supersurfer", "version": "1"}})
            self.authenticate(connection, init)
            session = connection.call("session/new", {"cwd": str(self.state_dir), "mcpServers": []})
            catalog = self.session_models(session)
            with self._account_lock:
                if not self._closed:
                    self._authenticated = True
                    self._catalog = catalog
                    self._login = {"status": "completed"}
        except Exception:
            with self._account_lock:
                self._authenticated = False
                self._login = {"status": "failed", "error": "Antigravity sign-in could not be verified. Check its official ACP installation and finish Google sign-in on the workspace host, then reconnect. No model prompt was sent."}
        finally:
            if connection:
                connection.close()
            with self._account_lock:
                self._login_connection = None
                self._account_cache = None

    @staticmethod
    def session_models(session):
        options = next((item for item in session.get("configOptions", []) if item.get("category") == "model" or item.get("id") == "model"), {})
        values = options.get("options", [])
        # ACP select options may be grouped.
        values = [choice for item in values for choice in (item.get("options", []) if "options" in item else [item])]
        return [{"id": item["value"], "model": item["value"],
                 "displayName": str(item.get("name") or item["value"])[:200], "isDefault": False,
                 "supportedReasoningEfforts": [], "defaultReasoningEffort": None}
                for item in values if isinstance(item.get("value"), str) and 0 < len(item["value"]) <= 200]

    def models(self):
        with self._account_lock:
            return {"backend": self.backend, "models": [{"id": "auto", "model": "auto", "displayName": "Antigravity default",
                    "isDefault": True, "supportedReasoningEfforts": [], "defaultReasoningEffort": None}, *copy.deepcopy(self._catalog)]}

    def model_defaults(self, cwd=None):
        return {"model": "auto", "reasoning": None}

    def configure_session(self, connection, session_id, session, model):
        choices = session.get("configOptions", [])
        mode = next((item for item in choices if item.get("id") == "mode" or item.get("category") == "mode"), None)
        if not mode or not any(item.get("value") == "default" for item in mode.get("options", [])):
            raise BridgeError("Antigravity cannot confirm its default permission mode. Update the official ACP runtime; no prompt was sent.")
        # Keep native permissions at default even in YOLO. Only our exact-turn
        # allow-once callback auto-approves; no shared allow-always cache is set.
        connection.call("session/set_config_option", {"sessionId": session_id, "configId": mode["id"], "value": "default"})
        catalog = self.session_models(session)
        with self._account_lock:
            self._catalog = catalog
        if model and model != "auto":
            if model not in {item["id"] for item in catalog}:
                raise BridgeError("The selected Antigravity model is unavailable; choose an advertised model. No fallback prompt was sent.", 400)
            selector = next(item for item in choices if item.get("category") == "model" or item.get("id") == "model")
            connection.call("session/set_config_option", {"sessionId": session_id, "configId": selector["id"], "value": model})

    def logout(self):
        raise BridgeError("Antigravity credentials belong to its native ACP runtime. Sign out in a supported Antigravity ACP client; SuperSurfer does not delete shared Google credentials.", 409)

    def close(self):
        with self._account_lock:
            self._closed = True
            connection = self._login_connection
        if connection:
            connection.close()
        if self._login_worker:
            self._login_worker.join(timeout=5)
        super().close()
