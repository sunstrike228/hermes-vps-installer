#!/usr/bin/env python3
"""Local Telegram Bot API mock used by integration tests."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


class _Handler(BaseHTTPRequestHandler):
    server_version = "TelegramMock/1.0"

    @property
    def mock(self) -> "MockTelegramServer":
        return self.server.mock_owner  # type: ignore[attr-defined]

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        expected_prefix = f"/bot{self.mock.token}/"
        parsed = urlparse(self.path)
        if not parsed.path.startswith(expected_prefix):
            self._respond(404, {"ok": False, "description": "not found"})
            return
        method = parsed.path[len(expected_prefix) :]
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            params = json.loads(body.decode("utf-8")) if body else {}
        except (ValueError, json.JSONDecodeError):
            self._respond(400, {"ok": False, "description": "invalid json"})
            return

        self.mock.calls.append((method, params))
        if method == "getMe":
            result: Any = {"id": 9001, "username": "integration_bot", "is_bot": True}
        elif method == "getWebhookInfo":
            result = {"url": ""}
        elif method == "getUpdates":
            if params.get("offset") == -1:
                result = [self.mock.message_update(10, 666, f"/start {self.mock.claim_payload}")]
            elif not self.mock.claim_updates_delivered:
                self.mock.claim_updates_delivered = True
                result = [
                    self.mock.message_update(11, 555, "/start wrong"),
                    self.mock.message_update(12, 777, f"/start {self.mock.claim_payload}"),
                ]
            else:
                result = []
        elif method == "sendMessage":
            self.mock.sent_messages.append((str(params.get("chat_id")), str(params.get("text"))))
            result = {"message_id": 1}
        else:
            self._respond(404, {"ok": False, "description": f"unknown method {method}"})
            return
        self._respond(200, {"ok": True, "result": result})

    def _respond(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        del format, args
        return


class MockTelegramServer:
    def __init__(self, *, token: str, claim_payload: str) -> None:
        self.token = token
        self.claim_payload = claim_payload
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.sent_messages: list[tuple[str, str]] = []
        self.claim_updates_delivered = False
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.base_url = ""

    @staticmethod
    def message_update(update_id: int, user_id: int, text: str) -> dict[str, Any]:
        return {
            "update_id": update_id,
            "message": {
                "text": text,
                "from": {
                    "id": user_id,
                    "is_bot": False,
                    "username": f"user{user_id}",
                    "first_name": "Owner",
                },
                "chat": {"id": user_id, "type": "private"},
            },
        }

    def __enter__(self) -> "MockTelegramServer":
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        server.mock_owner = self  # type: ignore[attr-defined]
        self._server = server
        host, port = server.server_address[:2]
        self.base_url = f"http://{host}:{port}"
        thread = threading.Thread(target=server.serve_forever, name="telegram-mock", daemon=True)
        self._thread = thread
        thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit("Import MockTelegramServer from tests; it is not a standalone daemon")
