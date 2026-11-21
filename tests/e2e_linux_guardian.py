"""Linux controller CLI and real Chromium; Wi-Fi/route inputs are isolated fixtures."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

from e2e_browser_login import portal_server
from e2e_campus_maintenance import write_browser


PROJECT = Path(__file__).resolve().parents[1]
APP = PROJECT / "app"
DATA = Path(__file__).parent / "data"
STUB = DATA / "linux_network.py"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--work-dir", required=True, type=Path)
    args = p.parse_args()
    if sys.platform != "linux":
        p.error("Requires Linux and installed Playwright Chromium")
    spec = json.loads((DATA / "browser_journey.json").read_text(encoding="utf-8"))
    scenario = json.loads((DATA / "linux_journey.json").read_text(encoding="utf-8"))
    spec.update(relay_host=spec["host"], second_probe=scenario["second_probe"])
    server, portal = portal_server(spec, (DATA / "browser_portal.html").read_text(encoding="utf-8"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with server, tempfile.TemporaryDirectory(dir=args.work_dir, prefix="nm-e2e-") as directory:
        root = Path(directory).resolve()
        config = root / "campus.linux.toml"
        fixture = root / "network.json"
        active = dict(scenario["network"])
        now = scenario["first_tick"]

        def write_fixture(**updates):
            active.update(updates)
            fixture.write_text(json.dumps(dict(active, now=now)), encoding="utf-8")

        for name in ("nmcli", "ip"):
            path = root / name
            path.write_text(f"#!{sys.executable}\n" + STUB.read_text(encoding="utf-8"), encoding="utf-8")
            path.chmod(0o700)
        # On mounted Windows directories chmod may not be enforced, but the
        # launch still uses task-owned paths against a loopback-only config.
        write_fixture()
        template = (APP / "config" / "campus.linux.example.toml").read_text(encoding="utf-8")
        config.write_text(template.replace('interface = ""', f'interface = "{active["interface"]}"')
                          .replace('profile_uuid = ""', f'profile_uuid = "{active["profile"]}"')
                          .replace('runtime_dir = "../runtime/linux-campus"', 'runtime_dir = "state"')
                          .replace('"/usr/bin/nmcli"', json.dumps(str(root / "nmcli"), ensure_ascii=False))
                          .replace('"/usr/sbin/ip"', json.dumps(str(root / "ip"), ensure_ascii=False)), encoding="utf-8")
        url = f"http://{spec['host']}:{server.server_port}"
        write_browser(root / "browser_login.linux.toml",
                      (APP / "config" / "browser_login.example.toml").read_text(encoding="utf-8"), url, url, spec)
        (root / ".env").write_text(f"CAMPUS_USERNAME={spec['username']}\nCAMPUS_PASSWORD={spec['password']}\n",
                                   encoding="utf-8")

        def cli(mode, *flags):
            result = subprocess.run([sys.executable, "-X", "utf8", str(APP / "campus_maintenance.py"),
                                     mode, "--config", str(config), "--rehearsal-state", str(fixture), *flags],
                                    capture_output=True, encoding="utf-8", check=True, timeout=30)
            return json.loads(result.stdout)

        results = []

        def tick(expected, *, posts=0, joins=0):
            outcome = cli("tick")["outcome"]
            join_file = root / "joins"
            observed_joins = len(join_file.read_text(encoding="utf-8").splitlines()) if join_file.is_file() else 0
            if (outcome, portal["submissions"], observed_joins, portal["logout_posts"]) != (expected, posts, joins, 0):
                raise RuntimeError(f"Expected {expected}/{posts}/{joins}/0; "
                                   f"got {outcome}/{portal['submissions']}/{observed_joins}/{portal['logout_posts']}")
            results.append(outcome)

        tick("outside_window")
        policy = cli("schedule", "--windows", *scenario["windows"])
        if cli("schedule") != policy or not cli("status")["allowed"]:
            raise RuntimeError("Saved schedule is not visible to the watcher")
        tick("linux_other_route_present")
        now = scenario["after_other_route"]
        write_fixture(default_route=False, other_wifi=True)
        tick("different_or_ambiguous_wifi")
        write_fixture(other_wifi=False)
        tick("wifi_join_requested", joins=1)
        now = scenario["after_join"]
        write_fixture(connected=True)
        if not cli("observe")["suse_connected"] or portal["submissions"]:
            raise RuntimeError("Read-only observation unexpectedly mutated the portal")
        portal["on_form"] = lambda: write_fixture(wrong_portal_route=True)
        tick("linux_portal_route_mismatch", joins=1)
        portal.pop("on_form")
        now = scenario["after_backoff"]
        write_fixture(wrong_portal_route=False)
        tick("browser_login_verified", posts=1, joins=1)
        tick("online", posts=1, joins=1)
        now = scenario["after_window"]
        write_fixture()
        tick("outside_window", posts=1, joins=1)
        server.shutdown()
        thread.join(timeout=5)
        print(json.dumps({"outcome": "passed", "journey": results, "portal_posts": portal["submissions"]}))


if __name__ == "__main__":
    main()
