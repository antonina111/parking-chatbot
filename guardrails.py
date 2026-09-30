"""Small rule-based guardrails; curated public data is the main privacy boundary."""
import re


PATTERNS = [
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    r"(?<!\w)\+?\d[\d ()-]{7,}\d(?!\w)",
    r"\b(?:password|api[_ -]?key|secret|token)\s*[:=]\s*\S+",
    r"\b(?:first name|surname|full name|car number|registration|license plate)\s*[:=]\s*[^\n,;]+",
]


def redact(text: str) -> str:
    for pattern in PATTERNS:
        text = re.sub(pattern, "[REDACTED]", text, flags=re.IGNORECASE)
    return text


def blocked(text: str) -> bool:
    return bool(re.search(
        r"\b(passwords?|secrets?|tokens?|private|confidential|personal data|"
        r"api[ _-]?keys?|system prompt|ignore.{0,30}instructions|"
        r"other (?:users?|customers?)|all reservations|customer (?:names|details))\b",
        text, re.IGNORECASE,
    ))
