"""
Centralized logging configuration for the Harmonic Pattern Trading System.

This module provides a consistent logging setup across all modules,
with proper formatting, handlers, and log levels.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """Custom formatter with color support for console output."""

    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors for console output."""
        # Add color to levelname
        if hasattr(sys.stderr, 'isatty') and sys.stderr.isatty():
            levelname = record.levelname
            if levelname in self.COLORS:
                record.levelname = f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"

        return super().format(record)


def setup_logging(
    log_level: int = logging.INFO,
    log_to_file: bool = True,
    log_dir: Optional[Path] = None,
    module_name: str = "harmonic_scanner"
) -> logging.Logger:
    """
    Set up logging configuration for the application.

    Args:
        log_level: Logging level (e.g., logging.INFO, logging.DEBUG)
        log_to_file: Whether to log to file in addition to console
        log_dir: Directory for log files (default: project_root/logs)
        module_name: Name of the module requesting logger

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(module_name)

    # Prevent duplicate handlers if setup_logging is called multiple times
    if logger.handlers:
        return logger

    logger.setLevel(log_level)
    logger.propagate = False

    # Console handler with colored output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # Use colored formatter for console
    console_formatter = ColoredFormatter(
        fmt='%(levelname)s - %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_to_file:
        if log_dir is None:
            # Default to logs/ directory in project root
            script_dir = Path(__file__).parent
            project_root = script_dir.parent
            log_dir = project_root / "logs"

        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create timestamped log file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = log_dir / f"{module_name}_{timestamp}.log"

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)  # File gets all messages

        # Detailed format for file logging
        file_formatter = logging.Formatter(
            fmt='%(asctime)s - %(levelname)s - %(name)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for the given module name.

    This is a convenience function that ensures consistent logger naming
    across the application.

    Args:
        name: Module name (typically __name__)

    Returns:
        Logger instance

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Pattern detected")
    """
    # Use the module name directly without setup to allow lazy initialization
    return logging.getLogger(name)


def configure_root_logger(
    log_level: int = logging.INFO,
    log_to_file: bool = True
) -> None:
    """
    Configure the root logger for the entire application.

    This should be called once at application startup.

    Args:
        log_level: Logging level for console output
        log_to_file: Whether to enable file logging
    """
    setup_logging(
        log_level=log_level,
        log_to_file=log_to_file,
        module_name="harmonic_scanner"
    )
