# Antigravity ACP 1.4.5 native usage evidence

Observed November 3, 2026 (America/New_York). Reviewed for publication: no
credentials, account identity, native session IDs or private transcript content.

## Native command proof

The installed Google registry archive was previously verified against its
published SHA-256 `886fff7767d08994ca39eb02c3d01a7532c7325a94aa33aaf52d52068733284f`.
The installed Darwin arm64 server binary SHA-256 is
`fb2581fb49738263db15ffccf3f48d979794ffb748350e85c335953f6b6522a2`.

The executable includes readable Python source in its embedded archive. Inspection
of `acp_server/server.py` found `prompt` at line 5580 dispatches exact `/usage`
at lines 5613–5614 to `_handle_usage_command` before the agent/model execution
path. The handler at line 3472 reads native session metadata and fetches quota
through the runtime-owned consumer/enterprise clients, formats a report, and
returns `end_turn`. SuperSurfer does not call these authenticated APIs itself.
`usage.py` defines the exact command parser and Markdown format. No credentials
or native credential stores were inspected.

Bundled source SHA-256:

- `server.py`: `9f1c1b8dc8b452cdd12bd15ff10d5da7226d55c05f0478047baf226e03bb95bb`
- `usage.py`: `d4b0cabd4934af8b0fc23718c210d638627253069ae830fb45e46432092bf85d`

## Bounded native wire observation

A temporary empty directory, no MCP servers, empty client capabilities and a
callback denying every client request were used. `initialize` reported
`antigravity-acp`, title `Google Antigravity`, version `1.4.5`. `session/new`
advertised the built-in `usage` command. Only after inspecting the interception
above, a single `session/prompt` containing exactly `/usage` was sent, bounded to
20 seconds for this investigation. The runtime returned `end_turn` with:

| Native group | Native remaining | Native reset text (UTC) |
| --- | --- | --- |
| Gemini Models | 100% | Nov 11, 2026, 02:31 UTC |
| Claude and GPT models | 100% | Nov 11, 2026, 02:31 UTC |

Session total was unavailable. No model turn, tool execution, explicit auth
request or existing conversation load was sent by the probe. Its process was
closed afterwards. These are a historical native observation, not current quota
or an end-to-end test of the subsequently installed SuperSurfer app.

## Integration boundary

Only the verified 1.4.5 identity plus the private session's advertised command
allows dispatch. Future versions require a new interception/format review.
Explicit Connect retains its existing no-project/no-MCP setup process. Polling
uses only that process, never calls authenticate or session/new, sends only exact
`/usage`, denies client execution, bounds the report and times out after 15 seconds.
Timeout/disconnect/unexpected execution discards the channel with no replay.
Cache lifetime is 60 seconds and reconnect clears it. No account email/token is
needed; observations belong to that native connection. External native sign-in
changes remain runtime-owned and should be followed by explicit reconnect.

Only Quota Limits are normalized. The native interface rounds percentages to
integers and reset timestamps to minutes; the UI states this precision and shows
source/observation time. Amount-only buckets stay units, never fake percentages.
Missing quota stays unavailable; context `used`/`size` and session totals do not
become remaining quota or host consumption.

## Sources and visual fixture

- [Google ACP changelog](https://antigravity.google/docs/changelog?tab=hub): ACP 1.4.0 added `/usage` for consumer/enterprise quotas.
- [Google usage command](https://antigravity.google/docs/cli/commands/usage): CLI quota behavior, not a separate authenticated API contract.
- [Google status line](https://antigravity.google/docs/cli/statusline): distinguishes context fields from quota fields; this integration does not modify status-line settings.

[UI screenshot](antigravity-usage.png) is an isolated Electron fixture with
synthetic 91%/0% values. It demonstrates layout and unavailable/token separation,
not a live account measurement. Chrome was not launched.
