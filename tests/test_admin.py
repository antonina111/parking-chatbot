import unittest
import json
from io import BytesIO
from unittest.mock import patch
from unittest.mock import Mock
from uuid import uuid4

import httpx

from admin_agent import AdminAgent
from admin_api import AdminInbox, make_handler
from reservations import ReservationWorkflow

DETAILS = {"first_name": "Anna", "surname": "Example", "car_number": "WX1234",
           "start": "2099-01-01 10:00", "end": "2099-01-02 10:00"}
ADMIN = {"Authorization": "Bearer test-admin"}
BOT = {"Authorization": "Bearer test-bot"}


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.writer = Mock()
        self.inbox = AdminInbox("test-admin", "test-bot", writer=self.writer)

        def transport(request):
            body = json.loads(request.content) if request.content else None
            code, response = self.inbox.dispatch(request.method, request.url.path,
                                                 request.headers.get("Authorization", ""), body)
            return httpx.Response(code, json=response)

        self.client = httpx.Client(base_url="http://test", headers=BOT,
                                   transport=httpx.MockTransport(transport))
        self.agent = AdminAgent(self.client)
        self.workflow = ReservationWorkflow(self.agent)

    def tearDown(self):
        self.client.close()

    def collect(self):
        self.workflow.handle("reserve")
        for value in DETAILS.values():
            reply = self.workflow.handle(value)
        return reply

    def test_complete_handoff_for_both_decisions(self):
        for decision in ["confirmed", "refused"]:
            with self.subTest(decision=decision):
                self.assertIn("sent to the administrator", self.collect())
                self.assertEqual(self.workflow.draft.data, {})
                self.assertIn("awaiting", self.workflow.handle("status"))
                inbox = self.client.get("/requests", headers=ADMIN).json()
                request = next(row for row in inbox if row["id"] == self.workflow.request_id)
                self.assertEqual(request["details"], DETAILS)
                self.assertIn("Anna Example", request["message"])
                response = self.client.post(f"/requests/{request['id']}/decision",
                                            headers=ADMIN, json={"status": decision})
                self.assertEqual(response.status_code, 200)
                self.assertIn(decision, self.workflow.handle("status"))

    def test_permissions_and_status_privacy(self):
        self.collect()
        path = f"/requests/{self.workflow.request_id}"
        self.assertEqual(self.client.get("/requests").status_code, 403)
        self.assertEqual(self.client.post(path + "/decision", json={"status": "confirmed"}).status_code, 403)
        self.assertEqual(set(self.client.get(path + "/status").json()), {"id", "status"})
        self.assertEqual(self.client.get(path + "/status", headers={"Authorization": "Bearer wrong"}).status_code, 403)
        self.assertEqual(self.client.put(path, headers=ADMIN, json={"details": DETAILS, "message": "test"}).status_code, 403)

    def test_retry_after_lost_response_does_not_duplicate(self):
        original = self.agent.submit

        def lose_response(*args):
            original(*args)
            raise httpx.ReadTimeout("Simulated lost response")

        with patch.object(self.agent, "submit", side_effect=lose_response):
            self.assertIn("retry", self.collect())
        self.assertEqual(self.workflow.draft.data, DETAILS)
        self.assertIn("sent to the administrator", self.workflow.handle("retry"))
        self.assertEqual(len(self.client.get("/requests", headers=ADMIN).json()), 1)
        self.assertEqual(self.workflow.draft.data, {})

    def test_invalid_request_and_decision_conflict(self):
        path = f"/requests/{uuid4()}"
        invalid = {**DETAILS, "end": "2098-01-01 10:00"}
        self.assertEqual(self.client.put(path, json={"details": invalid, "message": "test"}).status_code, 422)
        self.assertEqual(self.client.get(path + "/status").status_code, 404)
        self.collect()
        path = f"/requests/{self.workflow.request_id}"
        self.assertEqual(self.client.post(path + "/decision", headers=ADMIN,
                                         json={"status": "maybe"}).status_code, 422)
        self.client.post(path + "/decision", headers=ADMIN, json={"status": "refused"})
        self.assertEqual(self.client.post(path + "/decision", headers=ADMIN,
                                         json={"status": "confirmed"}).status_code, 409)

    def test_cancel_before_submission_and_pending_guard(self):
        self.workflow.handle("reserve")
        self.workflow.handle("Anna")
        self.workflow.handle("cancel")
        self.assertEqual(self.client.get("/requests", headers=ADMIN).json(), [])
        self.assertEqual(self.workflow.draft.data, {})
        self.collect()
        self.assertIn("outstanding", self.workflow.handle("reserve"))
        self.assertIn("administrator", self.workflow.handle("cancel"))

    def test_http_adapter_serializes_response_and_rejects_bad_json(self):
        for body, expected in [(json.dumps({"details": DETAILS, "message": "Please review"}).encode(), 200),
                               (b"not json", 400)]:
            handler = object.__new__(make_handler(self.inbox))
            handler.command = "PUT"
            handler.path = f"/requests/{uuid4()}"
            handler.request_version = "HTTP/1.1"
            handler.requestline = "PUT /requests HTTP/1.1"
            handler.headers = {**BOT, "Content-Length": str(len(body))}
            handler.rfile = BytesIO(body)
            handler.wfile = BytesIO()
            handler.do_PUT()
            head, payload = handler.wfile.getvalue().split(b"\r\n\r\n", 1)
            self.assertIn(str(expected).encode(), head.split(b"\r\n")[0])
            self.assertIsInstance(json.loads(payload), dict)


if __name__ == "__main__":
    unittest.main()
