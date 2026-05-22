"""Logging setup for gcash."""

import logging

logger = logging.getLogger("gcash")


def setup_logging(level: str = "WARNING") -> None:
    """Configure the gcash logger with a standard format."""
    if not any(getattr(handler, "_gcash_handler", False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler._gcash_handler = True
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.WARNING))
