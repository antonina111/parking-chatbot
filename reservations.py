"""Collect a single draft locally. No LLM, database, or confirmation action."""
from datetime import datetime
import re

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
        return "This collects a temporary draft, not a confirmed booking. Type cancel to stop. " + QUESTIONS[0]

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
            return ("Draft collected in memory. No space is reserved and nothing has been sent "
                    "to an administrator. Human confirmation will be added in a later stage. "
                    "Type cancel to clear the draft.")
        return QUESTIONS[len(self.data)]
