"""Run with: python app.py"""
from rag import ParkingRAG, build_store
from admin_agent import AdminAgent
from reservations import ReservationWorkflow
from workflow import ParkingWorkflow


def main():
    rag = ParkingRAG(build_store())
    admin = AdminAgent()
    reservation = ReservationWorkflow(admin)
    workflow = ParkingWorkflow(rag=rag, reservation=reservation)
    print("Parking chatbot (demo data). Ask a question, or type reserve, status, retry, cancel, or quit.")
    try:
        while True:
            text = input("You: ").strip()
            if text.lower() in {"quit", "exit"}:
                break
            if not text:
                continue
            answer = workflow.respond(text)
            print("Bot:", answer)
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye.")
    finally:
        reservation.draft.data.clear()
        admin.close()


if __name__ == "__main__":
    main()
