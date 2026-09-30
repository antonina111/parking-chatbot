"""Run with: python app.py"""
from httpx import HTTPError
from ollama import ResponseError

from rag import ParkingRAG, build_store
from admin_agent import AdminAgent
from reservations import ReservationWorkflow


def main():
    rag = ParkingRAG(build_store())
    admin = AdminAgent()
    reservation = ReservationWorkflow(admin)
    print("Parking chatbot (demo data). Ask a question, or type reserve, status, retry, cancel, or quit.")
    try:
        while True:
            text = input("You: ").strip()
            if text.lower() in {"quit", "exit"}:
                break
            if not text:
                continue
            answer = reservation.handle(text)
            if answer is None:
                try:
                    answer = rag.ask(text)
                except (ConnectionError, TimeoutError, HTTPError, ResponseError):
                    answer = "Could not generate an answer. Please check the model service and try again."
            print("Bot:", answer)
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye.")
    finally:
        reservation.draft.data.clear()
        admin.close()


if __name__ == "__main__":
    main()
