from __future__ import annotations

import logging


def debug_suppressed(context: str, exc: Exception) -> None:
    try:
        logging.getLogger(__name__).debug("%s: %s", context, exc, exc_info=True)
    except Exception:
        return
