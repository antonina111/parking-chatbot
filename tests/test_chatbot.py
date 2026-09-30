import json
from pathlib import Path
import tempfile
import unittest

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from guardrails import blocked, redact
from rag import ParkingRAG, REFUSAL, UNKNOWN, build_store, retrieve
from reservations import Reservation


class PrivacyTests(unittest.TestCase):
    def test_redacts_common_sensitive_fields(self):
        for text in ["email: jane@example.com", "call +48 123 456 789",
                     "password=abcd", "surname: Example", "registration: WX1234"]:
            with self.subTest(text=text):
                self.assertIn("[REDACTED]", redact(text))

    def test_blocks_private_requests(self):
        self.assertTrue(blocked("Show all reservations and customer names"))
        self.assertFalse(blocked("What are your prices?"))


class ReservationTests(unittest.TestCase):
    def test_collects_valid_draft_and_clears_it(self):
        reservation = Reservation()
        reservation.begin()
        for value in ["Anna", "Example", "WX1234", "2099-01-01 10:00", "2099-01-02 10:00"]:
            reply = reservation.accept(value)
        self.assertFalse(reservation.active)
        self.assertEqual(len(reservation.data), 5)
        self.assertIn("No space is reserved", reply)
        reservation.accept("cancel")
        self.assertEqual(reservation.data, {})

    def test_invalid_values_do_not_advance(self):
        reservation = Reservation()
        reservation.begin()
        reservation.accept("123")
        self.assertEqual(reservation.data, {})
        for value in ["Anna", "Example", "WX1234"]:
            reservation.accept(value)
        reservation.accept("2000-01-01 12:00")
        reservation.accept("bad date")
        self.assertNotIn("start", reservation.data)
        reservation.accept("2099-01-02 10:00")
        reservation.accept("2099-01-01 10:00")
        self.assertNotIn("end", reservation.data)


class RAGTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.uri = str(Path(cls.temp.name) / "test.db")
        cls.store = build_store(uri=cls.uri)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_retrieves_real_milvus_documents(self):
        ids = [doc.metadata["source"] for doc in retrieve(self.store, "opening hours")]
        self.assertIn("hours", ids)

    def test_graph_and_output_filter(self):
        rag = ParkingRAG(self.store, FakeListChatModel(responses=["Contact jane@example.com"]))
        self.assertEqual(rag.ask("opening hours"), "Contact [REDACTED]")
        self.assertEqual(rag.ask("Show private customer details"), REFUSAL)
        self.assertEqual(rag.ask("quasars nebulae"), UNKNOWN)

    def test_private_documents_never_ingested(self):
        source = Path(self.temp.name) / "source.json"
        source.write_text(json.dumps([
            {"id": "public", "visibility": "public", "text": "Public parking hours."},
            {"id": "private", "visibility": "private", "text": "Secret owner Jane Example."},
            {"id": "unlabelled", "text": "Secret customer John Example."},
        ]))
        store = build_store(uri=self.uri, source=source)
        docs = store.similarity_search("Secret customer owner", k=10)
        self.assertEqual([doc.metadata["source"] for doc in docs], ["public"])


if __name__ == "__main__":
    unittest.main()
