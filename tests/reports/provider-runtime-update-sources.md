# Provider runtime update sources (November 19, 2026)

Reviewed public vendor documentation and installed CLI help. No credentials,
account identity or native conversation content are included.

- Codex installed0.164.0 advertises `update` in `--help` and `codex update --help`.
  The official CLI source dispatches this command to the installation-aware
  updater: https://github.com/openai/codex/blob/main/codex-rs/cli/src/main.rs .
  SuperSurfer invokes the advertised updater, not a guessed npm installer.
- Claude's supported command is `claude update`, retaining vendor channel and
  managed-installation policy: https://code.claude.com/docs/en/setup .
- Cursor documents `agent update`: https://cursor.com/docs/cli/installation .
  SuperSurfer uses its detected official executable (agent/cursor-agent).
- OpenCode documents `opencode upgrade`: https://opencode.ai/docs/cli/commands/ .
- Antigravity standalone ACP distribution comes from the official registry:
  https://github.com/agentclientprotocol/registry/blob/main/antigravity-acp/agent.json .
  The managed runtime/helper pair is downloaded from dl.google.com, checksum
  verified, initialize-only identity checked, then selected by atomic symlink.
  Installing the unrelated npm package or swapping to the agy CLI is not used.

Observed registry1.5.0 Darwin arm64 archive SHA256:
`c82ecb4ef476bfc35cbe5b2745cdddef873b99c9f5bd7fd11e5ca1fc1667a3fc`.
Binary SHA256:
`bbb138a7ff32982e231af325e3176b252174f4c59e4fee7159c0e364ad5f9613`.
Bundled server.py SHA256:
`c4a5909af7ba15079309a67012014d071c608ac920ab229f3a2344f21383e4fb`.
Bundled usage.py SHA256:
`d4b0cabd4934af8b0fc23718c210d638627253069ae830fb45e46432092bf85d`.

Software-source inspection: `prompt` at5499 intercepts `is_usage_prompt` at5532,
returning `_handle_usage_command` before agent execution. Handler3385 reads native
usage/quota and returns without a model turn. usage.py is byte-identical to the
reviewed1.4.5 formatter/parser. Native logout remains supported at3193. No private
credential files or authenticated Google APIs were inspected. Future unreviewed
versions still show unavailable quota rather than sending an unproven prompt.

Model eligibility remains the provider's decision. Runtime updates refresh the
advertised catalog; no model IDs, entitlement or rollout access are fabricated.
