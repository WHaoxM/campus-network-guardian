"""Real controller CLI + Edge + isolated portal, using a virtual wall clock."""
import argparse
import json
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time

from e2e_browser_login import portal_server


def write_browser(path, template, base, relay, spec):
    replacements = {
        "entry_url": json.dumps(base + spec["entry"]),
        "portal_origin": json.dumps(base),
        "allowed_origins": json.dumps([base, relay]),
        "http_relay_origins": json.dumps([relay]),
        "credential_file": '".env"', "runtime_dir": '"edge-runs"',
        "navigation_timeout_seconds": "2", "timeout_seconds": "5", "verify_delay_seconds": "0.2",
        "verify_attempts": "2",
    }
    body = template.split("[[network.probes]]", 1)[0]
    for key, v in replacements.items():
        body = re.sub(r"(?m)^" + key + r"\s*=.*$", lambda _: key + " = " + v, body)
    for probe in (spec["probe"], spec["second_probe"]):
        body += "\n[[network.probes]]\nurl = " + json.dumps(base + probe) + "\nstatus = 204\nbody = \"\"\n"
    path.write_text("loopback_fixture = true\n" + body, encoding="utf-8")


def check_log_view(cmd, path, fixture, scenario):
    logs = [*cmd[:4], "logs", *cmd[5:]]

    def view(kind):
        r = subprocess.run([*logs, "--filter", kind, "--tail", "100"], capture_output=True, encoding="utf-8", timeout=15, check=True)
        return r.stdout

    important, auth, expanded = (view(kind) for kind in ("important", "auth", "all"))
    if "已确认掉线" not in important or "开始尝试登录" not in important or "门户明确拒绝凭证" not in important:
        raise RuntimeError("Important log omits a recovery decision")
    if "正在复核" in important or "等待 SUSE 接入" in important or "正在复核" not in expanded:
        raise RuntimeError("Default filter did not hide routine probes")
    if "[auth]" not in auth or any(tag in auth for tag in ("[network]", "[wifi]", "[schedule]", "[quiet]")):
        raise RuntimeError("Auth view included unrelated events")
    if any(value in expanded for _, user, pw in scenario["accounts"] for value in (user, pw)):
        raise RuntimeError("Log view exposed test credentials")

    q = queue.Queue()
    child = subprocess.Popen([*logs, "--follow", "--filter", "wifi", "--tail", "0"],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, encoding="utf-8")
    reader = threading.Thread(target=lambda: [q.put(line) for line in child.stdout], daemon=True)
    reader.start()

    def until(needle):
        cutoff = time.monotonic() + 8
        result = []
        while time.monotonic() < cutoff:
            try:
                line = q.get(timeout=max(0.1, cutoff - time.monotonic()))
            except queue.Empty:
                break
            result.append(line)
            if needle in line:
                return result
        raise RuntimeError("Log follower did not show expected new event")

    def tick(now, wifi):
        fixture.write_text(json.dumps({"now": now, "wifi": wifi}), encoding="utf-8")
        subprocess.run(cmd, capture_output=True, encoding="utf-8", timeout=15, check=True)

    try:
        until("正在跟踪日志")
        # Force the existing file to rotate on the next actual watcher write.
        path.write_text(re.sub(r"(?m)^max_bytes\s*=.*$", "max_bytes = 768", path.read_text(encoding="utf-8")), encoding="utf-8")
        tick("2026-11-23T07:11:00+08:00", "other")
        until("不抢占其他网络")
        tick("2026-11-23T07:11:10+08:00", "campus")
        tick("2026-11-23T07:11:15+08:00", "other")
        tick("2026-11-23T07:11:20+08:00", "none")
        after = until("其他网络外网已通")
        if any("不抢占其他网络" in line for line in after):
            raise RuntimeError("Log follower repeated an identical status within the deduplication window")
    finally:
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=8)
        reader.join(timeout=3)
    return {"filters": "passed", "live_after_rotation": "passed", "duplicate_status": "suppressed"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--portal", type=Path, required=True)
    p.add_argument("--html", type=Path, required=True)
    p.add_argument("--journey", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    cfg = args.config.resolve()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    scenario = json.loads(args.journey.read_text(encoding="utf-8"))
    spec = dict(json.loads(args.portal.read_text(encoding="utf-8")), second_probe=scenario["second_probe"])
    server, state = portal_server(spec, args.html.read_text(encoding="utf-8"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.update(extra_accounts=[{"username": u, "password": pw, "service": spec["service"]}
                                 for alias, u, pw in scenario["accounts"] if alias == "third"], explicit_rejection=True)
    results = []
    with server:
        try:
            with tempfile.TemporaryDirectory(prefix="campus-e2e-", dir=output.parent) as folder:
                root = Path(folder)
                browser_path = root / "browser_login.toml"
                browser_template = (cfg.parent / "browser_login.example.toml").read_text(encoding="utf-8")
                base = f"http://{spec['host']}:{server.server_port}"
                relay = f"http://{spec['relay_host']}:{server.server_port}"
                write_browser(browser_path, browser_template, base, relay, spec)
                campus_path = root / cfg.name
                campus = cfg.read_text(encoding="utf-8").split("[[accounts]]", 1)[0]
                campus = re.sub(r'(?m)^runtime_dir\s*=.*$', 'runtime_dir = "state"', campus)
                env, blocks = [], []
                for index, (alias, user, password) in enumerate(scenario["accounts"]):
                    uk, pk = f"FIXTURE_USER_{index}", f"FIXTURE_PASSWORD_{index}"
                    blocks.append(f'\n[[accounts]]\nalias = "{alias}"\nusername_key = "{uk}"\npassword_key = "{pk}"\n')
                    env.extend((f"{uk}={user}", f"{pk}={password}"))
                campus_path.write_text(campus + "".join(blocks), encoding="utf-8")
                (root / ".env").write_text("\n".join(env) + "\n", encoding="utf-8")
                fixture = root / "current.json"
                cmd = [sys.executable, "-X", "utf8", str(cfg.parents[1] / "campus_maintenance.py"),
                       "tick", "--config", str(campus_path), "--rehearsal-state", str(fixture)]
                for step in scenario["steps"]:
                    if "pool_size" in step:
                        campus_path.write_text(campus + "".join(blocks[:step["pool_size"]]), encoding="utf-8")
                    def set_now(at):
                        fixture.write_text(json.dumps({"now": at, "wifi": step.get("wifi", "campus")}), encoding="utf-8")
                    set_now(step["at"])
                    state["on_form"] = (lambda: set_now(step["actuate_at"])) if "actuate_at" in step else None
                    if "online" in step:
                        state["accepted"] = step["online"]
                    if "portal" in step:
                        state["portal_unavailable"] = not step["portal"]
                    state["failed_probes"] = [spec["probe"]] if step.get("lose_first_probe") else []
                    r = subprocess.run(cmd, capture_output=True, encoding="utf-8", timeout=90)
                    actual = json.loads(r.stdout)
                    wrong = (r.returncode or actual["outcome"] != step["want"]
                             or state["submissions"] != step.get("posts", results[-1]["posts"] if results else 0)
                             or state["relay_posts"] or state["logout_posts"])
                    if "account" in step and actual.get("last_success") != step["account"]:
                        wrong = True
                    if "attempts" in step and [[a["alias"], a["result"]] for a in actual["attempts"]] != step["attempts"]:
                        wrong = True
                    if "cooldown" in step and step["cooldown"] not in actual["cooldown"]:
                        wrong = True
                    if "window_day" in step and not actual["window"].startswith(step["window_day"]):
                        wrong = True
                    if wrong:
                        raise RuntimeError(f"{step['at']}: expected {step['want']}, got {actual}; posts={state['submissions']}")
                    results.append({"at": step["at"], "outcome": actual["outcome"], "posts": state["submissions"],
                                    "logout_posts": state["logout_posts"]})
                log_view = check_log_view(cmd, campus_path, fixture, scenario)
            evidence = {"journey": results, "log_view": log_view}
            output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"outcome": "passed", "steps": len(results), "posts": state["submissions"],
                              "logout_posts": state["logout_posts"], "log_view": log_view}, ensure_ascii=False))
        finally:
            server.shutdown()
            thread.join()


if __name__ == "__main__":
    main()
