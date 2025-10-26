# log.py
import logging
import os
import sys


def setup_logger() -> logging.Logger:
    """Configure logging based on environment variables.

    LOG_FILE   -> file path for log output
    LOG_LEVEL  -> 0 (silent), 1 (info), 2 (debug). Default = 0.
    """
    log_file = os.environ.get("LOG_FILE")
    try:
        log_level = int(os.environ.get("LOG_LEVEL", "0"))
    except ValueError:
        log_level = 0  # fallback

    # Map custom levels to logging
    if log_level <= 0:
        level = logging.CRITICAL + 1  # effectively disables all logging
    elif log_level == 1:
        level = logging.INFO
    else:  # log_level >= 2
        level = logging.DEBUG

    logger = logging.getLogger("cli_logger")
    logger.setLevel(level)
    logger.handlers.clear()  # avoid duplicate handlers

    # If no LOG_FILE is set, disable logging
    if not log_file:
        return logger

    handler: logging.Handler  # <-- general type
    try:
        handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    except Exception as e:
        # If log file path is invalid, fallback to stderr
        handler = logging.StreamHandler(sys.stderr)
        logger.error(f"Invalid log file path: {e}")

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


# Create a module-level logger that others can import
logger = setup_logger()
