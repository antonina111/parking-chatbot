"""Local administrator REST inbox, using Python's built-in HTTP server."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import secrets
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, model_validator

from reservations import FIELDS, Reservation


class RequestBody(BaseModel):
    details: dict[str, str]
    message: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_details(self):
        draft = Reservation()
        draft.begin()
        if set(self.details) != set(FIELDS):
            raise ValueError("Provide all five reservation fields.")
        for field in FIELDS:
            draft.accept(self.details[field])
            if field not in draft.data:
                raise ValueError("Invalid reservation details.")
        self.details = draft.data
        return self


class Decision(BaseModel):
    status: Literal["confirmed", "refused"]


class AdminInbox:
    def __init__(self, admin_token, bot_token):
        if not admin_token or not bot_token or admin_token == bot_token:
            raise ValueError("Set different, nonempty ADMIN_TOKEN and BOT_TOKEN environment variables.")
        self.admin_token = admin_token
        self.bot_token = bot_token
        self.requests = {}

    def dispatch(self, method, path, authorization, body=None):
        """Shared by the HTTP adapter and route tests. Run with one server worker."""
        parts = path.strip("/").split("/")
        listing = method == "GET" and parts == ["requests"]
        deciding = method == "POST" and len(parts) == 3 and parts[2] == "decision"
        submitting = method == "PUT" and len(parts) == 2
        checking = method == "GET" and len(parts) == 3 and parts[2] == "status"
        if parts[0] != "requests" or not (listing or deciding or submitting or checking):
            return 404, {"detail": "Route not found."}
        token = self.admin_token if listing or deciding else self.bot_token
        if not secrets.compare_digest(authorization.encode(), f"Bearer {token}".encode()):
            return 403, {"detail": "Invalid token."}
        if listing:
            return 200, list(self.requests.values())
        try:
            key = str(UUID(parts[1]))
        except ValueError:
            return 422, {"detail": "Invalid request ID."}
        try:
            if submitting:
                request = RequestBody.model_validate(body)
                if key in self.requests:
                    if self.requests[key]["details"] != request.details:
                        return 409, {"detail": "Request ID already used."}
                else:
                    self.requests[key] = {"id": key, **request.model_dump(), "status": "pending"}
            elif key not in self.requests:
                return 404, {"detail": "Request not found."}
            elif deciding:
                decision = Decision.model_validate(body)
                if self.requests[key]["status"] not in {"pending", decision.status}:
                    return 409, {"detail": "This request already has a final decision."}
                self.requests[key]["status"] = decision.status
        except ValidationError:
            return 422, {"detail": "Invalid reservation details or decision."}
        return 200, {"id": key, "status": self.requests[key]["status"]}


def make_handler(inbox):
    class Handler(BaseHTTPRequestHandler):
        def handle_request(self):
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 <= size <= 16384:
                    raise ValueError("Invalid body size")
                body = json.loads(self.rfile.read(size)) if size else None
                status, result = inbox.dispatch(
                    self.command, self.path, self.headers.get("Authorization", ""), body,
                )
            except (ValueError, UnicodeDecodeError):
                status, result = 400, {"detail": "Invalid JSON request."}
            content = json.dumps(result).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        do_GET = do_PUT = do_POST = handle_request

        def log_message(self, *_):
            pass  # Do not log request IDs or personal details.

    return Handler


if __name__ == "__main__":
    inbox = AdminInbox(os.getenv("ADMIN_TOKEN"), os.getenv("BOT_TOKEN"))
    with HTTPServer(("127.0.0.1", 8000), make_handler(inbox)) as server:
        print("Administrator API listening at http://127.0.0.1:8000. Press Ctrl+C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
