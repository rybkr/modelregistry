"""Logging configuration for the Model Registry.

This module provides a configurable logger that can be set up via environment
variables. It supports file-based logging, console logging, and configurable
log levels. The logger is designed to be silent by default and can be enabled
for debugging or production monitoring.

Environment Variables:
    LOG_FILE: Path to log file (if not set, logging is disabled)
    LOG_LEVEL: Logging level (0=silent, 1=info, 2=debug, default=0)
"""

import logging
import os
import sys


def setup_logger() -> logging.Logger:
    """Configure logging based on environment variables.

    Creates and configures a logger instance based on LOG_FILE and LOG_LEVEL
    environment variables. If LOG_FILE is not set, logging is effectively
    disabled. The logger uses a standard format with timestamps and log levels.

    Environment Variables:
        LOG_FILE: Path to log file (optional, disables logging if not set)
        LOG_LEVEL: Logging verbosity (0=silent, 1=info, 2=debug, default=0)

    Returns:
        logging.Logger: Configured logger instance named "cli_logger"
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
