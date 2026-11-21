"""Weekly recovery policy shared by the desktop and the watcher."""
from datetime import datetime, time, timedelta
import json
import re
from uuid import uuid4

from browser_login import Stop
from campus_status import atomic_json, valid_id


DAY = timedelta(days=1)
EMPTY = (None,) * 7
CLOCK = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")


def parse_windows(windows, *, legacy=False):
    if not isinstance(windows, list) or len(windows) != 7:
        raise Stop("invalid_windows")
    pairs = []
    for value in windows:
        if value is None and not legacy:
            pairs.append(None)
            continue
        try:
            start, end = value.split("-")
            if not legacy and not (CLOCK.fullmatch(start) and (CLOCK.fullmatch(end) or end == "24:00")):
                raise ValueError()

            def offset(text):
                if text == "24:00":
                    return DAY
                t = time.fromisoformat(text)
                if t.tzinfo is not None:
                    raise ValueError()
                return timedelta(hours=t.hour, minutes=t.minute, seconds=t.second, microseconds=t.microsecond)

            begin, finish = offset(start), offset(end)
            if begin == finish or begin == DAY:
                raise ValueError()
            pairs.append((begin, finish + DAY if finish < begin else finish))
        except (AttributeError, ValueError):
            raise Stop("invalid_windows") from None
    for i, pair in enumerate(pairs):
        following = pairs[(i + 1) % 7]
        if pair and following and pair[1] - DAY > following[0]:
            raise Stop("overlapping_windows")
    if not any(pairs):
        raise Stop("schedule_needs_day")
    return pairs


def boundaries(day, windows, zone):
    pair = windows[day.weekday()]
    if pair is not None:
        midnight = datetime.combine(day, time.min, zone)
        return midnight + pair[0], midnight + pair[1]
    return ()


def allowed_window(now, windows, zone):
    for day in (now.date(), now.date() - DAY):
        if (pair := boundaries(day, windows, zone)) and pair[0] <= now < pair[1]:
            return pair[0].isoformat()
    return None


def settings(source, windows=EMPTY, revision=None):
    return {"source": source, "windows": windows, "revision": revision}


def read_schedule(cfg):
    snap = cfg.get("desktop_status_path")
    if snap:
        try:
            with snap.with_name("schedule.json").open("rb") as file:
                raw = file.read(4097)
            data = json.loads(raw) if len(raw) <= 4096 else None
            if (not isinstance(data, dict) or data.get("schema") != 1 or not valid_id(data.get("revision"))):
                raise ValueError()
            return settings("custom", data["windows"], data["revision"]), parse_windows(data["windows"])
        except FileNotFoundError:
            pass
        except (ValueError, KeyError, OSError, Stop, RecursionError):
            # Never fall back to a broader legacy policy on failed/invalid reads.
            return settings("invalid"), EMPTY
    legacy = cfg["schedule"].get("windows")
    if legacy is not None:
        return settings("legacy", legacy), cfg["legacy_windows"]
    return settings("unset"), EMPTY


def save_schedule(cfg, windows):
    parse_windows(windows)
    snap = cfg.get("desktop_status_path")
    if not snap or not snap.parent.is_dir():
        raise Stop("schedule_storage_error")
    revision = uuid4().hex
    atomic_json(snap.with_name("schedule.json"), {"schema": 1, "revision": revision, "windows": windows})
    return settings("custom", windows, revision)
