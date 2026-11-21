"""NetworkManager adapter. Only activate an explicitly chosen saved SUSE profile."""
from ipaddress import IPv4Address
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit
from uuid import UUID

from campus_portable import Stop


INTERFACE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,14}")


class LinuxWifi:
    def __init__(self, settings, ssid):
        self.interface = settings.get("interface", "")
        self.ssid = ssid
        self.profile = settings.get("profile_uuid", "")
        self.nmcli = settings.get("nmcli", "")
        self.ip = settings.get("ip", "")
        if (settings.get("backend") != "networkmanager" or not INTERFACE.fullmatch(self.interface)
                or not all(Path(command).is_absolute() for command in (self.nmcli, self.ip))):
            raise Stop("linux_wifi_configuration_required")
        if self.profile:
            try:
                if str(UUID(self.profile)) != self.profile:
                    raise ValueError()
            except (ValueError, TypeError, AttributeError):
                raise Stop("linux_saved_profile_invalid") from None

    def command(self, executable, *args, timeout=6):
        try:
            return subprocess.run(
                [executable, *args], stdin=subprocess.DEVNULL, capture_output=True,
                encoding="utf-8", errors="strict", check=True, timeout=timeout,
                env=dict(os.environ, LC_ALL="C", LANG="C"),
            ).stdout.rstrip("\r\n")
        except (OSError, subprocess.SubprocessError, UnicodeError):
            raise Stop("wifi_status_unavailable") from None

    def nm(self, fields, *args):
        return self.command(self.nmcli, "--colors", "no", "--terse", "--escape", "no",
                            "--fields", fields, *args)

    def saved_ssid(self, profile):
        try:
            if str(UUID(profile)) != profile:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise Stop("wifi_status_unavailable") from None
        return self.command(self.nmcli, "--get-values", "802-11-wireless.ssid", "--escape", "no",
                            "connection", "show", "uuid", profile)

    def entries(self):
        devices = self.nm("DEVICE,TYPE,STATE", "device", "status")
        active = self.nm("UUID,TYPE,DEVICE", "connection", "show", "--active")
        links = []
        for line in devices.splitlines():
            fields = line.split(":", 2)
            if len(fields) != 3 or fields[1] not in ("wifi", "802-11-wireless"):
                continue
            name, _, state = fields
            if not INTERFACE.fullmatch(name):
                raise Stop("wifi_status_unavailable")
            profiles = [p[0] for raw in active.splitlines()
                        if len(p := raw.split(":")) == 3 and p[2] == name
                        and p[1] in ("wifi", "802-11-wireless")]
            if name == self.interface and state in {"unmanaged", "unavailable", "unknown"}:
                raise Stop("linux_wifi_unmanaged")
            if state == "disconnected" and not profiles:
                if name == self.interface:
                    links.append({"guid": name, "ssid": None})
                continue
            if state == "connected" and len(profiles) == 1:
                # Profile labels are not SSIDs. Read the wireless SSID by UUID.
                ssid = self.saved_ssid(profiles[0])
                allowed = (name == self.interface and ssid == self.ssid
                           and (not self.profile or profiles[0] == self.profile))
                links.append({"guid": name, "ssid": self.ssid if allowed else "other"})
            else:
                # Transitional or ambiguous links cannot be disconnected/replaced by us.
                links.append({"guid": name, "ssid": "other"})
        if not any(link["guid"] == self.interface for link in links):
            raise Stop("linux_wifi_unmanaged")
        return links

    def ip_json(self, *args):
        try:
            data = json.loads(self.command(self.ip, "-j", *args))
            if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
                raise ValueError()
            return data
        except (ValueError, TypeError):
            raise Stop("wifi_status_unavailable") from None

    def source(self, interface):
        if interface != self.interface:
            return None
        try:
            entries = self.ip_json("-4", "address", "show", "dev", interface)
            addresses = set()
            for row in entries:
                for info in row.get("addr_info", []):
                    if info.get("scope") != "global" or info.get("preferred_life_time") == 0 or info.get("deprecated"):
                        continue
                    ip = IPv4Address(info["local"])
                    if not (ip.is_loopback or ip.is_link_local or ip.is_unspecified):
                        addresses.add(str(ip))
            return next(iter(addresses)) if len(addresses) == 1 else None
        except (Stop, KeyError, ValueError, TypeError):
            return None

    def require_portal_route(self, url):
        try:
            address = str(IPv4Address(urlsplit(url).hostname))
            routes = self.ip_json("-4", "route", "get", address)
        except (Stop, ValueError):
            raise Stop("linux_portal_route_mismatch") from None
        source = self.source(self.interface)
        if (len(routes) != 1 or not source or routes[0].get("dev") != self.interface
                or routes[0].get("prefsrc", routes[0].get("src")) != source):
            raise Stop("linux_portal_route_mismatch")

    def visible(self):
        try:
            cached = self.nm("SSID", "device", "wifi", "list", "ifname", self.interface, "--rescan", "no")
        except Stop:
            return None
        return self.ssid in cached.splitlines() if cached else None

    def connect_saved(self, guard):
        if not self.profile:
            return "linux_saved_profile_required"
        try:
            if self.saved_ssid(self.profile) != self.ssid:
                return "linux_saved_profile_invalid"
            if self.entries() != [{"guid": self.interface, "ssid": None}]:
                return "wifi_join_deferred"
            for family in ("-4", "-6"):
                for route in self.ip_json(family, "route", "show", "table", "all", "default"):
                    if route.get("dev") != self.interface:
                        return "linux_other_route_present"
            guard()
            self.command(self.nmcli, "--wait", "8", "connection", "up", "uuid", self.profile,
                         "ifname", self.interface, timeout=10)
            return "wifi_join_requested"
        except Stop as exc:
            if str(exc) != "wifi_status_unavailable":
                raise
            return "wifi_join_failed"
