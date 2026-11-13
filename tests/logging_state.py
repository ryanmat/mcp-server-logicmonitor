# Description: Test helper that puts back the logging state configure_logging changes.
# Description: Restores the root and audit logger levels and removes the server's stderr handler.

import contextlib
import logging
from collections.abc import Iterator


@contextlib.contextmanager
def restored_logging() -> Iterator[None]:
    """Run the body, then restore the root and lm_mcp.audit levels and drop the stderr handler."""
    from lm_mcp.logging import STDERR_HANDLER_NAME

    root = logging.getLogger()
    audit = logging.getLogger("lm_mcp.audit")
    root_level, audit_level = root.level, audit.level
    try:
        yield
    finally:
        for handler in list(root.handlers):
            if handler.get_name() == STDERR_HANDLER_NAME:
                root.removeHandler(handler)
        root.setLevel(root_level)
        audit.setLevel(audit_level)
