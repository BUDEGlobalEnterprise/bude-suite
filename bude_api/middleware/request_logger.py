"""Request logging middleware — Phase 1 placeholder.

In Phase 2, wire this into hooks.py via `before_request` / `after_request`.
"""

import logging

logger = logging.getLogger("bude_api")


def log_request(*args, **kwargs) -> None:
    pass


def log_response(*args, **kwargs) -> None:
    pass
