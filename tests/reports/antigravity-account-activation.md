# Antigravity Settings account controls — local verification

Verified November 19, 2026. Reviewed for publication: no credentials, account
emails, session IDs or private conversation content.

- PR #7 adds native ACP Sign out, subsequent Sign in and explicit stale-channel
  Reconnect, stacked on unmerged quota PR6. Native capability/source proof is in
  `tests/reports/antigravity-native-logout.md`.
- Feature800/combined803 Python tests OK (34 skipped), Node50 passed/5 skipped;
  22 native-wire and 11 provider-routing tests passed. Isolated source and
  delivered Electron tests cover Sign out → Sign in, shared-login notice,
  active-turn disabled state and explicit reconnect without a real Google logout.
- Combined local build67a18d0 retains installed native quota and paused-status
  fixe6a6145. Darwin arm64 packaging, original/ZIP-extracted strict signatures,
  isolated launches and renderer sandbox checks passed. Local/ad-hoc signing;
  no notarization/downloaded Gatekeeper claim.
- Installed desktop PID7652 runs `/Applications/SuperSurfer.app` with the original
  profile; matching service PID7650 runs release `c19694c530d28ff8`. Exact server/
  UI source matches the validated package. Original window and histories restored.
  Research engine PID54249 unchanged. Consistent database/preferences and prior
  app backups retained. One-shot helper exited after dispatching this same worker.
- Visible native Settings first showed Sign in after the service restart. Clicking
  it completed the existing cached Google Connect flow. Settings then displayed
  enabled Sign out plus the notice that other Antigravity clients sharing this
  login may be signed out. Live API confirms `logout_supported: true`, completed
  login and no reconnect required; native quota remains available in the sidebar.
- The real Sign out button was not clicked for QA. No Chrome, credential scraping,
  model inference, merge or public release. Surfboard checks remain unconfigured;
  no managed-check or preview success is claimed.

Workspace archive SHA256:
`c19694c530d28ff894ac52e0cb9ca58f228074897ccea65b75aa43ff6ff7a5f7`.

Activation recovered from an old one-shot marker before any service/app mutation.
A unique marker was used for this update. The editor's accessibility label also
falsely identified a clean tab as unsaved; visual/native Quit checks confirmed no
dirty marker or discard prompt. No draft was discarded.
