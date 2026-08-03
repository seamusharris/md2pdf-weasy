"""Small exact-I/O primitives shared by compatibility boundaries."""

from __future__ import annotations

import os


def write_all(fd: int, value: bytes) -> None:
    """Write all bytes to an existing descriptor or fail explicitly."""
    remaining = memoryview(value)
    while remaining:
        written = os.write(fd, remaining)
        if written <= 0:
            raise OSError("write made no progress")
        remaining = remaining[written:]
