from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .paths import log_dir


def setup_logging(verbose_console: bool = False) -> logging.Logger:
    logger = logging.getLogger("djen_monitor")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)

    file_handler = RotatingFileHandler(
        log_dir() / "djen-monitor.log",
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(file_handler)

    if verbose_console:
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(console)
    return logger
