"""Task-local nmcli/ip executables for the Linux end-to-end rehearsal."""
import json
from pathlib import Path
import sys

path = Path(sys.argv[0])
network = json.loads(path.with_name("network.json").read_text(encoding="utf-8"))
args = sys.argv[1:]
nic = network["interface"]
profile = network["profile"]
if path.name == "nmcli":
    if args[-2:] == ["device", "status"]:
        print(f'{nic}:wifi:{"connected" if network["connected"] else "disconnected"}')
        if network["other_wifi"]:
            print(f'{network["other_wifi_interface"]}:wifi:connecting')
    elif args[-3:] == ["connection", "show", "--active"]:
        if network["connected"]:
            print(f"{profile}:802-11-wireless:{nic}")
    elif args[-4:] == ["connection", "show", "uuid", profile]:
        print(network["ssid"])
    elif args[-3:] == [nic, "--rescan", "no"]:
        print(network["ssid"])
    elif args == ["--wait", "8", "connection", "up", "uuid", profile, "ifname", nic]:
        with path.with_name("joins").open("a", encoding="utf-8") as file:
            file.write(profile + "\n")
    else:
        raise SystemExit(4)
elif args == ["-j", "-4", "address", "show", "dev", nic]:
    print(json.dumps([{"addr_info": [{"scope": "global", "local": network["source"]}]}]))
elif args[2:] == ["route", "show", "table", "all", "default"]:
    routes = [{"dev": network["other_interface"]}] if network["default_route"] and args[1] == "-6" else []
    print(json.dumps(routes))
elif args[2:4] == ["route", "get"]:
    print(json.dumps([{"dev": network["other_interface"] if network["wrong_portal_route"] else nic,
                       "prefsrc": network["source"]}]))
else:
    raise SystemExit(4)
