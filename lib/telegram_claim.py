#!/usr/bin/env python3
"""Secure Telegram setup helper for the Hermes VPS installer.

The bot token is accepted only through TELEGRAM_BOT_TOKEN. It is never placed
in command-line arguments or included in normal/error output.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping


_TOKEN_RE = re.compile(r"^[0-9]{6,12}:[A-Za-z0-9_-]{30,}$")
_PAYLOAD_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


class TelegramError(RuntimeError):
    """A user-facing Telegram setup failure that never contains the bot token."""


def validate_token(token: str) -> str:
    token = (token or "").strip()
    if not _TOKEN_RE.fullmatch(token):
        raise TelegramError("Telegram bot token has an invalid format")
    return token


class TelegramClient:
    def __init__(
        self,
        token: str,
        *,
        api_base: str = "https://api.telegram.org",
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        self._token = validate_token(token)
        self._base = api_base.rstrip("/")
        self._opener = opener

    def request(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", method):
            raise TelegramError("Invalid Telegram API method")
        url = f"{self._base}/bot{self._token}/{method}"
        body = json.dumps(dict(params or {}), separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=35) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            description = ""
            try:
                error_payload = json.loads(exc.read().decode("utf-8"))
                description = str(error_payload.get("description") or "").strip()
            except Exception:
                description = ""
            suffix = f": {description}" if description else ""
            raise TelegramError(
                f"Telegram API {method} failed with HTTP {exc.code}{suffix}"
            ) from None
        except urllib.error.URLError as exc:
            reason = str(getattr(exc, "reason", "network error"))
            raise TelegramError(f"Telegram API {method} network error: {reason}") from None
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise TelegramError(f"Telegram API {method} returned an invalid response") from exc

        if not isinstance(payload, dict) or payload.get("ok") is not True:
            description = ""
            if isinstance(payload, dict):
                description = str(payload.get("description") or "").strip()
            suffix = f": {description}" if description else ""
            raise TelegramError(f"Telegram API {method} rejected the request{suffix}")
        return payload.get("result")

    def send_message(self, chat_id: str, text: str) -> Any:
        return self.request(
            "sendMessage",
            {"chat_id": str(chat_id), "text": str(text), "disable_web_page_preview": True},
        )


def prepare_bot(client: Any) -> dict[str, Any]:
    identity = client.request("getMe", {})
    if not isinstance(identity, dict) or identity.get("is_bot") is not True:
        raise TelegramError("Telegram getMe did not return a bot account")
    username = str(identity.get("username") or "").strip()
    bot_id = identity.get("id")
    if not username or bot_id is None:
        raise TelegramError("Telegram bot identity is missing id or username")

    webhook = client.request("getWebhookInfo", {})
    webhook_url = str((webhook or {}).get("url") or "").strip() if isinstance(webhook, dict) else ""
    if webhook_url:
        raise TelegramError(
            "This bot already has a webhook configured; use a fresh BotFather bot or remove the webhook explicitly"
        )
    return {"id": bot_id, "username": username}


def _clock_from_values(
    monotonic_values: Iterable[float] | None,
) -> Callable[[], float]:
    if monotonic_values is None:
        return time.monotonic
    iterator = iter(monotonic_values)
    return lambda: float(next(iterator))


def claim_owner(
    client: Any,
    payload: str,
    *,
    timeout_seconds: int = 600,
    monotonic_values: Iterable[float] | None = None,
) -> dict[str, str]:
    if not _PAYLOAD_RE.fullmatch(payload or ""):
        raise TelegramError("Telegram claim payload has an invalid format")
    if timeout_seconds < 1 or timeout_seconds > 3600:
        raise TelegramError("Telegram claim timeout must be between 1 and 3600 seconds")

    clock = _clock_from_values(monotonic_values)
    started = clock()

    stale = client.request(
        "getUpdates",
        {"offset": -1, "limit": 1, "timeout": 0, "allowed_updates": ["message"]},
    )
    offset = 0
    if isinstance(stale, list):
        for update in stale:
            if isinstance(update, dict) and isinstance(update.get("update_id"), int):
                offset = max(offset, int(update["update_id"]) + 1)

    expected_text = f"/start {payload}"
    while True:
        now = clock()
        elapsed = now - started
        if elapsed >= timeout_seconds:
            break
        remaining = max(1, int(timeout_seconds - elapsed))
        poll_timeout = min(20, remaining)
        updates = client.request(
            "getUpdates",
            {
                "offset": offset,
                "limit": 20,
                "timeout": poll_timeout,
                "allowed_updates": ["message"],
            },
        )
        if not isinstance(updates, list):
            continue
        for update in updates:
            if not isinstance(update, dict):
                continue
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                offset = max(offset, update_id + 1)
            message = update.get("message")
            if not isinstance(message, dict):
                continue
            sender = message.get("from")
            chat = message.get("chat")
            if not isinstance(sender, dict) or not isinstance(chat, dict):
                continue
            if sender.get("is_bot") is True or chat.get("type") != "private":
                continue
            sender_id = sender.get("id")
            chat_id = chat.get("id")
            if sender_id is None or chat_id is None or str(sender_id) != str(chat_id):
                continue
            text = str(message.get("text") or "")
            if not secrets.compare_digest(text, expected_text):
                continue
            return {
                "user_id": str(sender_id),
                "chat_id": str(chat_id),
                "username": str(sender.get("username") or ""),
                "first_name": str(sender.get("first_name") or ""),
            }

    raise TelegramError("Telegram owner claim timed out")


def upsert_env(path: str | Path, values: Mapping[str, str]) -> None:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(target.parent, 0o700)
    except OSError:
        pass

    clean_values: dict[str, str] = {}
    for key, value in values.items():
        key = str(key)
        value = str(value)
        if not _ENV_KEY_RE.fullmatch(key):
            raise ValueError(f"Invalid environment key: {key!r}")
        if "\n" in value or "\r" in value or "\x00" in value:
            raise ValueError(f"Environment value for {key} contains a forbidden character")
        clean_values[key] = value

    existing_lines: list[str] = []
    if target.exists():
        existing_lines = target.read_text(encoding="utf-8").splitlines()

    kept: list[str] = []
    for line in existing_lines:
        candidate = line.strip()
        if candidate and not candidate.startswith("#") and "=" in candidate:
            existing_key = candidate.split("=", 1)[0].strip()
            if existing_key in clean_values:
                continue
        kept.append(line)
    while kept and kept[-1] == "":
        kept.pop()
    if kept:
        kept.append("")
    kept.extend(f"{key}={value}" for key, value in clean_values.items())
    content = "\n".join(kept) + "\n"

    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        os.chmod(target, 0o600)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _client_from_env() -> TelegramClient:
    token = validate_token(os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    api_base = "https://api.telegram.org"
    if os.environ.get("HERMES_INSTALLER_TEST_MODE") == "1":
        api_base = os.environ.get("TELEGRAM_API_BASE", api_base)
    return TelegramClient(token, api_base=api_base)


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in {"prepare", "claim", "save-env", "notify"}:
        print("usage: telegram_claim.py {prepare|claim|save-env|notify}", file=sys.stderr)
        return 2

    action = args[0]
    try:
        if action == "save-env":
            token = validate_token(os.environ.get("TELEGRAM_BOT_TOKEN", ""))
            user_id = str(os.environ.get("TELEGRAM_ALLOWED_USERS", "")).strip()
            chat_id = str(os.environ.get("TELEGRAM_HOME_CHANNEL", "")).strip()
            if not user_id.isdigit() or not chat_id.lstrip("-").isdigit():
                raise TelegramError("Telegram owner identifiers are invalid")
            env_path = os.environ.get("HERMES_ENV_PATH", "~/.hermes/.env")
            upsert_env(
                env_path,
                {
                    "TELEGRAM_BOT_TOKEN": token,
                    "TELEGRAM_ALLOWED_USERS": user_id,
                    "TELEGRAM_HOME_CHANNEL": chat_id,
                },
            )
            _print_json({"saved": True, "path": str(Path(env_path).expanduser())})
            return 0

        client = _client_from_env()
        if action == "prepare":
            _print_json(prepare_bot(client))
            return 0
        if action == "claim":
            payload = str(os.environ.get("TELEGRAM_CLAIM_PAYLOAD", ""))
            timeout = int(os.environ.get("TELEGRAM_CLAIM_TIMEOUT", "600"))
            _print_json(claim_owner(client, payload, timeout_seconds=timeout))
            return 0

        chat_id = str(os.environ.get("TELEGRAM_HOME_CHANNEL", "")).strip()
        text = str(os.environ.get("TELEGRAM_NOTIFY_TEXT", "")).strip()
        if not chat_id or not text:
            raise TelegramError("Telegram notification chat or text is missing")
        client.send_message(chat_id, text)
        _print_json({"sent": True})
        return 0
    except (TelegramError, ValueError) as exc:
        print(f"Telegram setup error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
