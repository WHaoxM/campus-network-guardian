"""Bundle the committed public source, Windows publish output and upstream notices."""
from argparse import ArgumentParser
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile


def git(root, *args):
    return subprocess.check_output(("git", "-C", str(root), *args))


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.version):
        parser.error("version must be a plain x.y.z")
    root = Path(__file__).resolve().parents[1]
    if Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve() != root:
        raise SystemExit("Run from the standalone public repository.")
    if git(root, "status", "--porcelain"):
        raise SystemExit("Commit the exact public source before building its release archive.")

    build = root / "runtime/desktop"
    exe = build / "CampusGuardian.exe"
    if not exe.is_file():
        raise SystemExit("Run build_desktop.ps1 before packaging.")
    metadata = json.loads((build / "CampusGuardian.deps.json").read_text(encoding="utf-8"))
    manifests = {
        "runtimepack.microsoft.netcore.app.runtime.win-x64": ("dotnet-runtime", "LICENSE.TXT"),
        "runtimepack.microsoft.windowsdesktop.app.runtime.win-x64": ("dotnet-windows-desktop", "LICENSE"),
        "microsoft.web.webview2": ("webview2-sdk", "LICENSE.txt"),
    }
    versions = {name.lower(): version for name, version in
                (key.split("/", 1) for key in metadata["libraries"])}
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
            notices[f"licenses/{label}/{filename}"] = file

    release = root / "runtime/release"
    release.mkdir(parents=True, exist_ok=True)
    name = f"CampusNetworkGuardian-{args.version}-win-x64"
    output = release / f"{name}.zip"
    pending = output.with_suffix(".tmp")
    with ZipFile(io.BytesIO(git(root, "archive", "--format=zip", "HEAD"))) as source, \
            ZipFile(pending, "w", compression=ZIP_DEFLATED, compresslevel=6) as dest:
        for entry in source.infolist():
            if entry.is_dir():
                continue
            path = PurePosixPath(entry.filename)
            if any(p in {"runtime", "captures", ".venv"} for p in path.parts) or path.name in {
                ".env", "browser_python.txt", "browser_login.toml", "accounts.private.json", "accounts.private.tmp",
            }:
                raise SystemExit(f"Refusing to package non-public configuration: {path}")
            dest.writestr(f"{name}/{entry.filename}", source.read(entry))
        for file in sorted(build.rglob("*")):
            if file.is_file() and file.suffix.lower() not in {".pdb", ".xml"}:
                dest.write(file, f"{name}/runtime/desktop/{file.relative_to(build).as_posix()}")
        for filename, file in notices.items():
            dest.write(file, f"{name}/{filename}")
    pending.replace(output)
    with output.open("rb") as fd:
        digest = hashlib.file_digest(fd, "sha256").hexdigest()
    check = output.with_suffix(".zip.sha256")
    check.write_text(f"{digest}  {output.name}\n", encoding="ascii")
    print(output.relative_to(root).as_posix())
    print(check.relative_to(root).as_posix())


if __name__ == "__main__":
    main()
