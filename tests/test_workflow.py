"""Pipeline tests: real graphs, agent, API dispatcher and storage; test RAG dependencies."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import httpx
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from admin_agent import AdminAgent
from admin_api import AdminInbox
from rag import ParkingRAG
from reservation_storage import save_confirmed
from reservations import ReservationWorkflow
from workflow import ParkingWorkflow


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)

        def writer(request):
            save_confirmed(request["id"], request["details"], request["approval_time"], self.directory)

        self.inbox = AdminInbox("admin", "bot", writer=writer)

        def transport(request):
            body = json.loads(request.content) if request.content else None
            code, result = self.inbox.dispatch(request.method, request.url.path,
                                                request.headers.get("Authorization", ""), body)
            return httpx.Response(code, json=result)

        self.client = httpx.Client(base_url="http://test", headers={"Authorization": "Bearer bot"},
                                   transport=httpx.MockTransport(transport))
        self.agent = AdminAgent(self.client)
        self.reservation = ReservationWorkflow(self.agent)
        self.store = Mock()
        self.store.similarity_search_with_score.return_value = [
            (Document(page_content="DEMO DATA: Open 24 hours daily.", metadata={"source": "hours"}), 1.0)]
        self.rag = ParkingRAG(self.store, FakeListChatModel(responses=["Demo data: open 24 hours daily."]))
        self.workflow = ParkingWorkflow(rag=self.rag, reservation=self.reservation)

    def tearDown(self):
        self.agent.close()
        self.temp.cleanup()

    def collect(self):
        self.workflow.respond("reserve")
        for value in ["Anna", "Example", "WX1234", "2099-01-01 10:00", "2099-01-02 10:00"]:
            answer = self.workflow.respond(value)
        return answer

    def decide(self, status, token="admin"):
        return self.client.post(f"/requests/{self.reservation.request_id}/decision",
                                headers={"Authorization": f"Bearer {token}"}, json={"status": status})

    def test_question_to_reservation_to_human_to_file_to_user(self):
        self.assertIn("24 hours", self.workflow.respond("What are your opening hours?"))
        self.assertIn("sent to the administrator", self.collect())
        self.assertIn("awaiting", self.workflow.respond("status"))
        self.assertEqual(list(self.directory.glob("*.txt")), [])
        self.assertEqual(self.decide("confirmed", token="bot").status_code, 403)
        self.assertEqual(list(self.directory.glob("*.txt")), [])
        self.assertEqual(self.decide("confirmed").status_code, 200)
        self.assertIn("confirmed", self.workflow.respond("status"))
        self.assertEqual(self.decide("confirmed").status_code, 200)
        files = list(self.directory.glob("*.txt"))
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].read_text().startswith("Anna Example | WX1234 | "))
        self.assertEqual(self.store.similarity_search_with_score.call_count, 1)

    def test_refusal_bypasses_recording(self):
        self.collect()
        with patch.object(self.inbox, "writer") as writer:
            self.assertEqual(self.decide("refused").status_code, 200)
            writer.assert_not_called()
        self.assertIn("refused", self.workflow.respond("status"))
        self.assertEqual(list(self.directory.glob("*.txt")), [])

    def test_failed_recording_recovers_through_graph(self):
        self.collect()
        with patch.object(self.inbox, "writer", side_effect=OSError("Disk error")):
            self.assertEqual(self.decide("confirmed").status_code, 503)
        self.assertIn("awaiting", self.workflow.respond("status"))
        self.assertEqual(self.decide("confirmed").status_code, 200)
        self.assertIn("confirmed", self.workflow.respond("status"))
        self.assertEqual(len(list(self.directory.glob("*.txt"))), 1)

    def test_submission_failure_and_retry_through_graph(self):
        with patch.object(self.agent, "submit", side_effect=httpx.ConnectError("Disconnected")):
            self.assertIn("retry", self.collect())
        self.assertEqual(len(self.inbox.requests), 0)
        self.assertIn("sent to the administrator", self.workflow.respond("retry"))
        self.assertEqual(len(self.inbox.requests), 1)

    def test_form_input_is_not_sent_to_rag_or_graph_state(self):
        self.workflow.respond("reserve")
        with patch.object(self.workflow.graph, "invoke", wraps=self.workflow.graph.invoke) as invoke:
            self.workflow.respond("Anna")
            self.assertEqual(invoke.call_args.args[0], {"event": "user"})
            self.assertEqual(self.workflow._text, "")
        self.store.similarity_search_with_score.assert_not_called()
        self.workflow.respond("cancel")
        self.assertEqual(self.reservation.draft.data, {})

    def test_rag_error_does_not_break_reservations(self):
        with patch.object(self.rag, "ask", side_effect=ConnectionError("Disconnected")):
            self.assertIn("Could not generate", self.workflow.respond("What are your prices?"))
        self.assertIn("sent to the administrator", self.collect())


if __name__ == "__main__":
    unittest.main()
