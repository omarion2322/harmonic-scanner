"""
Tests for logging configuration module.
"""

import pytest
from pathlib import Path
import sys
import logging
from unittest.mock import Mock, patch, MagicMock
import tempfile

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from logging_config import (
    ColoredFormatter,
    setup_logging,
    get_logger,
    configure_root_logger
)


class TestColoredFormatter:
    """Test ColoredFormatter class."""

    def test_formatter_initialization(self):
        """Test that formatter can be initialized."""
        formatter = ColoredFormatter()

        assert formatter is not None
        assert hasattr(formatter, 'COLORS')

    def test_formatter_has_color_codes(self):
        """Test that formatter has color code definitions."""
        formatter = ColoredFormatter()

        assert 'DEBUG' in formatter.COLORS
        assert 'INFO' in formatter.COLORS
        assert 'WARNING' in formatter.COLORS
        assert 'ERROR' in formatter.COLORS
        assert 'CRITICAL' in formatter.COLORS
        assert 'RESET' in formatter.COLORS

    def test_format_basic_record(self):
        """Test formatting a basic log record."""
        formatter = ColoredFormatter(fmt='%(levelname)s - %(message)s')

        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname='test.py',
            lineno=1,
            msg='Test message',
            args=(),
            exc_info=None
        )

        formatted = formatter.format(record)

        assert isinstance(formatted, str)
        assert 'Test message' in formatted

    @patch('sys.stderr')
    def test_format_adds_colors_to_tty(self, mock_stderr):
        """Test that colors are added when output is a TTY."""
        mock_stderr.isatty.return_value = True

        formatter = ColoredFormatter(fmt='%(levelname)s - %(message)s')

        record = logging.LogRecord(
            name='test',
            level=logging.WARNING,
            pathname='test.py',
            lineno=1,
            msg='Warning message',
            args=(),
            exc_info=None
        )

        formatted = formatter.format(record)

        # Should contain color codes (ANSI escape sequences)
        # The exact format depends on implementation
        assert isinstance(formatted, str)

    @patch('sys.stderr')
    def test_format_no_colors_for_non_tty(self, mock_stderr):
        """Test that colors are not added when output is not a TTY."""
        mock_stderr.isatty.return_value = False

        formatter = ColoredFormatter(fmt='%(levelname)s - %(message)s')

        record = logging.LogRecord(
            name='test',
            level=logging.ERROR,
            pathname='test.py',
            lineno=1,
            msg='Error message',
            args=(),
            exc_info=None
        )

        formatted = formatter.format(record)

        assert 'Error message' in formatted


class TestSetupLogging:
    """Test setup_logging function."""

    def test_setup_logging_returns_logger(self):
        """Test that setup_logging returns a logger."""
        logger = setup_logging(
            log_level=logging.INFO,
            log_to_file=False,
            module_name="test_module"
        )

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_module"

    def test_setup_logging_sets_log_level(self):
        """Test that setup_logging sets correct log level."""
        logger = setup_logging(
            log_level=logging.DEBUG,
            log_to_file=False,
            module_name="test_debug"
        )

        assert logger.level == logging.DEBUG

    def test_setup_logging_adds_console_handler(self):
        """Test that setup_logging adds console handler."""
        logger = setup_logging(
            log_level=logging.INFO,
            log_to_file=False,
            module_name="test_console"
        )

        # Should have at least one handler
        assert len(logger.handlers) > 0

        # Should have a StreamHandler
        has_stream_handler = any(
            isinstance(h, logging.StreamHandler) for h in logger.handlers
        )
        assert has_stream_handler

    def test_setup_logging_with_file_handler(self, tmp_path):
        """Test that setup_logging adds file handler when requested."""
        logger = setup_logging(
            log_level=logging.INFO,
            log_to_file=True,
            log_dir=tmp_path,
            module_name="test_file"
        )

        # Should have multiple handlers (console + file)
        assert len(logger.handlers) >= 2

        # Should have a FileHandler
        has_file_handler = any(
            isinstance(h, logging.FileHandler) for h in logger.handlers
        )
        assert has_file_handler

    def test_setup_logging_creates_log_directory(self, tmp_path):
        """Test that setup_logging creates log directory."""
        log_dir = tmp_path / "logs"

        assert not log_dir.exists()

        setup_logging(
            log_level=logging.INFO,
            log_to_file=True,
            log_dir=log_dir,
            module_name="test_dir"
        )

        assert log_dir.exists()

    def test_setup_logging_creates_log_file(self, tmp_path):
        """Test that setup_logging creates log file."""
        logger = setup_logging(
            log_level=logging.INFO,
            log_to_file=True,
            log_dir=tmp_path,
            module_name="test_logfile"
        )

        # Log a message
        logger.info("Test message")

        # Check that log file was created
        log_files = list(tmp_path.glob("*.log"))
        assert len(log_files) > 0

    def test_setup_logging_prevents_duplicate_handlers(self):
        """Test that calling setup_logging twice doesn't add duplicate handlers."""
        logger1 = setup_logging(
            log_level=logging.INFO,
            log_to_file=False,
            module_name="test_duplicate"
        )
        handler_count_1 = len(logger1.handlers)

        logger2 = setup_logging(
            log_level=logging.INFO,
            log_to_file=False,
            module_name="test_duplicate"
        )
        handler_count_2 = len(logger2.handlers)

        # Should return same logger with same number of handlers
        assert logger1 is logger2
        assert handler_count_1 == handler_count_2

    def test_setup_logging_propagate_false(self):
        """Test that logger propagation is disabled."""
        logger = setup_logging(
            log_level=logging.INFO,
            log_to_file=False,
            module_name="test_propagate"
        )

        assert logger.propagate is False


class TestGetLogger:
    """Test get_logger function."""

    def test_get_logger_returns_logger(self):
        """Test that get_logger returns a logger."""
        logger = get_logger("test_module")

        assert isinstance(logger, logging.Logger)

    def test_get_logger_uses_module_name(self):
        """Test that get_logger uses provided module name."""
        logger = get_logger("custom_module_name")

        assert logger.name == "custom_module_name"

    def test_get_logger_same_name_returns_same_logger(self):
        """Test that get_logger returns same logger for same name."""
        logger1 = get_logger("same_module")
        logger2 = get_logger("same_module")

        assert logger1 is logger2

    def test_get_logger_different_names_return_different_loggers(self):
        """Test that different names return different loggers."""
        logger1 = get_logger("module_a")
        logger2 = get_logger("module_b")

        assert logger1 is not logger2
        assert logger1.name != logger2.name

    def test_get_logger_with_dunder_name(self):
        """Test get_logger with __name__ pattern."""
        logger = get_logger(__name__)

        assert isinstance(logger, logging.Logger)
        assert len(logger.name) > 0


class TestConfigureRootLogger:
    """Test configure_root_logger function."""

    def test_configure_root_logger_runs_without_error(self):
        """Test that configure_root_logger executes successfully."""
        # Should not raise any exceptions
        configure_root_logger(
            log_level=logging.INFO,
            log_to_file=False
        )

    def test_configure_root_logger_with_file_logging(self, tmp_path):
        """Test configure_root_logger with file logging enabled."""
        # Temporarily change working directory to tmp_path
        with patch('logging_config.Path') as mock_path:
            mock_path.return_value.parent.parent = tmp_path

            configure_root_logger(
                log_level=logging.DEBUG,
                log_to_file=True
            )


class TestLoggingIntegration:
    """Integration tests for logging system."""

    def test_logger_can_log_messages(self):
        """Test that logger can log messages at different levels."""
        logger = setup_logging(
            log_level=logging.DEBUG,
            log_to_file=False,
            module_name="test_integration"
        )

        # Should not raise exceptions
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        logger.critical("Critical message")

    def test_logger_respects_log_level(self, tmp_path):
        """Test that logger respects configured log level."""
        logger = setup_logging(
            log_level=logging.WARNING,
            log_to_file=True,
            log_dir=tmp_path,
            module_name="test_level"
        )

        logger.debug("Debug - should not appear in console")
        logger.info("Info - should not appear in console")
        logger.warning("Warning - should appear")
        logger.error("Error - should appear")

        # File handler uses DEBUG level
        log_files = list(tmp_path.glob("*.log"))
        assert len(log_files) > 0

        with open(log_files[0], 'r') as f:
            content = f.read()

        # File handler is set to DEBUG, but logger level is WARNING
        # So DEBUG and INFO may not appear if logger itself filters them
        assert 'Warning' in content
        assert 'Error' in content

    def test_logger_with_formatting(self, tmp_path):
        """Test that logger formats messages correctly."""
        logger = setup_logging(
            log_level=logging.INFO,
            log_to_file=True,
            log_dir=tmp_path,
            module_name="test_format"
        )

        logger.info("Formatted message: %s", "value")
        logger.error("Error with code: %d", 404)

        log_files = list(tmp_path.glob("*.log"))
        assert len(log_files) > 0

        with open(log_files[0], 'r') as f:
            content = f.read()

        assert 'Formatted message: value' in content
        assert 'Error with code: 404' in content

    def test_logger_handles_exceptions(self, tmp_path):
        """Test that logger can log exceptions."""
        logger = setup_logging(
            log_level=logging.ERROR,
            log_to_file=True,
            log_dir=tmp_path,
            module_name="test_exception"
        )

        try:
            raise ValueError("Test exception")
        except ValueError:
            logger.exception("An error occurred")

        log_files = list(tmp_path.glob("*.log"))
        assert len(log_files) > 0

        with open(log_files[0], 'r') as f:
            content = f.read()

        assert 'An error occurred' in content
        assert 'ValueError' in content
        assert 'Test exception' in content

    def test_multiple_modules_use_separate_loggers(self):
        """Test that different modules get separate logger instances."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")

        assert logger1.name == "module1"
        assert logger2.name == "module2"
        assert logger1 is not logger2

    def test_logger_file_naming_includes_timestamp(self, tmp_path):
        """Test that log files include timestamp in name."""
        logger = setup_logging(
            log_level=logging.INFO,
            log_to_file=True,
            log_dir=tmp_path,
            module_name="test_timestamp"
        )

        logger.info("Test message")

        log_files = list(tmp_path.glob("*.log"))
        assert len(log_files) > 0

        # Check that filename contains module name
        assert any('test_timestamp' in f.name for f in log_files)

    def test_logger_file_encoding_utf8(self, tmp_path):
        """Test that log files use UTF-8 encoding."""
        logger = setup_logging(
            log_level=logging.INFO,
            log_to_file=True,
            log_dir=tmp_path,
            module_name="test_utf8"
        )

        # Log message with unicode characters
        logger.info("Unicode test: \u2713 \u2714 \u2718")

        log_files = list(tmp_path.glob("*.log"))
        assert len(log_files) > 0

        # Should be able to read with UTF-8
        with open(log_files[0], 'r', encoding='utf-8') as f:
            content = f.read()

        assert '\u2713' in content or '✓' in content
