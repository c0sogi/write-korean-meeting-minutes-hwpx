from __future__ import annotations

import sys
from typing import TextIO


def _reconfigure(stream: TextIO) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")


def configure_utf8_output() -> None:
    """Emit machine-readable and Korean console output as UTF-8 on every OS."""
    _reconfigure(sys.stdout)
    _reconfigure(sys.stderr)
