"""Campus Wi-Fi maintenance. This module never calls portal logout."""
import argparse
from datetime import datetime, timedelta, timezone
import http.client
import ipaddress
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
import time as clock
from urllib.parse import urlsplit

from browser_login import Stop, online, run, single_instance, validate_config, wlan_interfaces
from campus_accounts import load_accounts
from campus_linux import LinuxWifi
from campus_log import FILTERS, TEXT, date_label, safe_code, show_log
from campus_portable import tomllib
from campus_schedule import allowed_window, boundaries, parse_windows, read_schedule, save_schedule
from campus_status import DesktopStatus


ZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")
SAFE_SSID = re.compile(r"[A-Za-z0-9 _.-]{1,32}")
SAFE_ALIAS = re.compile(r"[A-Za-z0-9_-]{1,40}")
ENV_KEY = re.compile(r"[A-Z][A-Z0-9_]{1,63}")


def parse_time(value):
    date = datetime.fromisoformat(value)
    if date.utcoffset() is None:
        raise Stop("time_requires_timezone")
    return date.astimezone(ZONE)


def read_config(path):
    cfg = tomllib.loads(path.read_text(encoding="utf-8"))
    browser_path = (path.parent / cfg["browser_config"]).resolve()
    browser = tomllib.loads(browser_path.read_text(encoding="utf-8"))
    validate_config(browser)
    if (not browser.get("loopback_fixture") and
            len({urlsplit(p["url"]).hostname for p in browser["network"]["probes"]}) < 2):
        raise Stop("two_independent_probe_hosts_required")
    cfg["browser_path"] = browser_path
    cfg["browser_settings"] = browser
    cfg["root"] = (path.parent / cfg["runtime_dir"]).resolve()
    if "schedule_file" in cfg:
        schedule = (cfg["root"] / cfg["schedule_file"]).resolve()
        if schedule.parent != cfg["root"] or schedule.suffix != ".json" or schedule.name == "state.json":
            raise Stop("schedule_storage_error")
        cfg["schedule_path"] = schedule
    if "desktop_status_file" in cfg:
        snapshot = (cfg["root"] / cfg["desktop_status_file"]).resolve()
        if not snapshot.is_relative_to(cfg["root"]) or snapshot.suffix != ".json" or snapshot.parent == cfg["root"]:
            raise Stop("invalid_desktop_status_path")
        cfg["desktop_status_path"] = snapshot
    cfg["browser_root"] = (browser_path.parent / browser["local"]["runtime_dir"]).resolve()
    policy = cfg["schedule"]
    if not policy["backoff_seconds"]:
        raise Stop("invalid_schedule")
    timings = [policy[k] for k in ("poll_seconds", "failure_rounds", "cooldown_seconds", "join_retry_seconds")]
    timings.extend(policy[k] for k in ("join_poll_seconds", "join_scan_retry_seconds") if k in policy)
    dns_timeout = cfg.get("diagnostics", {}).get("dns_timeout_seconds")
    if dns_timeout is not None and (type(dns_timeout) is not int or not 1 <= dns_timeout <= 15):
        raise Stop("invalid_dns_timeout")
    if any(type(n) is not int or n <= 0 for n in [*timings, *policy["backoff_seconds"]]):
        raise Stop("invalid_retry_policy")
    if "windows" in policy:
        cfg["legacy_windows"] = parse_windows(policy["windows"], legacy=True)
    if not SAFE_SSID.fullmatch(browser["local"]["wifi_ssid"]):
        raise Stop("invalid_saved_wlan_name")
    accounts = cfg["accounts"]
    aliases = [a["alias"] for a in accounts]
    keys = [a[k] for a in accounts for k in ("username_key", "password_key")]
    if (not accounts or len(set(aliases)) != len(aliases) or len(set(keys)) != len(keys)
            or not all(SAFE_ALIAS.fullmatch(a) for a in aliases)
            or not all(ENV_KEY.fullmatch(k) for k in keys)):
        raise Stop("invalid_account_configuration")
    return cfg


def wlan_source(guid, powershell):
    # GUID comes only from netsh's parsed interface listing, never from credentials.
    command = ("$ErrorActionPreference='Stop'; "
               f"$g=[guid]'{guid}'; "
               "$a=@(Get-NetAdapter -IncludeHidden | Where-Object { $_.InterfaceGuid -and [guid]$_.InterfaceGuid -eq $g }); "
               "if($a.Count -ne 1){exit 1}; "
               "Get-NetIPAddress -InterfaceIndex $a[0].ifIndex -AddressFamily IPv4 "
               "| Where-Object { $_.AddressState -eq 'Preferred' -and -not $_.SkipAsSource } | ForEach-Object IPAddress")
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    try:
        output = subprocess.check_output([powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
                                         timeout=8, stderr=subprocess.DEVNULL, startupinfo=startup)
        found = []
        for line in output.decode("ascii", errors="ignore").splitlines():
            ip = ipaddress.IPv4Address(line.strip())
            if not ip.is_link_local and not ip.is_loopback and not ip.is_unspecified:
                found.append(str(ip))
        return found[0] if len(found) == 1 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def wlan_visible(netsh, ssid):
    """Return None when Windows hides the scan or its result is inconclusive."""
    try:
        data = subprocess.check_output(
            [netsh, "wlan", "show", "networks"], timeout=5, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).decode("oem", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    names = set(re.findall(r"(?m)^[ \t]*SSID[ \t]+[0-9]+[ \t]*:[ \t]*([^\r\n]*)", data))
    return ssid in {name.strip() for name in names} if names else None


def windows_dns_signals(cfg, guid):
    timeout = cfg.get("diagnostics", {}).get("dns_timeout_seconds")
    if not timeout:
        return None
    hosts = list(dict.fromkeys(urlsplit(p["url"]).hostname for p in cfg["browser_settings"]["network"]["probes"]))
    hosts = [h for h in hosts if h and re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,252}", h)
             and not re.fullmatch(r"[0-9.]+", h)][:2]
    if not hosts:
        return None
    script = Path(__file__).with_name("network_diagnostics.ps1")
    # Match wlan_source: keep PowerShell hidden without losing redirected output.
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    try:
        raw = subprocess.check_output(
            [cfg["windows"]["powershell"], "-NoLogo", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-File", str(script), "-WifiGuid", guid, "-ProbeHosts", ",".join(hosts)],
            timeout=timeout, stderr=subprocess.DEVNULL, startupinfo=startup,
        )
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def wlan_online(network, source):
    # Binding to the WLAN's source address avoids recording a recovery based
    # only on a different adapter's successful HTTPS requests.
    for probe in network["probes"]:
        p = urlsplit(probe["url"])
        c = http.client.HTTPSConnection(p.hostname, p.port, timeout=network["probe_timeout_seconds"],
                                        source_address=(source, 0))
        try:
            c.request("GET", (p.path or "/") + ("?" + p.query if p.query else ""))
            r = c.getresponse()
            if r.status == probe["status"] and r.read(256).strip() == probe["body"].encode("utf-8"):
                return True
        except (OSError, http.client.HTTPException):
            pass
        finally:
            c.close()
    return False


class Controller:
    def __init__(self, cfg, fixture_file):
        self.cfg = cfg
        self.portal = cfg["browser_settings"]
        self.policy = cfg["schedule"]
        self.root = cfg["root"]
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "state.json"
        self.fixture_file = fixture_file
        self.desktop_status = None
        if bool(fixture_file) != bool(self.portal.get("loopback_fixture", False)):
            raise Stop("rehearsal_requires_isolated_loopback_config")
        self.disabled = set()
        self.ssid = self.portal["local"]["wifi_ssid"]
        self.linux = None
        if sys.platform == "linux" and (not fixture_file or "linux" in cfg):
            self.linux = LinuxWifi(cfg.get("linux", {}), self.ssid)
            if fixture_file and not all(Path(command).resolve().is_relative_to(fixture_file.resolve().parent)
                                        for command in (self.linux.ip, self.linux.nmcli)):
                raise Stop("rehearsal_requires_isolated_loopback_config")
        self.accounts = []
        self.sync_accounts()
        self.log = logging.getLogger(str(self.root))
        self.log.setLevel(logging.INFO)
        limits = cfg["logging"]
        if any(type(n) is not int or n <= 0 for n in (limits["max_bytes"], limits["backups"])):
            raise Stop("invalid_log_limits")
        handler = RotatingFileHandler(self.root / "campus.log", encoding="utf-8",
                                      maxBytes=limits["max_bytes"], backupCount=limits["backups"], delay=True)
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.log.addHandler(handler)

    def sync_accounts(self):
        try:
            rows = load_accounts(self.cfg)
        except (Stop, OSError):
            rows = []
        previous = {row["alias"]: row["password"] for row in self.accounts}
        self.accounts = [dict(row, alias=row.get("alias", row["id"])) for row in rows]
        for row in self.accounts:
            if previous.get(row["alias"]) != row["password"]:
                self.disabled.discard(row["alias"])

    def guard_account(self, account, window, guid):
        self.guard(window, guid)
        try:
            matches = any(row["id"] == account["id"] and row["username"] == account["username"]
                          and row["password"] == account["password"] for row in load_accounts(self.cfg))
        except (Stop, OSError):
            matches = False
        if not matches:
            raise Stop("account_configuration_changed")

    def scenario(self):
        return json.loads(self.fixture_file.read_text(encoding="utf-8"))

    def now(self):
        return parse_time(self.scenario()["now"]) if self.fixture_file else datetime.now(ZONE)

    def window(self):
        return allowed_window(self.now(), read_schedule(self.cfg)[1], ZONE)

    def sleep_seconds(self, elapsed, outcome):
        now = self.now()
        poll = self.policy["poll_seconds"]
        if outcome == "suse_not_visible":
            poll = min(poll, self.policy.get("join_scan_retry_seconds", poll))
        if outcome in {"wifi_join_requested", "wifi_join_requested_fixture", "wifi_waiting",
                       "suse_address_not_ready", "wifi_recheck_pending", "wifi_status_unavailable"}:
            # Check association/DHCP sooner; netsh reconnection itself remains throttled.
            poll = min(poll, self.policy.get("join_poll_seconds", poll))
        until = max(0.1, poll - elapsed)
        _, windows = read_schedule(self.cfg)
        for day in (now.date() - timedelta(days=1), now.date(), now.date() + timedelta(days=1)):
            for boundary in boundaries(day, windows, ZONE):
                if boundary > now:
                    until = min(until, (boundary - now).total_seconds())
        return until

    def state(self):
        if self.path.exists():
            s = json.loads(self.path.read_text(encoding="utf-8"))
            if s["version"] != 1 or s["fixture"] != bool(self.fixture_file):
                raise Stop("state_mode_mismatch")
            return s
        return dict(version=1, fixture=bool(self.fixture_file), window=None, was_online=False, observed=False, rotate_after=None,
                    failures=0, last_success=None, cooldown={}, next_attempt=0, backoff_step=0, next_join=0,
                    outcome="not_run")

    def save(self, s):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def event(self, code, kind="state", alias=None, submissions=None, retry_at=None):
        entry = {"time": self.now().isoformat(), "kind": kind, "code": code}
        if alias is not None:
            entry["alias"] = alias
        if submissions is not None:
            entry["submissions"] = submissions
        if retry_at:
            entry["retry_at"] = retry_at
        self.log.info("%s", json.dumps(entry, ensure_ascii=False))

    def finish(self, s, outcome, attempts):
        if not attempts and s["outcome"] != outcome:
            # A verified login already reported the success; the next healthy
            # probe is a continuation of that state, not a second recovery.
            if not (outcome == "online" and s["outcome"] in {"browser_login_verified", "already_online"}):
                self.event(outcome)
        s["outcome"] = outcome
        s["attempts"] = attempts
        self.save(s)
        if self.desktop_status:
            self.desktop_status.publish("monitoring", outcome=outcome)
        return s

    def status_wifi(self, entries):
        if self.desktop_status:
            self.desktop_status.inspect(entries, self.ssid)

    def status_probe(self, probe):
        result = probe()
        if self.desktop_status:
            self.desktop_status.checked(result, self.now())
        return result

    def desktop_paused(self):
        status = self.desktop_status
        if status is None:
            return False
        if event := status.control.poll():
            self.event(event)
            status.publish(status.phase)
        return status.control.active()

    def observe_without_recovery(self):
        """Expose real connectivity without joining Wi-Fi or authorizing."""
        try:
            entries = self.wifi()
        except Stop:
            self.desktop_status.set_link("unknown")
            return
        self.status_wifi(entries)
        links = [link for link in entries if link["ssid"] == self.ssid]
        if len(links) != 1:
            return
        net = self.portal["network"]
        if self.fixture_file:
            self.status_probe(lambda: online(net))
            return
        source = self.source(links[0]["guid"])
        if source:
            self.status_probe(lambda: wlan_online(net, source))
        else:
            self.desktop_status.internet = "unknown"

    def wifi(self):
        if self.linux:
            return self.linux.entries()
        if self.fixture_file:
            scenario = self.scenario()
            if scenario.get("wifi_status_unavailable"):
                raise Stop("wifi_status_unavailable")
            wifi = scenario["wifi"]
            return [{"ssid": self.ssid if wifi == "campus" else "different" if wifi == "other" else None, "guid": "rehearsal"}]
        return wlan_interfaces()

    def source(self, guid):
        if self.linux:
            return self.linux.source(guid)
        return wlan_source(guid, self.cfg["windows"]["powershell"])

    def observe(self):
        links = [link for link in self.wifi() if link["ssid"] == self.ssid]
        source = self.source(links[0]["guid"]) if len(links) == 1 and (self.linux or not self.fixture_file) else None
        net = self.portal["network"]
        return {"outcome": "observation_only", "allowed": bool(self.window()), "suse_connected": len(links) == 1,
                "source_available": bool(source),
                "suse_probe_ok": (online(net) if self.fixture_file else wlan_online(net, source)) if source else None}

    def guard(self, window, expected_guid=None):
        def check_schedule():
            schedule, windows = read_schedule(self.cfg)
            if (schedule["source"], schedule["revision"]) != self.round_schedule:
                raise Stop("schedule_changed")
            if allowed_window(self.now(), windows, ZONE) != window:
                raise Stop("outside_window")

        if self.desktop_paused():
            raise Stop("pause_gate_wait")
        check_schedule()
        if expected_guid is not None:
            if not any(item["guid"] == expected_guid and item["ssid"] == self.ssid for item in self.wifi()):
                raise Stop("wifi_changed_before_submit")
            check_schedule()
            if self.desktop_paused():
                raise Stop("pause_gate_wait")

    def diagnose_dns(self, guid, reason):
        if self.linux:
            return None
        if reason not in {"browser_portal_unavailable", "browser_dns_resolution_failed", "browser_proxy_unavailable",
                          "browser_navigation_failed", "browser_form_not_found", "browser_relay_did_not_finish",
                          "browser_login_not_verified", "browser_login_request_not_observed"}:
            return None
        signals = self.scenario().get("dns") if self.fixture_file else windows_dns_signals(self.cfg, guid)
        if not isinstance(signals, dict) or signals.get("system") is not False:
            return None
        if signals.get("wifi") is True:
            return "vpn_dns_suspected" if signals.get("vpn") is True else "dns_configuration_suspected"
        return "dns_resolution_unavailable"

    def connect_saved(self, entries, window):
        self.guard(window)
        fresh = self.wifi()
        if len(entries) != 1 or len(fresh) != 1 or fresh[0]["guid"] != entries[0]["guid"] or fresh[0]["ssid"]:
            return "wifi_join_deferred"
        self.guard(window)
        if self.linux:
            return self.linux.connect_saved(lambda: self.guard(window))
        if self.fixture_file:
            return "wifi_join_requested_fixture"
        try:
            result = subprocess.run([self.cfg["windows"]["netsh"], "wlan", "connect", f"name={self.ssid}", f"ssid={self.ssid}"],
                                    capture_output=True, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
            return "wifi_join_requested" if result.returncode == 0 else "wifi_saved_profile_unavailable"
        except (OSError, subprocess.SubprocessError):
            return "wifi_join_failed"

    def backoff(self, s, earlier=0):
        values = self.policy["backoff_seconds"]
        i = min(s["backoff_step"], len(values) - 1)
        s["next_attempt"] = max(earlier, self.now().timestamp() + values[i])
        s["backoff_step"] = min(i + 1, len(values) - 1)
        self.event("retry_scheduled", retry_at=s["next_attempt"])

    def mark_online(self, s):
        s.update(was_online=True, observed=True, failures=0, next_attempt=0, backoff_step=0,
                 rotate_after=None, link_recheck_streak=0)

    def attempt(self, account, window, guid, probe):
        self.guard(window, guid)
        alias = account["alias"]
        cpath = self.cfg["browser_path"]
        auth = (account["username"], account["password"])
        root = self.cfg["browser_root"]
        root.mkdir(parents=True, exist_ok=True)
        report = dict(documents=[], login_submissions=0, submission_clicked=False, success_page=False, network_online=False)
        args = SimpleNamespace(mode="login", show=False, headless=True)
        try:
            with single_instance(root):
                result = run(args, self.portal, cpath, root, report, account=auth, probe=probe,
                             login_guard=lambda: self.guard_account(account, window, guid),
                             connection_guard=(lambda: self.guard(window, guid)) if self.linux else None,
                             request_guard=self.linux.require_portal_route if self.linux else None)
        except Stop as exc:
            result = str(exc)
        except Exception as exc:
            result = "browser_error_" + type(exc).__name__
        return dict(alias=alias, result=result, submissions=report["login_submissions"])

    def tick(self):
        self.sync_accounts()
        s = self.state()
        local_now = self.now()
        now = local_now.timestamp()
        schedule, windows = read_schedule(self.cfg)
        self.round_schedule = schedule["source"], schedule["revision"]
        window = allowed_window(local_now, windows, ZONE)
        if self.desktop_status:
            self.desktop_status.schedule_source, self.desktop_status.schedule_revision = self.round_schedule
            self.desktop_status.publish("checking", allowed=bool(window))
        paused = self.desktop_paused()
        if not window:
            if self.desktop_status:
                self.observe_without_recovery()
            s.update(window=None, failures=0, observed=False, was_online=False)
            return self.finish(s, "outside_window", [])
        if paused:
            self.observe_without_recovery()
            s.update(failures=0, observed=False, was_online=False)
            return self.finish(s, "pause_gate_wait", [])
        if s["window"] != window:
            s.update(window=window, failures=0, observed=False, was_online=False,
                     next_attempt=0, backoff_step=0, rotate_after=None, link_recheck_streak=0)
            self.event("window_open")
        s["cooldown"] = {a: n for a, n in s["cooldown"].items() if n > now}
        try:
            entries = self.wifi()
        except Stop as exc:
            if self.desktop_status:
                self.desktop_status.set_link("unknown")
            return self.finish(s, str(exc), [])
        self.status_wifi(entries)
        links = [i for i in entries if i["ssid"] == self.ssid]
        net = self.portal["network"]
        if len(links) != 1:
            s["failures"] = 0
            if any(i["ssid"] for i in entries):
                return self.finish(s, "different_or_ambiguous_wifi", [])
            if online(net):
                return self.finish(s, "other_network_online", [])
            if len(entries) != 1:
                return self.finish(s, "different_or_ambiguous_wifi", [])
            if now >= s["next_join"]:
                visible = (self.linux.visible() if self.linux else self.scenario().get("nearby_suse") if self.fixture_file
                           else wlan_visible(self.cfg["windows"]["netsh"], self.ssid))
                if visible is False:
                    s["next_join"] = now + self.policy.get("join_scan_retry_seconds", self.policy["poll_seconds"])
                    return self.finish(s, "suse_not_visible", [])
                s["next_join"] = now + self.policy["join_retry_seconds"]
                if self.desktop_status:
                    self.desktop_status.publish("joining")
                return self.finish(s, self.connect_saved(entries, window), [])
            return self.finish(s, "wifi_waiting", [])

        guid = links[0]["guid"]
        source = self.source(guid) if self.linux or not self.fixture_file else None
        if not source and (self.linux or not self.fixture_file):
            if self.desktop_status:
                self.desktop_status.internet = "unknown"
            s["failures"] = 0
            return self.finish(s, "suse_address_not_ready", [])
        raw_probe = (lambda: wlan_online(net, source)) if source and not self.fixture_file else (lambda: online(net))
        probe = lambda: self.status_probe(raw_probe)
        if probe():
            self.mark_online(s)
            return self.finish(s, "online", [])
        if source and online(net):
            s["failures"] = 0
            return self.finish(s, "other_network_online", [])

        s["failures"] += 1
        k = self.policy["failure_rounds"]
        if s["observed"] and s["failures"] < k:
            return self.finish(s, "checking_outage", [])
        takeover = s["was_online"]
        if takeover:
            self.event("outage_confirmed")
        if takeover and s["last_success"]:
            s["cooldown"][s["last_success"]] = now + self.policy["cooldown_seconds"]
            s["rotate_after"] = s["last_success"]
        s.update(observed=True, was_online=False, failures=k)
        if now < s["next_attempt"]:
            return self.finish(s, "backoff_wait", [])

        order = [a["alias"] for a in self.accounts]
        anchor = s.get("rotate_after")
        offset = order.index(anchor) + 1 if anchor in order else 0
        ordered = self.accounts[offset:] + self.accounts[:offset]
        eligible = [a for a in ordered if a["alias"] not in s["cooldown"] and a["alias"] not in self.disabled]
        if not eligible:
            waits = [s["cooldown"][a] for a in order if a not in self.disabled and a in s["cooldown"]]
            self.backoff(s, min(waits) if waits else 0)
            return self.finish(s, "cooldown_or_no_account", [])

        attempts = []
        for account in eligible:
            if self.desktop_paused():
                return self.finish(s, "pause_gate_wait", attempts)
            # Persist a minimum floor before starting a browser, even if the
            # process is interrupted before it can record the attempt result.
            s["next_attempt"] = self.now().timestamp() + self.policy["backoff_seconds"][0]
            self.save(s)
            self.event("login_started", alias=account["alias"])
            if self.desktop_status:
                self.desktop_status.publish("recovering")
            try:
                result = self.attempt(account, window, guid, probe)
            except Stop as exc:
                result = {"alias": account["alias"], "result": str(exc), "submissions": 0}
            attempts.append(result)
            reason = result["result"]
            if reason == "pause_gate_wait":
                return self.finish(s, reason, attempts)
            if reason == "schedule_changed":
                self.event(reason)
                s["next_attempt"] = 0
                return self.finish(s, reason, attempts)
            self.event(reason, kind="attempt_result", alias=account["alias"], submissions=result["submissions"])
            if not result["submissions"] and reason in {"wifi_status_unavailable", "wifi_changed_before_submit", "wifi_not_connected"}:
                # Windows can briefly lose the link state during association.
                # No account was submitted; recheck the link without auth backoff.
                s["link_recheck_streak"] = min(s.get("link_recheck_streak", 0) + 1, 2)
                retry_at = self.now().timestamp() + self.policy["join_retry_seconds"] if s["link_recheck_streak"] > 1 else 0
                s.update(next_attempt=retry_at, failures=0, observed=False)
                return self.finish(s, "wifi_recheck_pending", attempts)
            s["link_recheck_streak"] = 0
            if reason in {"browser_login_verified", "already_online"}:
                self.mark_online(s)
                if reason == "browser_login_verified":
                    if takeover or anchor:
                        previous = anchor or s["last_success"]
                        if previous and previous != account["alias"]:
                            self.event("backup_login_verified", kind="attempt_result", alias=account["alias"])
                    s["last_success"] = account["alias"]
                return self.finish(s, reason, attempts)
            if reason == "credential_rejected":
                self.disabled.add(account["alias"])
                continue
            # Stop the whole round on network-like failures. Diagnose once,
            # without treating a transport or DNS failure as a bad password.
            diagnostic = self.diagnose_dns(guid, reason)
            if diagnostic and s["outcome"] != diagnostic:
                self.event(diagnostic)
            self.backoff(s)
            return self.finish(s, diagnostic or reason, attempts)
        self.backoff(s)
        return self.finish(s, "no_accepted_account", attempts)

    def display_logs(self, selected, tail, follow):
        limits = self.cfg["logging"]
        tail = limits.get("monitor_tail", 20) if tail is None else tail
        poll = limits.get("monitor_poll_seconds", 1)
        repeat = limits.get("monitor_repeat_seconds", 60)
        if (type(tail) is not int or not 0 <= tail <= 500 or type(poll) is not int or not 1 <= poll <= 60
                or type(repeat) is not int or not 0 <= repeat <= 3600):
            raise Stop("invalid_log_monitor_options")
        s = self.state()
        try:
            last = self.path.stat().st_mtime
        except FileNotFoundError:
            last = 0
        code = safe_code(s["outcome"]) or "not_run"
        description = TEXT.get(code, ("system", code))[1]
        name = safe_code(s.get("last_success"))
        print(f"校园网守护｜{'当前允许自动登录' if self.window() else '当前不自动登录'}｜已配置 {len(self.accounts)} 个账号")
        print(f"最近状态：{description}；最近检查：{date_label(last, ZONE) or '尚未检查'}；上次成功别名：{name or '未记录'}")
        retry = s.get("next_attempt", 0)
        if type(retry) in (int, float) and retry > self.now().timestamp():
            print(f"最早可再试：{date_label(retry, ZONE)}")
        show_log(self.root / "campus.log", selected, tail, follow, ZONE, poll, repeat, limits["backups"])


def main():
    p = argparse.ArgumentParser(description="校园网自动维护：只登录和恢复，不主动下线。")
    p.add_argument("mode", choices=("status", "observe", "check", "tick", "watch", "logs", "schedule"))
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--rehearsal-state", type=Path, help="仅隔离回环演练")
    p.add_argument("--follow", action="store_true", help="logs 模式：持续跟踪")
    p.add_argument("--tail", type=int, help="logs 模式：最近匹配的事件条数")
    p.add_argument("--filter", choices=FILTERS, default="important", help="logs 模式：日志过滤")
    p.add_argument("--windows", nargs=7, metavar="WINDOW", help="schedule 模式：周一到周日；HH:MM-HH:MM 或 off")
    args = p.parse_args()
    if args.mode != "logs" and (args.follow or args.tail is not None or args.filter != "important"):
        p.error("日志选项只用于 logs")
    if args.windows is not None and args.mode != "schedule":
        p.error("--windows 只用于 schedule")
    try:
        ctl = Controller(read_config(args.config.resolve()), args.rehearsal_state)
        if args.mode == "logs":
            ctl.display_logs(args.filter, args.tail, args.follow)
        elif args.mode == "schedule":
            policy = (save_schedule(ctl.cfg, [None if item == "off" else item for item in args.windows])
                      if args.windows is not None else read_schedule(ctl.cfg)[0])
            print(json.dumps(policy, ensure_ascii=False))
        elif args.mode == "status":
            print(json.dumps(dict(ctl.state(), now=ctl.now().isoformat(), allowed=bool(ctl.window())),
                             ensure_ascii=False))
        elif args.mode == "observe":
            print(json.dumps(ctl.observe(), ensure_ascii=False))
        elif args.mode == "check":
            ctl.accounts = load_accounts(ctl.cfg, strict=True)
            if not ctl.accounts:
                raise Stop("credentials_missing")
            root = ctl.cfg["browser_root"]
            root.mkdir(parents=True, exist_ok=True)
            with single_instance(root):
                outcome = run(SimpleNamespace(mode="check", show=False, headless=True), ctl.portal,
                              ctl.cfg["browser_path"], root, {"documents": [], "login_submissions": 0})
            print(json.dumps({"outcome": outcome, "configured_accounts": len(ctl.accounts)}, ensure_ascii=False))
        else:
            if args.mode == "watch" and args.rehearsal_state and "desktop_status_path" not in ctl.cfg:
                raise Stop("rehearsal_watch_requires_desktop_status")
            with single_instance(ctl.root):
                if args.mode == "watch" and "desktop_status_path" in ctl.cfg:
                    ctl.state()  # Refuse a rehearsal/live state mismatch before publishing.
                    pause_seconds = ctl.cfg.get("desktop_rehearsal_pause_seconds", 1800) if args.rehearsal_state else 1800
                    if type(pause_seconds) is not int or not 1 <= pause_seconds <= 1800:
                        raise Stop("invalid_desktop_rehearsal_pause")
                    ctl.desktop_status = DesktopStatus(ctl.cfg["desktop_status_path"], bool(args.rehearsal_state),
                                                       ctl.root, ctl.cfg["logging"], ZONE, pause_seconds)
                    ctl.desktop_status.publish("starting")
                if args.mode == "watch":
                    ctl.event("watch_started")
                while True:
                    started = clock.monotonic()
                    try:
                        s = ctl.tick()
                    except Stop as exc:
                        s = ctl.finish(ctl.state(), str(exc), [])
                    if args.mode == "tick":
                        print(json.dumps(s, ensure_ascii=False))
                        break
                    clock.sleep(ctl.sleep_seconds(clock.monotonic() - started, s["outcome"]))
    except KeyboardInterrupt:
        return 0
    except Stop as exc:
        if args.mode == "watch" and str(exc) == "another_browser_login_running":
            # A foreground watcher may already own the lock during task setup.
            # Let the scheduler's watchdog retry later instead of reporting an
            # abnormal exit and asking Windows to restart immediately.
            print(json.dumps({"outcome": "watcher_already_running"}, ensure_ascii=False))
            return 0
        print(json.dumps({"outcome": str(exc)}, ensure_ascii=False))
        return 3
    except Exception as exc:
        print(json.dumps({"outcome": "maintenance_error_" + type(exc).__name__}))
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
