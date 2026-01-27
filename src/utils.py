"""
Utility classes to reduce code duplication and improve maintainability.

This module provides centralized utilities for:
- Configuration access (ConfigHelper)
- Path management (PathManager)
- Pattern and reaction formatting (FormattingUtils)
- Ticker list management (TickerManager)

Note: Uses pathlib.Path exclusively for all path operations.
"""

from pathlib import Path
from datetime import datetime
from typing import List, Optional, Any, TYPE_CHECKING
from types import ModuleType

from logging_config import get_logger

if TYPE_CHECKING:
    from pattern_detector import HarmonicPattern
    from reaction_detector import ReactionData

logger = get_logger(__name__)


class ConfigHelper:
    """
    Helper class for safe configuration access with defaults.

    Eliminates the need for repeated 'hasattr' checks throughout the codebase.
    Provides type-safe accessors for common configuration value types.
    """

    def __init__(self, config_module: ModuleType) -> None:
        """
        Initialize ConfigHelper with a configuration module.

        Args:
            config_module: The config module (typically imported as 'import config')
        """
        self.config = config_module

    def get(self, key: str, default: Any = None) -> Any:
        """
        Safely get a configuration value with a default fallback.

        Args:
            key: Configuration key name
            default: Default value if key doesn't exist

        Returns:
            Configuration value or default

        Example:
            >>> config_helper = ConfigHelper(config)
            >>> verbose = config_helper.get('VERBOSE_REPORTS', False)
        """
        if not hasattr(self.config, key):
            return default

        value = getattr(self.config, key)
        # Return default if value is explicitly None
        return default if value is None else value

    def get_bool(self, key: str, default: bool = False) -> bool:
        """
        Get a boolean configuration value.

        Args:
            key: Configuration key name
            default: Default value if key doesn't exist

        Returns:
            Boolean value
        """
        value = self.get(key, default)
        return bool(value) if value is not None else default

    def get_int(self, key: str, default: int = 0) -> int:
        """
        Get an integer configuration value.

        Args:
            key: Configuration key name
            default: Default value if key doesn't exist

        Returns:
            Integer value
        """
        value = self.get(key, default)
        try:
            return int(value) if value is not None else default
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to convert config key '{key}' to int: {e}. Using default: {default}")
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """
        Get a float configuration value.

        Args:
            key: Configuration key name
            default: Default value if key doesn't exist

        Returns:
            Float value
        """
        value = self.get(key, default)
        try:
            return float(value) if value is not None else default
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to convert config key '{key}' to float: {e}. Using default: {default}")
            return default


class PathManager:
    """
    Centralized path management for reports, charts, and other output files.

    Eliminates duplicate path building logic throughout the codebase.
    """

    def __init__(self, project_root: Optional[Path] = None) -> None:
        """
        Initialize PathManager.

        Args:
            project_root: Project root directory. If None, auto-detects from src/ directory.
        """
        if project_root is None:
            # Auto-detect project root (one level up from src/) using pathlib
            script_path = Path(__file__).resolve()
            self.project_root = script_path.parent.parent
        else:
            self.project_root = Path(project_root)

        logger.debug(f"PathManager initialized with project_root: {self.project_root}")

    def get_report_dir(
        self,
        date: Optional[str] = None,
        interval: str = '1d',
        asset_type: str = 'stocks'
    ) -> Path:
        """
        Get the report directory path for a given date and interval.

        Args:
            date: Date string in 'YYYY-MM-DD' format. Defaults to today.
            interval: Data interval (e.g., '1d', '1wk', '1mo')
            asset_type: Asset type - 'stocks' or 'crypto' (determines base directory)

        Returns:
            Path to report directory

        Example:
            >>> pm = PathManager()
            >>> report_dir = pm.get_report_dir(interval='1wk')
            >>> # Returns: /path/to/project/reports/2024-01-15/1wk/
            >>> report_dir = pm.get_report_dir(interval='1wk', asset_type='crypto')
            >>> # Returns: /path/to/project/crypto_reports/2024-01-15/1wk/
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        base_dir = "crypto_reports" if asset_type == 'crypto' else "reports"
        report_dir = self.project_root / base_dir / date / interval
        report_dir.mkdir(parents=True, exist_ok=True)

        return report_dir

    def get_chart_dir(
        self,
        date: Optional[str] = None,
        interval: str = '1d',
        asset_type: str = 'stocks'
    ) -> Path:
        """
        Get the chart directory path for a given date and interval.

        Args:
            date: Date string in 'YYYY-MM-DD' format. Defaults to today.
            interval: Data interval (e.g., '1d', '1wk', '1mo')
            asset_type: Asset type - 'stocks' or 'crypto' (determines base directory)

        Returns:
            Path to chart directory

        Example:
            >>> pm = PathManager()
            >>> chart_dir = pm.get_chart_dir(interval='1wk')
            >>> # Returns: /path/to/project/reports/2024-01-15/1wk/charts/
        """
        chart_dir = self.get_report_dir(date, interval, asset_type) / "charts"
        chart_dir.mkdir(parents=True, exist_ok=True)
        return chart_dir

    def get_tracking_dir(self, subdir: str = "pattern_tracking") -> Path:
        """
        Get the pattern tracking directory path.

        Args:
            subdir: Subdirectory name (default: "pattern_tracking")

        Returns:
            Path to tracking directory
        """
        tracking_dir = self.project_root / subdir
        tracking_dir.mkdir(parents=True, exist_ok=True)
        return tracking_dir

    def get_report_path(
        self,
        date: Optional[str] = None,
        interval: str = '1d',
        verbose: bool = False,
        asset_type: str = 'stocks'
    ) -> Path:
        """
        Get the full path for a report file.

        Args:
            date: Date string in 'YYYY-MM-DD' format. Defaults to today.
            interval: Data interval (e.g., '1d', '1wk', '1mo')
            verbose: Whether this is a verbose report
            asset_type: Asset type - 'stocks' or 'crypto' (determines base directory)

        Returns:
            Path to report file
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        report_dir = self.get_report_dir(date, interval, asset_type)
        suffix = "_verbose" if verbose else ""
        filename = f"harmonic_report_{date}_{interval}{suffix}.txt"
        return report_dir / filename


class FormattingUtils:
    """
    Utilities for formatting pattern and reaction information.

    Eliminates duplicate formatting logic for ratios and reactions.
    """

    @staticmethod
    def format_pattern_ratios(pattern: 'HarmonicPattern') -> str:
        """
        Format pattern ratios in a consistent way.

        Args:
            pattern: HarmonicPattern object with ratio attributes

        Returns:
            Formatted ratio string

        Example:
            >>> ratios = FormattingUtils.format_pattern_ratios(pattern)
            >>> # Returns: "B=0.618, BC_proj=1.272, D=0.786"
        """
        return (
            f"B={pattern.ab_xa_ratio:.3f}, "
            f"BC_proj={pattern.bc_projection:.3f}, "
            f"D={pattern.ad_xa_ratio:.3f}"
        )

    @staticmethod
    def format_reaction_status(
        reaction_data: Optional['ReactionData'],
        pattern: 'HarmonicPattern'
    ) -> List[str]:
        """
        Format Type 1 and Type 2 reaction status information.

        Args:
            reaction_data: ReactionData object with reaction information
            pattern: HarmonicPattern object

        Returns:
            List of formatted strings describing reaction status

        Example:
            >>> lines = FormattingUtils.format_reaction_status(reaction, pattern)
            >>> for line in lines:
            ...     print(line)
        """
        lines: List[str] = []

        if not reaction_data:
            return lines

        lines.append("")
        lines.append(f"  Reaction: {reaction_data.reaction_summary}")

        # Type 1 Status
        if reaction_data.type1_detected:
            type1_status = "✓ HIT"
            price_info = ""
            if reaction_data.type1_max_move:
                price_info = f" - Price reached: ${reaction_data.type1_max_move:.2f}"

            targets_hit: List[str] = []
            if reaction_data.type1_reached_382:
                targets_hit.append("38.2% of CD")
            if reaction_data.type1_reached_618:
                targets_hit.append("61.8% of CD")
            if targets_hit:
                price_info += f" ({', '.join(targets_hit)})"
        else:
            type1_status = "✗ NOT HIT"
            price_info = ""

        lines.append(f"    Type 1: {type1_status}{price_info}")

        # Type 2 Status
        if reaction_data.type2_detected:
            type2_status = "✓ HIT"
            price_info = ""
            if reaction_data.type2_terminal_bar_price:
                price_info = f" - Price reached: ${reaction_data.type2_terminal_bar_price:.2f}"
            price_info += " (Broke B level or exceeded 88.6% of CD)"
        else:
            type2_status = "✗ NOT HIT"
            price_info = ""

        lines.append(f"    Type 2: {type2_status}{price_info}")

        return lines


class TickerManager:
    """
    Manages ticker list merging and deduplication.

    Eliminates duplicate ticker merging logic throughout the codebase.
    """

    @staticmethod
    def merge_ticker_lists(
        custom_tickers: Optional[List[str]],
        universe_tickers: List[str]
    ) -> List[str]:
        """
        Merge custom tickers with universe tickers, removing duplicates.

        Custom tickers appear first in the list (scanned first), followed by
        unique universe tickers (no duplicates).

        Args:
            custom_tickers: List of custom ticker symbols (can be None)
            universe_tickers: List of universe ticker symbols (e.g., S&P 500)

        Returns:
            Merged list with custom tickers first, then unique universe tickers

        Example:
            >>> custom = ['TSLA', 'NVDA', 'AAPL']
            >>> sp500 = ['AAPL', 'MSFT', 'GOOGL', ...]
            >>> merged = TickerManager.merge_ticker_lists(custom, sp500)
            >>> # Returns: ['TSLA', 'NVDA', 'AAPL', 'MSFT', 'GOOGL', ...]
            >>> # Note: AAPL appears only once (from custom list)
        """
        # If no custom tickers, return universe as-is
        if not custom_tickers:
            logger.debug("No custom tickers provided, using universe tickers only")
            return universe_tickers

        # Normalize custom tickers to uppercase
        custom_upper = [t.upper().strip() for t in custom_tickers]

        # Filter out universe tickers that are already in custom list
        custom_upper_set = {c.upper() for c in custom_upper}
        unique_universe = [
            t for t in universe_tickers
            if t.upper() not in custom_upper_set
        ]

        logger.debug(
            f"Merged {len(custom_upper)} custom tickers with "
            f"{len(unique_universe)} unique universe tickers"
        )

        # Return custom tickers first, then unique universe tickers
        return custom_upper + unique_universe

    @staticmethod
    def print_custom_ticker_info(custom_tickers: Optional[List[str]]) -> None:
        """
        Print information about custom tickers being scanned first.

        Args:
            custom_tickers: List of custom ticker symbols
        """
        if custom_tickers:
            logger.info(f"Custom tickers will be scanned first: {', '.join(custom_tickers)}")
