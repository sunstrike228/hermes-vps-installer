import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib.telegram_claim import (
    TelegramError,
    _client_from_env,
    claim_owner,
    prepare_bot,
    upsert_env,
    validate_token,
)


VALID_TOKEN = "1234567890:" + ("A" * 35)


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, params=None):
        self.calls.append((method, params or {}))
        if not self.responses:
            raise AssertionError(f"Unexpected Telegram call: {method}")
        expected_method, response = self.responses.pop(0)
        self.assert_method(expected_method, method)
        if isinstance(response, Exception):
            raise response
        return response

    @staticmethod
    def assert_method(expected, actual):
        if expected != actual:
            raise AssertionError(f"Expected {expected}, got {actual}")


class TokenValidationTests(unittest.TestCase):
    def test_accepts_realistic_bot_token(self):
        token = VALID_TOKEN
        self.assertEqual(validate_token(token), token)

    def test_rejects_token_with_shell_or_url_characters(self):
        for token in (
            "",
            "123:not-long-enough",
            "1234567890:abc/defghijklmnopqrstuvwxyz1234567890",
            "1234567890:abc defghijklmnopqrstuvwxyz1234567890",
            "https://api.telegram.org/bot1234567890:abcdef",
        ):
            with self.subTest(token=token):
                with self.assertRaises(TelegramError):
                    validate_token(token)


class ClientEnvironmentTests(unittest.TestCase):
    def test_production_ignores_custom_api_base_from_environment(self):
        with patch.dict(
            os.environ,
            {
                "TELEGRAM_BOT_TOKEN": VALID_TOKEN,
                "TELEGRAM_API_BASE": "https://attacker.invalid",
            },
            clear=True,
        ):
            client = _client_from_env()

        self.assertEqual(client._base, "https://api.telegram.org")

    def test_test_mode_allows_local_mock_api_base(self):
        with patch.dict(
            os.environ,
            {
                "TELEGRAM_BOT_TOKEN": VALID_TOKEN,
                "TELEGRAM_API_BASE": "http://127.0.0.1:12345",
                "HERMES_INSTALLER_TEST_MODE": "1",
            },
            clear=True,
        ):
            client = _client_from_env()

        self.assertEqual(client._base, "http://127.0.0.1:12345")


class PrepareBotTests(unittest.TestCase):
    def test_returns_bot_identity_when_no_webhook_is_configured(self):
        client = FakeClient(
            [
                ("getMe", {"id": 42, "username": "guide_bot", "is_bot": True}),
                ("getWebhookInfo", {"url": ""}),
            ]
        )

        result = prepare_bot(client)

        self.assertEqual(result, {"id": 42, "username": "guide_bot"})

    def test_rejects_existing_webhook_without_deleting_it(self):
        client = FakeClient(
            [
                ("getMe", {"id": 42, "username": "guide_bot", "is_bot": True}),
                ("getWebhookInfo", {"url": "https://existing.example/webhook"}),
            ]
        )

        with self.assertRaisesRegex(TelegramError, "webhook"):
            prepare_bot(client)

        self.assertEqual([method for method, _ in client.calls], ["getMe", "getWebhookInfo"])


class ClaimOwnerTests(unittest.TestCase):
    def test_ignores_stale_wrong_and_group_messages_then_accepts_exact_private_start(self):
        payload = "claim_A1B2C3"
        client = FakeClient(
            [
                (
                    "getUpdates",
                    [
                        {
                            "update_id": 10,
                            "message": {
                                "text": f"/start {payload}",
                                "from": {"id": 100, "is_bot": False},
                                "chat": {"id": 100, "type": "private"},
                            },
                        }
                    ],
                ),
                (
                    "getUpdates",
                    [
                        {
                            "update_id": 11,
                            "message": {
                                "text": "/start wrong",
                                "from": {"id": 101, "is_bot": False},
                                "chat": {"id": 101, "type": "private"},
                            },
                        },
                        {
                            "update_id": 12,
                            "message": {
                                "text": f"/start {payload}",
                                "from": {"id": 102, "is_bot": False},
                                "chat": {"id": -102, "type": "group"},
                            },
                        },
                        {
                            "update_id": 13,
                            "message": {
                                "text": f"/start {payload}",
                                "from": {
                                    "id": 103,
                                    "is_bot": False,
                                    "username": "owner",
                                    "first_name": "Owner",
                                },
                                "chat": {"id": 103, "type": "private"},
                            },
                        },
                    ],
                ),
            ]
        )

        result = claim_owner(
            client,
            payload,
            timeout_seconds=30,
            monotonic_values=iter([0.0, 0.1, 0.2]),
        )

        self.assertEqual(
            result,
            {"user_id": "103", "chat_id": "103", "username": "owner", "first_name": "Owner"},
        )
        first_params = client.calls[0][1]
        second_params = client.calls[1][1]
        self.assertEqual(first_params["offset"], -1)
        self.assertEqual(second_params["offset"], 11)
        self.assertEqual(second_params["allowed_updates"], ["message"])

    def test_rejects_sender_chat_identity_mismatch(self):
        payload = "claim_safe"
        client = FakeClient(
            [
                ("getUpdates", []),
                (
                    "getUpdates",
                    [
                        {
                            "update_id": 1,
                            "message": {
                                "text": f"/start {payload}",
                                "from": {"id": 200, "is_bot": False},
                                "chat": {"id": 201, "type": "private"},
                            },
                        }
                    ],
                ),
            ]
        )

        with self.assertRaisesRegex(TelegramError, "timed out"):
            claim_owner(
                client,
                payload,
                timeout_seconds=1,
                monotonic_values=iter([0.0, 0.1, 1.1]),
            )


class EnvUpdateTests(unittest.TestCase):
    def test_upsert_preserves_unrelated_values_replaces_duplicates_and_uses_mode_0600(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "# keep this comment\nFOO=bar\nTELEGRAM_BOT_TOKEN=old\nTELEGRAM_BOT_TOKEN=duplicate\n",
                encoding="utf-8",
            )
            os.chmod(path, 0o644)

            upsert_env(
                path,
                {
                    "TELEGRAM_BOT_TOKEN": VALID_TOKEN,
                    "TELEGRAM_ALLOWED_USERS": "103",
                    "TELEGRAM_HOME_CHANNEL": "103",
                },
            )

            content = path.read_text(encoding="utf-8")
            self.assertIn("# keep this comment\n", content)
            self.assertIn("FOO=bar\n", content)
            self.assertEqual(content.count("TELEGRAM_BOT_TOKEN="), 1)
            self.assertIn("TELEGRAM_ALLOWED_USERS=103\n", content)
            self.assertIn("TELEGRAM_HOME_CHANNEL=103\n", content)
            mode = stat.S_IMODE(path.stat().st_mode)
            self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
