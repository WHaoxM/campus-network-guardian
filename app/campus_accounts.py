"""Local account pool shared by desktop and watcher. Only masked rows cross back to the UI."""
from pathlib import Path
import json
import sys
from uuid import NAMESPACE_URL, uuid4, uuid5

from browser_login import Stop, credentials
from campus_schedule import read_schedule, save_schedule
from campus_status import atomic_json, read_local_json, valid_id


MAX_ACCOUNTS = 12


def field(value, limit):
    return (isinstance(value, str) and 0 < len(value) <= limit and bool(value.strip())
            and not any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value))


def store_path(cfg):
    snapshot = cfg.get("desktop_status_path")
    return snapshot.with_name("accounts.private.json") if snapshot else None


def load_accounts(cfg, *, strict=False):
    path = store_path(cfg)
    if path is not None and path.exists():
        data = read_local_json(path, 98304)
        rows = data.get("rows")
        if (data.get("schema") != 1 or not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ACCOUNTS
                or any(not isinstance(r, dict) or not valid_id(r.get("id"))
                       or not field(r.get("username"), 128) or not field(r.get("password"), 256) for r in rows)
                or len({r["id"] for r in rows}) != len(rows)):
            raise Stop("invalid_account_store")
        return rows
    # Older installations keep working until the first desktop edit. The edit
    # imports the configured pool without editing or deleting the local .env.
    env = cfg["browser_path"].parent / cfg["browser_settings"]["local"]["credential_file"]
    if not env.exists() and not strict:
        return []
    rows = []
    for entry in cfg["accounts"]:
        username, password = credentials(env, (entry["username_key"], entry["password_key"]))
        rows.append(dict(id=uuid5(NAMESPACE_URL, "campus-guardian:" + entry["alias"]).hex,
                         alias=entry["alias"], username=username, password=password))
    return rows


def public_rows(rows):
    return [{"id": r["id"], "tail": r["username"][-4:] if len(r["username"]) > 4 else "",
             "primary": i == 0} for i, r in enumerate(rows)]


def edit_accounts(cfg, action, request):
    path = store_path(cfg)
    if path is None or not path.parent.is_dir():
        raise Stop("account_directory_unavailable")
    rows = load_accounts(cfg)
    if any(not field(r["username"], 128) or not field(r["password"], 256) for r in rows):
        raise Stop("account_fields")
    index = next((i for i, row in enumerate(rows) if row["id"] == request.get("id")), -1)
    if action in ("first", "add"):
        if (action == "first") != (not rows):
            raise Stop("account_list_changed")
        username, password = request.get("username"), request.get("password")
        if not field(username, 128) or not field(password, 256):
            raise Stop("account_fields")
        username = username.strip()
        if any(row["username"] == username for row in rows):
            raise Stop("account_duplicate")
        if len(rows) >= MAX_ACCOUNTS:
            raise Stop("account_limit")
        rows.append(dict(id=uuid4().hex, username=username, password=password))
    elif index < 0:
        raise Stop("account_list_changed")
    elif action == "password":
        if not field(request.get("password"), 256):
            raise Stop("account_fields")
        rows[index]["password"] = request["password"]
    elif action == "primary":
        rows.insert(0, rows.pop(index))
    elif action == "remove" and index > 0:
        rows.pop(index)
    else:
        raise Stop("account_list_changed")
    if len(rows) > MAX_ACCOUNTS:
        raise Stop("account_limit")
    atomic_json(path, {"schema": 1, "rows": [{k: r[k] for k in ("id", "username", "password")} for r in rows]})
    return rows


def main():
    from campus_maintenance import read_config
    try:
        cfg = read_config(Path(sys.argv[1]).resolve())
        if (sys.argv[2] == "fixture") != bool(cfg["browser_settings"].get("loopback_fixture")):
            raise Stop("account_profile_mismatch")
        snapshot = cfg.get("desktop_status_path")
        if not snapshot or snapshot != Path(sys.argv[3]).resolve():
            raise Stop("account_profile_mismatch")
        request = json.loads(sys.stdin.read(8193))
        action = request["action"]
        schedule, _ = read_schedule(cfg)
        if action == "schedule_read":
            result = {"schedule": schedule}
        elif action == "schedule_save":
            result = {"schedule": save_schedule(cfg, request.get("windows"))}
        elif action in ("first", "activate") and schedule["source"] not in ("custom", "legacy"):
            result = {"error": "schedule_required", "schedule": schedule}
        else:
            rows = load_accounts(cfg) if action in ("list", "activate") else edit_accounts(cfg, action, request)
            result = {"rows": public_rows(rows), "schedule": schedule}
    except Stop as exc:
        result = {"error": str(exc)}
    except (ValueError, OSError, TypeError, KeyError, IndexError):
        result = {"error": "account_storage_error"}
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
