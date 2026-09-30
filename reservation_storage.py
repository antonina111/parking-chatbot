"""Fixed-directory, atomic storage for approved reservations (macOS/Linux)."""
from datetime import datetime
import fcntl
import os
from pathlib import Path
import tempfile
from uuid import UUID

ROOT = Path(__file__).resolve().parent
STORAGE = ROOT / "data" / "confirmed_reservations"


def save_confirmed(request_id: str, details: dict, approval_time: str, directory=STORAGE):
    request_id = str(UUID(request_id))  # IDs cannot contain paths.
    fields = [details[key] for key in ("first_name", "surname", "car_number", "start", "end")]
    if any(not isinstance(value, str) or not value.strip() or len(value) > 100
           or any(ord(char) < 32 or char == "|" for char in value) for value in fields):
        raise ValueError("Invalid reservation fields.")
    start, end = (datetime.strptime(details[key], "%Y-%m-%d %H:%M") for key in ("start", "end"))
    if end <= start:
        raise ValueError("End must be after start.")
    approved = datetime.fromisoformat(approval_time)
    if approved.tzinfo is None:
        raise ValueError("Approval time must include a timezone.")
    line = (f"{fields[0]} {fields[1]} | {fields[2]} | {fields[3]} to {fields[4]} | "
            f"{approved.isoformat()}\n")
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    target = directory / f"{request_id}.txt"
    # Stable lock protects the existence check and atomic rename across processes.
    lock_fd = os.open(directory / ".write.lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(lock_fd, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if target.exists():
            if target.read_text(encoding="utf-8") != line:
                raise ValueError("Request ID already contains different approval data.")
        else:
            fd, temporary = tempfile.mkstemp(prefix=".reservation-", dir=directory)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as output:
                    output.write(line)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        # Also synchronize the directory entry, including on an idempotent retry.
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    return {"saved": True, "request_id": request_id}
