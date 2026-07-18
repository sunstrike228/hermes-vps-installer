# Verification report — v1.0.0

Date: 2026-07-18

This document records executed checks. It deliberately distinguishes verified behavior from behavior that still requires a real first-time user run.

## Verified

### Local quality gates

Executed from the release worktree:

```bash
bash -n install.sh
shellcheck install.sh tests/*.sh
python3 -m compileall -q lib tests
python3 -m unittest discover -s tests -v
bash tests/test_static.sh
bash tests/run_isolated.sh
```

Result:

```text
Ran 11 tests in 1.1s
OK
static installer checks: PASS
isolated installer verification: PASS
```

Coverage includes:

- realistic and malformed Telegram token validation;
- refusal to remove or replace an existing Telegram webhook;
- rejection of stale, wrong, group and sender/chat-mismatched owner claims;
- acceptance of only the exact random `/start <payload>` in a private chat;
- atomic `.env` update, duplicate removal and mode `0600`;
- helper CLI against a local HTTP Telegram Bot API mock;
- full installer orchestration from script content on stdin (the `curl | bash` execution shape) with mocked official installer, Hermes CLI and systemctl;
- absence of the test token from captured stdout, stderr and command logs;
- exact provider/model/reasoning/auto-effort and systemd install commands;
- static rejection of allow-all, YOLO and token-as-command-argument patterns.

### Clean Ubuntu 24.04 installation path

Executed the pinned official Hermes installer inside a fresh `ubuntu:24.04` container with only the declared dependencies installed.

Result:

```text
Hermes Agent v0.18.2 (2026.7.7.2)
UBUNTU24_FULL_OFFICIAL_INSTALL_OK
UBUNTU24_INSTALL_CONFIG_OK
```

Both the exact production upstream invocation (including the default browser/dependency stage) and the persisted configuration were exercised. The following values were loaded back from `/root/.hermes/config.yaml` using the installed Hermes virtual environment:

```text
model.provider = openai-codex
model.default = gpt-5.6-terra
agent.reasoning_effort = medium
agent.reasoning_effort_auto.enabled = true
```

This test found and led to fixes for two clean-install defects before release:

1. the immutable upstream installer lives at `scripts/install.sh`, not the repository root;
2. minimal Ubuntu requires the declared `xz-utils` dependency.

### Live Codex model availability

Executed against an existing valid OpenAI Codex OAuth credential:

```bash
hermes chat -q 'Reply with exactly: TERRATEST_OK' \
  -m gpt-5.6-terra --provider openai-codex -t safe -Q
```

Result:

```text
TERRATEST_OK
```

No fallback model was used.

### Live Telegram API compatibility

The release helper executed `getMe` and `getWebhookInfo` successfully against an existing bot token. Bot identity is intentionally redacted from this public report. The token was loaded internally and was not included in command arguments or output.

## Not yet independently verified

These checks require a fresh BotFather bot, a human Codex device authorization and a real systemd VPS run. They are intentionally not simulated or claimed as complete:

- first-time device-code login by an external user;
- first-time deep-link claim using a fresh Telegram bot;
- installation of the final public tagged asset from GitHub;
- live creation, boot enablement and Telegram reply of `hermes-gateway.service` on the external tester's VPS;
- a second real installer run on that VPS to confirm end-to-end idempotency.

The installer's mock flow does exercise the exact auth/config/gateway commands and service verification branches, but that is not described as a substitute for the external VPS test.

## Security boundary

Version `v1.0.0` intentionally runs Hermes as root because that was the explicit requirement for the guide. This gives Hermes terminal tools full control of the VPS. Use a dedicated VPS and do not store unrelated secrets on it.

The Telegram Bot Token must be pasted only into the installer's hidden prompt. Never put it in the one-line command, a GitHub issue, a screenshot or chat message.
