"""Run the real CLI in local Edge against a loopback-only fake portal."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
from urllib.parse import parse_qs, urlencode


def portal_server(spec, form):
    state = {"accepted": False, "submissions": 0, "relay_visits": 0, "relay_posts": 0, "logout_posts": 0}
    success_url = spec["success"] + "?" + urlencode({"userIndex": spec["session_token"]})

    class Portal(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, content=""):
            data = content.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            port = self.server.server_port
            portal = f"http://{spec['host']}:{port}"
            relay = f"http://{spec['relay_host']}:{port}"
            if self.path == spec["entry"]:
                if state.get("portal_unavailable"):
                    return self.send(503)
                self.send_response(302)
                self.send_header("Location", success_url if state["accepted"] else relay + spec["bootstrap"])
                self.end_headers()
            elif self.path == spec["bootstrap"]:
                state["relay_visits"] += 1
                self.send(200, "<!doctype html><script>const f=document.createElement('iframe');"
                          "f.src=" + json.dumps(portal + spec["auth"]) +
                          ";document.addEventListener('DOMContentLoaded',()=>document.body.append(f));</script>")
            elif self.path == spec["auth"]:
                if on_form := state.get("on_form"):
                    on_form()
                self.send(200, form.replace("__RELAY__", relay + spec["bootstrap"]).replace("__SUCCESS__", success_url))
            elif self.path == success_url and state["accepted"]:
                self.send(200, """<!doctype html><meta charset=utf-8><h1>假门户登录成功</h1>
                    <button id="toLogOut">下线</button>
                    <div id="mabcolse-confirm" hidden><button id="sure">确定</button></div>
                    <script>
                    document.querySelector('#toLogOut').onclick = () =>
                        document.querySelector('#mabcolse-confirm').hidden = false;
                    const own = new URL(location.href).searchParams.get('userIndex');
                    const other = """ + json.dumps(spec["other_session_token"]) + """;
                    const logout = (session) => fetch(""" + json.dumps(spec["logout"]) + """, {
                        method: 'POST', body: 'userIndex=' + session
                    });
                    document.querySelector('#sure').onclick = () => Promise.allSettled([logout(other),logout(own),logout(own)]);
                    </script>""")
            elif self.path in {spec["probe"], spec.get("second_probe")} and state["accepted"] and self.path not in state.get("failed_probes", []):
                self.send(204)
            elif self.path == spec["strict_probe_path"]:
                self.send(200, "<h1>" + spec["strict_probe_marker"] + "</h1>")
            else:
                self.send(404)

        def do_POST(self):
            if self.path == spec["bootstrap"]:
                state["relay_posts"] += 1
                return self.send(400)
            if self.path == spec["logout"]:
                state["logout_posts"] += 1
                body = self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 4096)).decode("utf-8")
                if state["accepted"] and parse_qs(body) == {"userIndex": [spec["session_token"]]}:
                    state["accepted"] = False
                    return self.send(200, "fixture")
                return self.send(403)
            if self.path != spec["login"]:
                return self.send(404)
            state["submissions"] += 1
            try:
                submitted = json.loads(self.rfile.read(min(int(self.headers["Content-Length"]), 4096)))
            except (ValueError, TypeError, KeyError):
                return self.send(400)
            authorized = [{key: spec[key] for key in ("username", "password", "service")}, *state.get("extra_accounts", [])]
            state["accepted"] = submitted in authorized
            if not state["accepted"] and state.get("explicit_rejection"):
                return self.send(200, json.dumps({"result": "fail", "message": "密码错误"}))
            self.send(200 if state["accepted"] else 403, "fixture")

    return ThreadingHTTPServer((spec["host"], 0), Portal), state


def strict_relay_journey(project, root, server, spec):
    """Observe a browser's native HTTPS upgrade and its exact-host exception."""
    sys.path.insert(0, str(project))
    sys.dont_write_bytecode = True
    from browser_login import seed_http_relay_permissions
    from playwright.sync_api import Error, sync_playwright

    host = spec["strict_probe_host"]
    if not host.endswith(".test") or spec["host"] != "127.0.0.1":
        raise RuntimeError("Strict relay must use a reserved test name and loopback")
    relay = f"http://{host}:{server.server_port}"
    outcomes = []
    old_env = {key: os.environ.get(key) for key in ("TMP", "TEMP", "TMPDIR")}
    try:
        for key in old_env:
            os.environ[key] = str(root)
        for with_exception in (False, True):
            profile = root / ("strict-allow" if with_exception else "strict-control")
            profile.mkdir()
            seed_http_relay_permissions(profile, [relay] if with_exception else [], 180)
            path = profile / "Default" / "Preferences"
            prefs = json.loads(path.read_text(encoding="utf-8"))
            prefs["https_only_mode_enabled"] = True  # Explicit test control only.
            path.write_text(json.dumps(prefs), encoding="utf-8")
            with sync_playwright() as pw:
                context = pw.chromium.launch_persistent_context(
                    profile, channel="msedge", headless=True, ignore_https_errors=False,
                    args=[f"--host-resolver-rules=MAP {host} {spec['host']}", "--no-proxy-server"],
                )
                try:
                    page, statuses = context.pages[0], []
                    page.on("response", lambda r: statuses.append(r.status) if r.request.resource_type == "document" else None)
                    try:
                        page.goto(relay + spec["strict_probe_path"], wait_until="commit", timeout=6500)
                    except Error:
                        pass
                    reached = False
                    try:
                        page.get_by_role("heading", name=spec["strict_probe_marker"]).wait_for(timeout=4500)
                        reached = True
                    except Error:
                        pass
                    expected_status = 200 if with_exception else 307
                    if reached != with_exception or expected_status not in statuses:
                        raise RuntimeError(f"Unexpected strict Edge navigation: {with_exception=}, {reached=}, {statuses=}")
                    outcomes.append({"allowlisted": with_exception, "relay_reached": reached, "statuses": statuses})
                finally:
                    context.close()
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return {"command": "edge_https_first_comparison", "outcomes": outcomes}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--journey", type=Path, required=True)
    p.add_argument("--html", type=Path, required=True)
    p.add_argument("--python", type=Path, default=Path(sys.executable), help="Interpreter of the installed app")
    p.add_argument("--login-only", action="store_true", help="Run the installed browser through one verified fixture login")
    p.add_argument("--serve", action="store_true", help="仅供 Playwright MCP 查看本地假门户")
    args = p.parse_args()
    spec = json.loads(args.journey.read_text(encoding="utf-8"))
    server, state = portal_server(spec, args.html.read_text(encoding="utf-8"))
    base = f"http://{spec['host']}:{server.server_port}"
    relay = f"http://{spec['relay_host']}:{server.server_port}"
    with server:
        if args.serve:
            print(base, flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            return
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        results = []
        config = args.config.resolve()
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix="browser-e2e-", dir=output.parent) as tmp:
                root = Path(tmp)
                text = config.read_text(encoding="utf-8")
                replacements = {
                    "portal_origin": json.dumps(base), "entry_url": json.dumps(base + spec["entry"]),
                    "allowed_origins": json.dumps([base, relay]), "credential_file": '".env"',
                    "runtime_dir": '"run"', "timeout_seconds": "12", "navigation_timeout_seconds": "12",
                    "http_relay_origins": json.dumps([relay]), "verify_delay_seconds": "0.3",
                }
                for key, replacement in replacements.items():
                    text = re.sub(r"(?m)^" + key + r"\s*=.*$", lambda _: key + " = " + replacement, text)
                text = text.split("[[network.probes]]", 1)[0]
                text += '\n[[network.probes]]\nurl = ' + json.dumps(base + spec["probe"]) + '\nstatus = 204\nbody = ""\n'
                (root / "config.toml").write_text("loopback_fixture = true\n" + text, encoding="utf-8")
                (root / ".env").write_text(f'CAMPUS_USERNAME={spec["username"]}\nCAMPUS_PASSWORD={spec["password"]}\n', encoding="utf-8")
                script = config.parents[1] / "browser_login.py"
                scenarios = (
                    ("prepare", "browser_form_ready", 0, 0),
                    ("login", "browser_login_verified", 1, 0),
                    ("login", "already_online", 1, 0),
                    ("logout-prepare", "logout_ready_not_sent", 1, 0),
                    ("logout", "logout_verified", 1, 1),
                    ("prepare", "browser_form_ready", 1, 1),
                )
                for mode, expected, count, logout_count in (scenarios[:2] if args.login_only else scenarios):
                    cmd = [str(args.python.resolve(strict=True)), "-X", "utf8", str(script), mode,
                           "--config", str(root / "config.toml"), "--headless"]
                    proc = subprocess.run(cmd, capture_output=True, encoding="utf-8", timeout=80)
                    if proc.returncode or expected not in proc.stdout or state["submissions"] != count or state["relay_posts"]:
                        raise RuntimeError(f"{mode}: expected {expected}, portal POST count={state['submissions']}\n{proc.stdout}\n{proc.stderr}")
                    if state["logout_posts"] != logout_count:
                        raise RuntimeError(f"{mode}: unexpected logout submission count {state['logout_posts']}")
                    if expected == "browser_login_verified":
                        reports = sorted((root / "run").glob("attempt-*.json"), key=lambda x: x.stat().st_mtime_ns)
                        report = json.loads(reports[-1].read_text(encoding="utf-8"))
                        if report.get("service_match") != "code":
                            raise RuntimeError("Portal choice was not identified by its service code")
                    results.append({"command": mode, "outcome": expected, "portal_posts": count,
                                    "relay_visits": state["relay_visits"], "relay_posts": state["relay_posts"],
                                    "logout_posts": logout_count})
                if not args.login_only and state["relay_visits"] != 4:
                    raise RuntimeError("Expected exactly one relay navigation per authentication-page visit")
                if not args.login_only:
                    results.append(strict_relay_journey(config.parents[1], root, server, spec))
            output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(results, ensure_ascii=False))
        finally:
            server.shutdown()
            thread.join()


if __name__ == "__main__":
    main()
