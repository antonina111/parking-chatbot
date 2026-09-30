"""Collect validated reservation details and coordinate the human handoff."""
from datetime import datetime
import re
from uuid import uuid4

from httpx import HTTPError

FIELDS = ["first_name", "surname", "car_number", "start", "end"]
QUESTIONS = [
    "What is your first name?", "What is your surname?",
    "What is your car registration number?",
    "Start date and time (YYYY-MM-DD HH:MM, local parking time)?",
    "End date and time (YYYY-MM-DD HH:MM, local parking time)?",
]


class Reservation:
    def __init__(self):
        self.active = False
        self.data = {}

    def begin(self):
        self.data.clear()
        self.active = True
        return "Your completed request will be sent for administrator approval. Type cancel to stop collecting details. " + QUESTIONS[0]

    def accept(self, value):
        value = value.strip()
        if value.lower() == "cancel":
            self.data.clear()
            self.active = False
            return "Draft cancelled and cleared."
        if not self.active:
            return "Type reserve to start a draft."
        field = FIELDS[len(self.data)]
        if field in {"first_name", "surname"}:
            if not (1 <= len(value) <= 60 and all(c.isalpha() or c in " '-" for c in value)
                    and any(c.isalpha() for c in value)):
                return "Enter a name using letters, spaces, apostrophes or hyphens."
        elif field == "car_number":
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 -]{1,14}", value) or not any(c.isalnum() for c in value):
                return "Enter a car registration number (2–15 letters, digits, spaces or hyphens)."
        else:
            try:
                date = datetime.strptime(value, "%Y-%m-%d %H:%M")
            except ValueError:
                return "Use a valid date and time: YYYY-MM-DD HH:MM."
            if field == "start" and date <= datetime.now():
                return "The start must be in the future."
            if field == "end" and date <= datetime.strptime(self.data["start"], "%Y-%m-%d %H:%M"):
                return "The end must be after the start."
        self.data[field] = value
        if len(self.data) == len(FIELDS):
            self.active = False
            return "Details collected. No space is reserved until administrator confirmation."
        return QUESTIONS[len(self.data)]


class ReservationWorkflow:
    """One outstanding request per chatbot session; retry uses the same ID."""

    def __init__(self, agent):
        self.agent = agent
        self.draft = Reservation()
        self.request_id = None
        self.sent = False
        self.final = False

    def handle(self, text, defer_submit=False):
        command = text.strip().lower()
        if command == "status":
            if not self.request_id:
                return "No request has been submitted in this session."
            try:
                status = self.agent.status(self.request_id)
            except HTTPError:
                return "Could not check the request. Check the API and type status to try again."
            self.sent = True
            self.draft.data.clear()
            self.final = status in {"confirmed", "refused"}
            return {"pending": "Your reservation is awaiting administrator approval.",
                    "confirmed": "The administrator confirmed your reservation.",
                    "refused": "The administrator refused your reservation."}[status]
        if command == "retry":
            if self.request_id and not self.sent:
                return "" if defer_submit else self.submit()
            return "No failed submission to retry. Type status to check a sent request."
        if command == "cancel":
            if self.request_id and not self.final:
                return "This request may already be with the administrator. Contact them to withdraw it; use status or retry."
            return self.draft.accept("cancel")
        if command in {"reserve", "book", "reservation", "book parking", "reserve parking"}:
            if self.request_id and not self.final:
                return "You already have an outstanding request. Type status or retry."
            self.request_id, self.sent, self.final = None, False, False
            return self.draft.begin()
        if self.draft.active:
            answer = self.draft.accept(text)
            if not self.draft.active and len(self.draft.data) == len(FIELDS):
                self.request_id = str(uuid4())
                return "" if defer_submit else self.submit()
            return answer
        return None

    def submit(self):
        try:
            self.agent.submit(self.request_id, dict(self.draft.data))
        except HTTPError:
            return "Could not verify submission. Details are kept for retry; type retry to resend safely."
        self.sent = True
        self.draft.data.clear()
        return f"Request {self.request_id} sent to the administrator. Type status to check their decision."
