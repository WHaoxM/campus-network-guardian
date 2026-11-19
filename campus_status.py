"""Desktop observations and a narrow, acknowledged local pause channel."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from campus_log import desktop_events, safe_code


def read_local_json(path, limit=4096):
    try:
        with path.open("rb") as handle:
            raw = handle.read(limit + 1)
        data = json.loads(raw) if len(raw) <= limit else None
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def atomic_json(path, data):
    tmp = path.with_suffix(".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
    tmp.replace(path)


def parsed_time(value):
    try:
        result = datetime.fromisoformat(value)
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def valid_id(value):
    try:
        return UUID(hex=value).hex == value
    except (ValueError, TypeError, AttributeError):
        return False


class DesktopControl:
    def __init__(self, directory, fixture, pause_seconds):
        self.inbox = directory / "control.json"
        self.persistence = directory / "pause-state.json"
        self.fixture = fixture
        self.duration = timedelta(seconds=pause_seconds)
        self.seen = None
        self.until = None
        state = read_local_json(self.persistence)
        if state.get("schema") == 1 and state.get("fixture") is fixture:
            self.seen = state["seen"] if valid_id(state.get("seen")) else None
            until = parsed_time(state.get("until"))
            if until is not None and until <= datetime.now(timezone.utc) + self.duration:
                self.until = until

    def active(self):
        return self.until is not None and self.until > datetime.now(timezone.utc)

    def save(self, seen, until):
        try:
            atomic_json(self.persistence, {"schema": 1, "fixture": self.fixture, "seen": seen,
                                           "until": until.isoformat() if until else None})
        except OSError:
            return False  # Never acknowledge a control action not actually applied.
        self.seen, self.until = seen, until
        return True

    def poll(self):
        now = datetime.now(timezone.utc)
        request = read_local_json(self.inbox)
        action, request_id = request.get("action"), request.get("id")
        issued = parsed_time(request.get("issued_at"))
        if (request.get("schema") == 1 and request.get("fixture") is self.fixture and valid_id(request_id)
                and request_id != self.seen and action in ("pause", "resume") and issued
                and -2 <= (now - issued).total_seconds() <= 90):
            until = now + self.duration if action == "pause" else None
            if self.save(request_id, until):
                return "desktop_paused" if until else "desktop_resumed"
        if self.until and self.until <= now and self.save(self.seen, None):
            return "desktop_pause_expired"
        return None


class DesktopStatus:
    def __init__(self, path: Path, fixture: bool, log_root, log_limits, zone, pause_seconds):
        self.path = path
        self.run_id = uuid4().hex
        self.started = self.utc_now()
        self.fixture = fixture
        self.phase = "starting"
        self.allowed = None
        self.link = "unknown"
        self.internet = "unknown"
        self.last_check = None
        self.outcome = None
        self.control = DesktopControl(path.parent, fixture, pause_seconds)
        self.log_files = [log_root / f"campus.log.{n}" for n in range(log_limits["backups"], 0, -1)]
        self.log_files.append(log_root / "campus.log")
        self.repeat_seconds = log_limits.get("monitor_repeat_seconds", 60)
        self.events_stamp = None
        self.zone = zone

    @staticmethod
    def utc_now():
        return datetime.now(timezone.utc).isoformat()

    def inspect(self, entries, ssid):
        links = sum(link["ssid"] == ssid for link in entries)
        link = ("suse" if links == 1 else "ambiguous" if links > 1 or len(entries) not in (0, 1)
                else "other" if any(item["ssid"] for item in entries) else "disconnected")
        self.set_link(link)

    def set_link(self, link):
        self.link = link
        if link != "suse":
            self.internet = "unknown"

    def checked(self, online, now):
        self.internet = "online" if online else "offline"
        self.last_check = now.isoformat()

    def publish(self, phase, *, allowed=None, outcome=None):
        self.phase = phase
        if allowed is not None:
            self.allowed = allowed
        if outcome is not None:
            self.outcome = safe_code(outcome)
        data = {
            "schema": 1, "run_id": self.run_id, "pid": os.getpid(),
            "started_at": self.started, "heartbeat_at": self.utc_now(),
            "fixture": self.fixture, "phase": self.phase, "allowed": self.allowed,
            "link": self.link, "internet": self.internet,
            "last_check_at": self.last_check, "outcome": self.outcome,
            "pause_until": self.control.until.isoformat() if self.control.active() else None,
            "control_ack": self.control.seen,
        }
        try:
            atomic_json(self.path, data)
        except OSError:
            # A failed publication makes the desktop snapshot expire; it must
            # not interrupt an otherwise healthy recovery loop.
            return
        self.refresh_events()

    def refresh_events(self):
        def fingerprint(path):
            try:
                stat = path.stat()
                return stat.st_ino, stat.st_size, stat.st_mtime_ns
            except OSError:
                return None

        stamp = tuple(fingerprint(path) for path in self.log_files)
        if stamp == self.events_stamp:
            return
        try:
            rows = desktop_events(self.log_files, self.zone, self.repeat_seconds)
            atomic_json(self.path.parent / "events.json", {"schema": 1, "fixture": self.fixture, "rows": rows})
            self.events_stamp = stamp
        except OSError:
            return
