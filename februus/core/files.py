"""Files of a key: open one for reading, safely. Nothing is ever written
on a key."""

import os
import stat
from pathlib import Path


def open_regular(path: Path) -> int:
    """Open a file of a key read-only and return its descriptor (to close).

    O_NOFOLLOW: a symbolic link found on the key is never followed.
    Anything else than a regular file (device, pipe...) raises OSError.
    FR : ne jamais suivre un lien symbolique présent sur la clé.
    """
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise OSError(f"not a regular file: {path}")
    return fd
