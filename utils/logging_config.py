"""Centralised logging configuration for the ERP Chatbot.

Import and call `setup()` once at app startup. Every other module
uses `logging.getLogger(__name__)` and benefits from this config
automatically.
"""

import logging
import sys


def setup(level: int = logging.DEBUG) -> None:
    """Configure the root logger with a coloured, readable format."""

    # ANSI colour codes — degrade gracefully on terminals that don't support them
    RESET   = "\033[0m"
    GREY    = "\033[90m"
    CYAN    = "\033[96m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    RED     = "\033[91m"
    BOLD    = "\033[1m"

    LEVEL_COLOURS = {
        logging.DEBUG:    GREY,
        logging.INFO:     CYAN,
        logging.WARNING:  YELLOW,
        logging.ERROR:    RED,
        logging.CRITICAL: BOLD + RED,
    }

    class ColourFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            colour = LEVEL_COLOURS.get(record.levelno, RESET)
            level  = f"{colour}{record.levelname:<8}{RESET}"
            # Shorten module path: tools.sales_tools → sales_tools
            module = record.name.split(".")[-1]
            ts     = self.formatTime(record, "%H:%M:%S")
            msg    = record.getMessage()
            return f"{GREY}{ts}{RESET}  {level}  {GREEN}{module:<22}{RESET}  {msg}"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColourFormatter())

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers on Streamlit hot-reloads
    if not root.handlers:
        root.addHandler(handler)
    else:
        root.handlers.clear()
        root.addHandler(handler)

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "openai", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
