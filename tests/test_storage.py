from datetime import datetime
import asyncio
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from admin_api import AdminInbox
from reservation_storage import save_confirmed

DETAILS = {"first_name": "Anna", "surname": "Example", "car_number": "WX1234",
           "start": "2099-01-01 10:00", "end": "2099-01-02 10:00"}
TIME = "2026-09-30T12:00:00+00:00"


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name) / "confirmed"
        self.key = str(uuid4())

    def tearDown(self):
        self.temp.cleanup()

    def save(self, request):
        return save_confirmed(request["id"], request["details"], request["approval_time"], self.directory)

    def inbox(self, writer=None):
        inbox = AdminInbox("admin", "bot", writer=writer or self.save)
        code, _ = inbox.dispatch("PUT", f"/requests/{self.key}", "Bearer bot",
                                 {"details": DETAILS, "message": "Review this reservation."})
        self.assertEqual(code, 200)
        return inbox

    def decide(self, inbox, decision="confirmed", token="admin"):
        return inbox.dispatch("POST", f"/requests/{self.key}/decision", f"Bearer {token}",
                              {"status": decision})

    def test_admin_confirmation_saves_required_format_once(self):
        inbox = self.inbox()
        self.assertFalse(self.directory.exists())
        self.assertEqual(self.decide(inbox)[0], 200)
        self.assertEqual(self.decide(inbox)[0], 200)
        saved = list(self.directory.glob("*.txt"))
        self.assertEqual(len(saved), 1)
        columns = saved[0].read_text().strip().split(" | ")
        self.assertEqual(columns[:3], ["Anna Example", "WX1234", "2099-01-01 10:00 to 2099-01-02 10:00"])
        self.assertIsNotNone(datetime.fromisoformat(columns[3]).tzinfo)
        self.assertEqual(saved[0].stat().st_mode & 0o777, 0o600)
        # Reopening storage and replaying a saved request remains idempotent.
        self.save(inbox.requests[self.key])
        self.assertEqual(len(list(self.directory.glob("*.txt"))), 1)

    def test_unauthorized_and_refused_requests_do_not_write(self):
        inbox = self.inbox()
        self.assertEqual(self.decide(inbox, token="bot")[0], 403)
        self.assertEqual(self.decide(inbox, "refused")[0], 200)
        self.assertFalse(self.directory.exists())

    def test_lost_acknowledgement_keeps_pending_and_retry_is_safe(self):
        def interrupted(request):
            self.save(request)
            raise TimeoutError("Lost acknowledgement")

        inbox = self.inbox(interrupted)
        self.assertEqual(self.decide(inbox)[0], 503)
        self.assertEqual(inbox.requests[self.key]["status"], "pending")
        self.assertEqual(self.decide(inbox, "refused")[0], 409)
        before = (self.directory / f"{self.key}.txt").read_bytes()
        inbox.writer = self.save
        self.assertEqual(self.decide(inbox)[0], 200)
        self.assertEqual((self.directory / f"{self.key}.txt").read_bytes(), before)

    def test_rejects_path_injection_line_injection_and_conflicting_retries(self):
        for key, details in [("../../escape", DETAILS),
                             (self.key, {**DETAILS, "first_name": "Anna\nFake"}),
                             (self.key, {**DETAILS, "car_number": "AA | BB"})]:
            with self.assertRaises(ValueError):
                save_confirmed(key, details, TIME, self.directory)
        save_confirmed(self.key, DETAILS, TIME, self.directory)
        with self.assertRaises(ValueError):
            save_confirmed(self.key, {**DETAILS, "surname": "Changed"}, TIME, self.directory)

    def test_failed_replace_leaves_no_partial_record(self):
        with patch("reservation_storage.os.replace", side_effect=OSError("Write failed")):
            with self.assertRaises(OSError):
                save_confirmed(self.key, DETAILS, TIME, self.directory)
        self.assertEqual(list(self.directory.glob("*.txt")), [])
        save_confirmed(self.key, DETAILS, TIME, self.directory)
        self.assertTrue((self.directory / f"{self.key}.txt").exists())

    @unittest.skipUnless(importlib.util.find_spec("mcp"), "MCP protocol test requires the SDK dependency")
    def test_real_mcp_initialization_and_tool_discovery(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def check():
            parameters = StdioServerParameters(command=sys.executable, args=[
                str(Path(__file__).resolve().parents[1] / "reservation_mcp.py")])
            async with asyncio.timeout(20):
                async with stdio_client(parameters) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        self.assertIn("store_confirmed_reservation", [tool.name for tool in tools.tools])
                        result = await session.call_tool("store_confirmed_reservation", {
                            "request_id": "../invalid", "details": DETAILS, "approval_time": TIME,
                        })
                        self.assertTrue(result.isError)

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
