"""Run with: python app.py"""
from httpx import HTTPError
from ollama import ResponseError

from rag import ParkingRAG, build_store
from reservations import Reservation


def main():
    rag = ParkingRAG(build_store())
    reservation = Reservation()
    print("Parking chatbot (demo data). Ask a question, or type reserve, cancel, or quit.")
    try:
        while True:
            text = input("You: ").strip()
            if text.lower() in {"quit", "exit"}:
                break
            if not text:
                continue
            if text.lower() == "cancel" or reservation.active:
                answer = reservation.accept(text)
            elif text.lower() in {"reserve", "book", "reservation", "book parking", "reserve parking"}:
                answer = reservation.begin()
            else:
                try:
                    answer = rag.ask(text)
                except (ConnectionError, TimeoutError, HTTPError, ResponseError):
                    answer = "Could not generate an answer. Please check the model service and try again."
            print("Bot:", answer)
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye.")
    finally:
        reservation.data.clear()


if __name__ == "__main__":
    main()
