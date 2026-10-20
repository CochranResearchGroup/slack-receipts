from __future__ import annotations

import hmac
import json
import os
import time
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any


def _verify_signature(signing_secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    if not signing_secret:
        return False
    base = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
    expected = "v0=" + hmac.new(signing_secret.encode("utf-8"), base, sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def run_webhook_server(
    *,
    bind: str,
    port: int,
    signing_secret: str,
    on_event,
) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/healthz":
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):  # noqa: N802
            if self.path != "/slack/events":
                self.send_response(404)
                self.end_headers()
                return

            raw_len = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(raw_len)

            ts = self.headers.get("X-Slack-Request-Timestamp", "")
            sig = self.headers.get("X-Slack-Signature", "")

            # replay window 5 minutes
            now = int(time.time())
            if not ts or abs(now - int(ts or "0")) > 300:
                self.send_response(401)
                self.end_headers()
                return

            if not _verify_signature(signing_secret, ts, body, sig):
                self.send_response(401)
                self.end_headers()
                return

            payload = json.loads(body.decode("utf-8"))

            if payload.get("type") == "url_verification":
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"challenge": payload.get("challenge")}).encode("utf-8"))
                return

            on_event(payload)
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, fmt: str, *args: Any) -> None:
            if os.getenv("SLACK_MIRROR_QUIET_HTTP", "1") == "1":
                return
            super().log_message(fmt, *args)

    server = HTTPServer((bind, port), Handler)
    print(f"Webhook server listening on http://{bind}:{port}/slack/events")
    server.serve_forever()


def dispatch_socket_request(client, request, *, on_event, on_interactive=None):
    """Dispatch only SDK-delivered envelopes from the authenticated Socket Mode connection."""
    from slack_sdk.socket_mode.response import SocketModeResponse
    if request.type == 'interactive':
        if on_interactive is not None:
            # Commit the response before ACK. A persistence failure lets Slack
            # retry the original envelope; handlers must never send from here.
            on_interactive(request.envelope_id, request.payload)
        client.send_socket_mode_response(SocketModeResponse(envelope_id=request.envelope_id))
    elif request.type == 'events_api':
        client.send_socket_mode_response(SocketModeResponse(envelope_id=request.envelope_id))
        on_event(request.payload)


def run_socket_mode(
    *,
    app_token: str,
    bot_token: str,
    on_event,
    on_interactive=None,
) -> None:
    from slack_sdk.web import WebClient
    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.response import SocketModeResponse
    from slack_sdk.socket_mode.request import SocketModeRequest
    from threading import Event

    client = SocketModeClient(
        app_token=app_token,
        web_client=WebClient(token=bot_token),
    )

    print("Socket Mode client starting", flush=True)

    def process_event(client: SocketModeClient, req: SocketModeRequest):
        print(f"Received Socket Mode event: {req.type}", flush=True)
        dispatch_socket_request(client, req, on_event=on_event, on_interactive=on_interactive)

    client.socket_mode_request_listeners.append(process_event)
    client.connect()

    Event().wait()

