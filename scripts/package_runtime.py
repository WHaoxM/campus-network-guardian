"""Build a private, relocatable Python runtime from pinned upstream archives."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import stat
from urllib.request import urlopen
from zipfile import ZipFile


def _download(item):
    with urlopen(item["url"], timeout=60) as response:
        body = response.read(64 * 1024 * 1024 + 1)
    if sha256(body).hexdigest() != item["sha256"]:
        raise ValueError("Upstream checksum did not match: " + item["url"])
    return body


def bundled_files():
    lock = json.loads(Path(__file__).with_name("runtime-win-x64.json").read_text(encoding="utf-8"))
    with ThreadPoolExecutor(max_workers=4) as executor:
        artifacts = list(executor.map(_download, [lock["python"], *lock["wheels"]]))
    written = set()
    for index, artifact in enumerate(artifacts):
        with ZipFile(BytesIO(artifact)) as archive:
            for entry in archive.infolist():
                relative = PurePosixPath(entry.filename)
                if entry.is_dir():
                    continue
                if (relative.is_absolute() or ".." in relative.parts or ":" in entry.filename
                        or "\\" in entry.filename or stat.S_ISLNK(entry.external_attr >> 16)):
                    raise ValueError(f"Unexpected runtime archive member: {entry.filename}")
                if index and relative.parts[0].endswith(".data"):
                    # Runtime does not compile or link against wheel headers.
                    if len(relative.parts) > 2 and relative.parts[1] == "headers":
                        continue
                    raise ValueError(f"Wheel requires unsupported installation layout: {entry.filename}")
                prefix = "app/runtime/python" + ("/site-packages" if index else "")
                installed = f"{prefix}/{relative}"
                if installed.casefold() in written:
                    raise ValueError(f"Duplicate runtime member: {installed}")
                written.add(installed.casefold())
                payload = archive.read(entry)
                if not index and relative.name.endswith("._pth"):
                    # The embed distribution ignores environment/PATH. Allow
                    # its own libraries, wheels and this installed app only.
                    payload = b"python313.zip\n.\nsite-packages\n..\\..\n"
                yield installed, payload
