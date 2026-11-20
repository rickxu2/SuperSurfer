# Native Antigravity logout interface (November 19, 2026)

Reviewed: no credentials, identity or conversation content.

Binary SHA256: `fb2581fb49738263db15ffccf3f48d979794ffb748350e85c335953f6b6522a2`.
Bundled server.py SHA256: `9f1c1b8dc8b452cdd12bd15ff10d5da7226d55c05f0478047baf226e03bb95bb`.

Initialize-only live probe, empty temporary cwd and client capabilities, denying
all client actions. No authenticate, session, prompt or logout was sent.

```json
{
  "agentInfo": {
    "name": "antigravity-acp",
    "title": "Google Antigravity",
    "version": "1.4.5"
  },
  "auth": {
    "logout": {}
  }
}
```

Bundled software-source excerpts establish native ownership and cleanup:

```python
3280:   async def logout(self, **kwargs: Any) -> schema.LogoutResponse:
3281:     """Signs the connection out, per ACP's `logout` method.
3282: 
3283:     Same effect as the `/logout` command: credentials are removed, the
3284:     connection reverts to unauthenticated, and active sessions are torn down.
3285: 
3286:     Args:
3287:       **kwargs: Ignored; `LogoutRequest` has no fields beyond `_meta`.
3288: 
3289:     Returns:
3290:       An empty schema.LogoutResponse.
3291:     """
3292:     del kwargs  # LogoutRequest has no parameters.
3293:     await self._sign_out_and_forget()
3294:     return schema.LogoutResponse()
3295: 
3296:   def _active_auth_method(self) -> str | None:
3297:     """The method in use, or the one that would be, before any logout runs."""
3298:     auth_state = self._auth_state or _infer_auth_state()
3299:     return auth_state.method_id if auth_state is not None else None
3300: 
3301:   async def _sign_out_and_forget(self) -> bool:
3302:     """Signs out and clears the saved auth method.
3303: 
3304:     Used only where the user asked to be signed out: the ACP `logout` method
3305:     and the `/logout` command.
3306: 
3307:     Returns:
3308:       True if the connection was signed out, as `_clear_all_credentials`
3309:       reports it.
3310:     """
3311:     # Captured first: `_clear_all_credentials` may reset the auth state.
3312:     method_id = self._active_auth_method()
3313:     signed_out = await self._clear_all_credentials()
3314:     # The gateway never writes `auth.type`, so clearing it here would only wipe
3315:     # some other method's saved preference. Leave it alone.

3301:   async def _sign_out_and_forget(self) -> bool:
3302:     """Signs out and clears the saved auth method.
3303: 
3304:     Used only where the user asked to be signed out: the ACP `logout` method
3305:     and the `/logout` command.
3306: 
3307:     Returns:
3308:       True if the connection was signed out, as `_clear_all_credentials`
3309:       reports it.
3310:     """
3311:     # Captured first: `_clear_all_credentials` may reset the auth state.
3312:     method_id = self._active_auth_method()
3313:     signed_out = await self._clear_all_credentials()
3314:     # The gateway never writes `auth.type`, so clearing it here would only wipe
3315:     # some other method's saved preference. Leave it alone.
3316:     if method_id == AUTH_METHOD_GATEWAY:
3317:       logging.info(
3318:           "Logout is a no-op for %r: no stored credential to remove, and its"
3319:           " selection was never written to settings.json.",
3320:           AUTH_METHOD_GATEWAY,
3321:       )
3322:     else:
3323:       await asyncio.to_thread(settings_writer.clear_auth_type)
3324:     return signed_out
3325: 
3326:   async def _clear_all_credentials(self) -> bool:
3327:     """Clears the stored credentials for the connection's auth method.
3328: 
3329:     Logout signs the user out of what they are signed in as: only the flavor in
3330:     use has its credentials removed, so signing out of Gemini Enterprise does
3331:     not also drop a personal-OAuth token that a different connection may be
3332:     relying on. When no method is active or inferable there is nothing to
3333:     disrupt, so both are cleared. Removal runs in a worker thread because
3334:     `clear_credentials` blocks on the manager's lock, which a concurrent sign-in
3335:     or refresh may hold.
3336: 

3326:   async def _clear_all_credentials(self) -> bool:
3327:     """Clears the stored credentials for the connection's auth method.
3328: 
3329:     Logout signs the user out of what they are signed in as: only the flavor in
3330:     use has its credentials removed, so signing out of Gemini Enterprise does
3331:     not also drop a personal-OAuth token that a different connection may be
3332:     relying on. When no method is active or inferable there is nothing to
3333:     disrupt, so both are cleared. Removal runs in a worker thread because
3334:     `clear_credentials` blocks on the manager's lock, which a concurrent sign-in
3335:     or refresh may hold.
3336: 
3337:     The connection is only signed out when its auth method is backed by those
3338:     credentials; an API-key or Agent Platform connection keeps working. Signing
3339:     out also tears down active sessions, whose SDK agents and loopback proxies
3340:     were built with the credentials just removed.
3341: 
3342:     Returns:
3343:       True if the connection was signed out (auth state reset and sessions torn
3344:       down); False if only stored credentials were removed.
3345:     """
3346:     # Fall back to the method that *would* be used, so a logout before the first
3347:     # request still targets the right flavor.
3348:     auth_state = self._auth_state or _infer_auth_state()
3349:     method_id = auth_state.method_id if auth_state is not None else None
3350: 
3351:     to_clear = []
3352:     if method_id is None or method_id == AUTH_METHOD_OAUTH:
3353:       to_clear.append(self._ensure_oauth_mgr())
3354:     if method_id is None or method_id == AUTH_METHOD_OAUTH_BUSINESS:
3355:       to_clear.append(self._ensure_business_auth_mgr())
3356: 
3357:     def _clear() -> None:
3358:       for mgr in to_clear:
3359:         mgr.clear_credentials()
3360: 
3361:     await asyncio.to_thread(_clear)
```

Integration dispatches ACP `logout` with `{}` only on this advertised capability
and the retained explicit personal-OAuth connection. Native logout is not a model
prompt. Offline wire/routing fixtures test credential-removal dispatch, bounded
failure, guards and conversation retention; no live Google logout is used for QA.
