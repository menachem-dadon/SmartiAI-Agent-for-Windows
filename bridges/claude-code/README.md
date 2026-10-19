# Smarti Claude Code bridge

Pinned official Anthropic Agent SDK 0.3.303 (Claude Code 2.1.303 on Windows x64).
The SDK and its native executable are installed without modification. Their
original licenses and README remain in node_modules and are included by the
packaging recipes. Smarti uses the published protocol, never private endpoints.

From this folder run `npm ci --ignore-scripts --no-audit --no-fund`.
Normal `scripts/run_tauri_dev.ps1` and the Tauri Core build prepare this dependency.
A `-SkipInstall` launch expects the locked dependencies to have been prepared.
No API key or OAuth token is stored here. Do not commit node_modules or auth data.

Login is owned by the official binary and opens its own console/browser flow.
An optional user-configured CLAUDE_CODE_OAUTH_TOKEN is inherited only by this
transport; it is not accepted over the bridge protocol. Token setup uses the
user's official Claude Code terminal; it requires an eligible subscription.
The SDK-bundled binary can also be invoked directly at:
`node_modules/@anthropic-ai/claude-agent-sdk-win32-x64/claude.exe`.

Inference replaces the coding prompt with Smarti instructions, disables native
tools and customizations through official settings, and fails closed if init
advertises any tool except the internal StructuredOutput serializer. Smarti Core
validates and executes the returned Smarti tool requests under its own policy.
A frame is limited to 4 MiB and a response to 24 MiB. No raw SDK error is logged.

This adapter has isolated protocol coverage and official metadata validation.
Paid Claude login/inference, token expiration, and packaged runtime acceptance
remain pending. Antigravity 1.4.2 inference is deliberately blocked by Core after
SP-0 exposed native tools despite custom-agent restrictions; see the tracked plan.
