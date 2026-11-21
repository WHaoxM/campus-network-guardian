"""Bundle only the committed runtime inputs, Windows build and upstream notices."""
from argparse import ArgumentParser
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile

from package_runtime import bundled_files

PUBLIC_FILES = {
    "suse.cmd": "suse.cmd", "README.md": "README.md", "LICENSE": "LICENSE",
    "docs/media/icon.png": "app/media/icon.png",
    "docs/media/desktop-flow.gif": "app/media/desktop-flow.gif",
    "app/desktop/ui/vendor/glassy-liquid/LICENSE": "app/licenses/glassy-liquid/LICENSE.txt",
    "app/desktop/ui/icons/lucide/LICENSE": "app/licenses/lucide/LICENSE.txt",
    "app/desktop/ui/vendor/webawesome/LICENSE": "app/licenses/webawesome-spinner/LICENSE.txt",
    **{f"app/{name}": f"app/{name}" for name in (
        "setup.ps1", "scripts/suse.ps1", "scripts/deploy.ps1", "requirements.txt",
        "browser_login.py", "campus_maintenance.py", "campus_accounts.py", "campus_status.py", "campus_log.py", "campus_schedule.py",
        "network_diagnostics.ps1", "enable_guardian.ps1", "install_campus_maintenance.ps1", "install_desktop.ps1",
        "config/browser_login.example.toml", "config/campus.toml",
    )},
}
SOURCE_REPO = "https://github.com/WHaoxM/campus-network-guardian"


def portable_readme(data):
    text = data.decode("utf-8")
    for name in ("docs/media/icon.png", "docs/media/desktop-flow.gif"):
        text = text.replace(name, PUBLIC_FILES[name])
    for name in ("docs/INSTALL.md", "docs/DEVELOPMENT.md", "SECURITY.md"):
        text = text.replace(f"({name}", f"({SOURCE_REPO}/blob/main/{name}")
    return text.encode("utf-8")


def git(root, *args):
    return subprocess.check_output(("git", "-C", str(root), *args))


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output-dir", type=Path, help="Optional output directory under runtime/.")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.version):
        parser.error("version must be a plain x.y.z")
    root = Path(__file__).resolve().parents[1]
    if Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve() != root:
        raise SystemExit("Run from the standalone public repository.")
    if git(root, "status", "--porcelain"):
        raise SystemExit("Commit the exact public source before building its release archive.")

    build = root / "app/runtime/desktop"
    exe = build / "CampusGuardian.exe"
    if not exe.is_file():
        raise SystemExit("Run scripts/build_desktop.ps1 before packaging.")
    metadata = json.loads((build / "CampusGuardian.deps.json").read_text(encoding="utf-8"))
    manifests = {
        "runtimepack.microsoft.netcore.app.runtime.win-x64": ("dotnet-runtime", "LICENSE.TXT"),
        "runtimepack.microsoft.windowsdesktop.app.runtime.win-x64": ("dotnet-windows-desktop", "LICENSE"),
        "microsoft.web.webview2": ("webview2-sdk", "LICENSE.txt"),
    }
    versions = {name.lower(): version for name, version in
                (key.split("/", 1) for key in metadata["libraries"])}
    if versions.get("campusguardian") != args.version:
        raise SystemExit("Desktop build version differs from the requested package version.")
    packages = root / "runtime/desktop-build/packages"
    notices = {}
    for key, (label, primary) in manifests.items():
        root_package = packages / key.removeprefix("runtimepack.") / versions[key]
        required = [primary]
        if label == "dotnet-runtime":
            required.append("THIRD-PARTY-NOTICES.TXT")
        for filename in required:
            file = root_package / filename
            if not file.is_file():
                raise SystemExit(f"Missing {label} redistribution notice: {filename}")
            notices[f"app/licenses/{label}/{filename}"] = file

    release = (root / (args.output_dir or "runtime/release")).resolve()
    if not release.is_relative_to(root / "runtime"):
        raise SystemExit("Zip output must stay under the repository's runtime directory.")
    release.mkdir(parents=True, exist_ok=True)
    name = f"CampusNetworkGuardian-{args.version}-win-x64"
    output = release / f"{name}.zip"
    pending = output.with_suffix(".tmp")
    with ZipFile(io.BytesIO(git(root, "archive", "--format=zip", "HEAD", "--", *PUBLIC_FILES))) as source, \
            ZipFile(pending, "w", compression=ZIP_DEFLATED, compresslevel=6) as dest:
        fingerprint = {}

        def add(target, data):
            if target in fingerprint:
                raise SystemExit(f"Duplicate package file: {target}")
            dest.writestr(f"{name}/{target}", data)
            fingerprint[target] = hashlib.sha256(data).hexdigest()

        if {e.filename for e in source.infolist() if not e.is_dir()} != PUBLIC_FILES.keys():
            raise SystemExit("Committed runtime archive does not match its allowlist.")
        for original, target in PUBLIC_FILES.items():
            data = source.read(original)
            add(target, portable_readme(data) if original == "README.md" else data)
        for file in sorted(build.rglob("*")):
            if file.is_file() and file.suffix.lower() not in {".pdb", ".xml"}:
                relative = PurePosixPath(file.relative_to(build).as_posix())
                is_icon = relative == PurePosixPath("ui/media/campus-guardian.ico") or (
                    relative.parent == PurePosixPath("ui/icons/lucide") and relative.suffix == ".svg"
                )
                if not is_icon and relative.suffix.lower() not in {".dll", ".exe", ".json", ".html", ".js", ".css", ".dat", ".bin"}:
                    raise SystemExit(f"Unexpected file in desktop build: {relative}")
                if relative.suffix.lower() == ".json" and relative.name not in {
                    "desktop.json", "CampusGuardian.deps.json", "CampusGuardian.runtimeconfig.json",
                }:
                    raise SystemExit(f"Unexpected desktop configuration: {relative}")
                add(f"app/runtime/desktop/{relative}", file.read_bytes())
        for filename, file in notices.items():
            add(filename, file.read_bytes())
        for target, data in bundled_files():
            add(target, data)
        dest.writestr(f"{name}/install-manifest.json", json.dumps(
            {"schema": 1, "product": "SUSE.CampusNetworkGuardian", "version": args.version, "files": fingerprint},
            sort_keys=True, separators=(",", ":"),
        ))
    pending.replace(output)
    with output.open("rb") as fd:
        digest = hashlib.file_digest(fd, "sha256").hexdigest()
    print(output.relative_to(root).as_posix())
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
