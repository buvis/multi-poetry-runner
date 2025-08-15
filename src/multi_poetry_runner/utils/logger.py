"""Logging utilities for MPR."""

import logging
import sys
from pathlib import Path
from rich.logging import RichHandler
from rich.console import Console


def setup_logging(level: int = logging.INFO, log_file: Path = None) -> None:
    """Set up logging configuration with Rich handler."""
    
    # Create logs directory if needed
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
    else:
        # Default log file location
        log_dir = Path.home() / ".mpr" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "mpr.log"
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Console handler with Rich
    console_handler = RichHandler(
        console=Console(stderr=True),
        show_time=False,
        show_path=False,
        rich_tracebacks=True
    )
    console_handler.setLevel(level)
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)
    
    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    
    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)
