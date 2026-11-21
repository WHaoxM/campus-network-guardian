"""Small runtime differences shared by the Windows and Linux entrypoints."""
import os

try:
    import tomllib
except ImportError:  # Ubuntu 22.04 ships Python 3.10.
    import tomli as tomllib

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class Stop(Exception):
    pass


def acquire_lock(handle):
    handle.seek(0)
    if os.name == "nt":
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)


def release_lock(handle):
    handle.seek(0)
    if os.name == "nt":
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(handle, fcntl.LOCK_UN)
