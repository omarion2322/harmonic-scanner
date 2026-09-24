"""
Chart generation for harmonic patterns.

This module handles all visualization logic for harmonic patterns,
separated from pattern detection to improve maintainability.

Note: Uses pathlib.Path exclusively for all path operations.
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from pathlib import Path

import pandas as pd
import numpy as np

# Configure matplotlib for thread-safety before importing pyplot
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend, thread-safe
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import matplotlib.patches as mpatches

from logging_config import get_logger
from exceptions import ChartGenerationError
from divergence_detector import point_reading_value
from tp_strategies.base import format_target, target_allocations
from config import POSITION_SIZE_T1, POSITION_SIZE_T2, POSITION_SIZE_T3

if TYPE_CHECKING:
    from pattern_detector import HarmonicPattern
    from reaction_detector import ReactionData
    from sector_etf_analyzer import SectorETFAnalysis

logger = get_logger(__name__)


class ChartGenerator:
    """
    Generates visualization charts for harmonic patterns.

    Responsibilities:
    - Create candlestick charts
    - Overlay harmonic pattern structure
    - Add Fibonacci ratio annotations
    - Highlight the Type 2 reaction area
    - Add trading level information boxes
    """

    BACKGROUND = '#0d1117'
    SURFACE = '#161b22'
    TEXT = '#e6edf3'
    MUTED = '#9da7b3'
    BORDER = '#394452'
    BULLISH = '#3dd6b0'
    BEARISH = '#ff7b86'
    ACCENT = '#79c0ff'
    DIVERGENCE = '#d2a8ff'

    def __init__(self, dpi: int = 150):
        """
        Initialize chart generator.

        Args:
            dpi: Dots per inch for chart resolution
        """
        self.dpi = dpi
        self.figsize = (16, 9)

    def generate_pattern_chart(
        self,
        pattern: 'HarmonicPattern',
        ticker: str,
        df: pd.DataFrame,
        chart_dir: str,
        interval: str = '1d',
        reaction_data: Optional['ReactionData'] = None,
        sector_etf_analysis: Optional['SectorETFAnalysis'] = None
    ) -> str:
        """
        Generate a chart visualization of the harmonic pattern.

        Args:
            pattern: The harmonic pattern to visualize
            ticker: Stock ticker symbol
            df: Price dataframe with OHLC data
            chart_dir: Directory to save the chart
            interval: Time interval ('1d', '1wk', '1mo', etc.)
            reaction_data: Optional ReactionData object with Type 1/Type 2 analysis
            sector_etf_analysis: Optional sector ETF trend confluence

        Returns:
            Path to the saved chart image

        Raises:
            ChartGenerationError: If chart generation fails
        """
        try:
            # Create directory if it doesn't exist
            Path(chart_dir).mkdir(parents=True, exist_ok=True)

            # Create figure
            fig, ax = plt.subplots(figsize=self.figsize, facecolor=self.BACKGROUND)

            # Filter data to relevant time window
            df_window = self._get_chart_window(df, pattern)

            # Plot candlesticks
            self._plot_candlesticks(ax, df_window, interval)

            # Overlay harmonic pattern
            self._plot_pattern_overlay(ax, pattern)

            # Add Fibonacci ratio vectors
            self._plot_fibonacci_ratios(ax, pattern)

            # Highlight the Type 2 reaction area
            if reaction_data:
                self._plot_reaction_markers(ax, pattern, reaction_data)

            # Add title and labels
            self._add_chart_labels(ax, pattern, ticker, interval)

            # Add trading info box
            self._add_info_box(ax, pattern, reaction_data)

            if sector_etf_analysis:
                self._add_sector_etf_box(ax, sector_etf_analysis)

            # Configure axes
            self._configure_axes(ax, pattern, reaction_data)

            # Add grid and styling
            self._apply_chart_styling(ax)

            # Add watermark
            self._add_watermark(fig)

            # Save chart
            chart_path = self._save_chart(fig, ticker, pattern, chart_dir)

            plt.close(fig)
            logger.debug(f"Chart generated successfully: {chart_path}")

            return chart_path

        except Exception as e:
            logger.error(f"Failed to generate chart for {ticker}: {e}")
            raise ChartGenerationError(
                f"Chart generation failed: {e}",
                ticker=ticker
            )

    @staticmethod
    def _format_divergence_summary(evidence) -> str:
        """Show exact point readings independently of the divergence decision."""
        source = (
            "Type 2 reaction area"
            if evidence and evidence.get("context") == "type2_retest" else "D point"
        )
        lines = ["MOMENTUM DIVERGENCE", "─" * 20, f"Source: {source}"]
        direction = evidence.get("anchor", {}).get("is_bullish") if evidence else None
        for key, label in (("rsi", "RSI14"), ("macd", "MACD")):
            item = evidence.get(key, {}) if evidence else {}
            value = point_reading_value(evidence, key)
            number = f"{value:.2f}" if value is not None else "N/A"
            confirmed = item.get("confirmed")
            if confirmed is True and direction is not None:
                status = "Bullish divergence" if direction else "Bearish divergence"
            elif confirmed is True:
                status = "Divergence (direction unavailable)"
            elif confirmed is False:
                status = "No divergence"
            elif not evidence:
                status = "Unavailable"
            elif evidence.get("status") == "developing":
                status = "Awaiting confirmation"
            else:
                status = "Unavailable"
            lines.append(f"{label}: {number} | {status}")
        if evidence and evidence.get("persistence_error"):
            lines.append("Warning: observation not saved")
        return "\n".join(lines)

    def _get_chart_window(
        self,
        df: pd.DataFrame,
        pattern: 'HarmonicPattern'
    ) -> pd.DataFrame:
        """
        Get the relevant time window for the chart (2x pattern duration).

        Args:
            df: Full price dataframe
            pattern: Harmonic pattern

        Returns:
            Filtered dataframe
        """
        pattern_start = (
            pattern.origin.date
            if pattern.pattern_type == '5-0' and pattern.origin
            else pattern.x.date
        )
        pattern_end = pattern.d.date
        pattern_duration = pattern_end - pattern_start

        # Calculate 2x the pattern duration
        chart_start = pattern_end - (pattern_duration * 2)

        # Filter dataframe
        df_window = df[df.index >= chart_start]

        # Ensure we have the pattern completion point
        if pattern_end not in df_window.index:
            df_window = df

        return df_window

    def _plot_candlesticks(
        self,
        ax: plt.Axes,
        df: pd.DataFrame,
        interval: str
    ) -> None:
        """
        Plot candlestick chart.

        Args:
            ax: Matplotlib axes
            df: Price dataframe
            interval: Time interval
        """
        dates = df.index
        opens = df['open'].values
        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values

        # Determine candle width based on interval
        candle_width = self._get_candle_width(interval)

        # Draw candlesticks
        for i, date in enumerate(dates):
            self._draw_single_candle(
                ax, date, opens[i], closes[i],
                highs[i], lows[i], candle_width
            )

    def _get_candle_width(self, interval: str) -> float:
        """Get appropriate candle width for the interval."""
        width_map = {
            '1d': 0.6,
            '3d': 2.0,
            '1wk': 5.0,
            '1mo': 20.0
        }
        return width_map.get(interval, 0.6)

    def _draw_single_candle(
        self,
        ax: plt.Axes,
        date: pd.Timestamp,
        open_price: float,
        close_price: float,
        high_price: float,
        low_price: float,
        candle_width: float
    ) -> None:
        """Draw a single candlestick."""
        # Determine colors
        if close_price >= open_price:
            body_color = self.BULLISH
            edge_color = self.BULLISH
        else:
            body_color = self.BEARISH
            edge_color = self.BEARISH

        # Draw high-low line (wick)
        ax.plot(
            [date, date],
            [low_price, high_price],
            color=edge_color,
            linewidth=1,
            zorder=1
        )

        # Draw open-close rectangle (body)
        height = abs(close_price - open_price)
        bottom = min(open_price, close_price)

        rect = Rectangle(
            (mdates.date2num(date) - candle_width / 2, bottom),
            candle_width,
            height,
            facecolor=body_color,
            edgecolor=edge_color,
            linewidth=1,
            zorder=2,
            alpha=0.8
        )
        ax.add_patch(rect)

    def _plot_pattern_overlay(
        self,
        ax: plt.Axes,
        pattern: 'HarmonicPattern'
    ) -> None:
        """
        Plot the harmonic pattern overlay on the chart.

        Args:
            ax: Matplotlib axes
            pattern: Harmonic pattern
        """
        if pattern.pattern_type == '5-0' and pattern.origin:
            pattern_points = [
                pattern.origin, pattern.x, pattern.a,
                pattern.b, pattern.c, pattern.d
            ]
            pattern_labels = ['0', 'X', 'A', 'B', 'C', 'D']
        else:
            pattern_points = [pattern.x, pattern.a, pattern.b, pattern.c, pattern.d]
            pattern_labels = ['X', 'A', 'B', 'C', 'D']
        pattern_dates = [p.date for p in pattern_points]
        pattern_prices = [p.price for p in pattern_points]

        # Pattern line color based on direction
        pattern_line_color = self.ACCENT if pattern.is_bullish else '#ffa657'

        # Draw pattern lines
        for i in range(len(pattern_points) - 1):
            ax.plot(
                [pattern_dates[i], pattern_dates[i + 1]],
                [pattern_prices[i], pattern_prices[i + 1]],
                color=pattern_line_color,
                linewidth=3,
                alpha=0.9,
                zorder=10,
                solid_capstyle='round'
            )

        # Fill pattern area
        ax.fill(
            pattern_dates,
            pattern_prices,
            color=pattern_line_color,
            alpha=0.1,
            zorder=3
        )

        # Plot pattern points
        self._plot_pattern_points(ax, pattern, pattern_dates, pattern_prices, pattern_labels)

    def _plot_pattern_points(
        self,
        ax: plt.Axes,
        pattern: 'HarmonicPattern',
        dates: list,
        prices: list,
        labels: list
    ) -> None:
        """Plot individual pattern points with labels."""
        # Point colors alternate between peak/trough
        first_color = self.BEARISH if pattern.is_bullish else self.BULLISH
        second_color = self.BULLISH if pattern.is_bullish else self.BEARISH
        point_colors = [
            first_color if i % 2 == 0 else second_color
            for i in range(len(labels))
        ]

        y_offset = (max(prices) - min(prices)) * 0.03

        for date, price, label, color in zip(dates, prices, labels, point_colors):
            # Outer circle
            ax.scatter(
                date, price,
                c=self.TEXT,
                s=300,
                zorder=11,
                edgecolors=self.BACKGROUND,
                linewidth=3
            )
            # Inner circle
            ax.scatter(
                date, price,
                c=color,
                s=250,
                zorder=12,
                edgecolors=self.BACKGROUND,
                linewidth=2
            )

            # Label above point
            ax.text(
                date, price + y_offset,
                label,
                fontsize=12,
                fontweight='bold',
                ha='center',
                va='bottom',
                color=self.TEXT,
                zorder=13,
                bbox=dict(
                    boxstyle='round,pad=0.4',
                    facecolor=self.SURFACE,
                    alpha=0.8,
                    edgecolor=color,
                    linewidth=2
                )
            )

            # Price label below point
            ax.text(
                date, price - y_offset,
                f'\\${price:.2f}',
                fontsize=9,
                ha='center',
                va='top',
                color=self.TEXT,
                zorder=13,
                bbox=dict(
                    boxstyle='round,pad=0.3',
                    facecolor=self.SURFACE,
                    alpha=0.9,
                    edgecolor=self.BORDER,
                    linewidth=1
                )
            )

    def _plot_fibonacci_ratios(
        self,
        ax: plt.Axes,
        pattern: 'HarmonicPattern'
    ) -> None:
        """
        Plot Fibonacci ratio vectors showing key relationships.

        Args:
            ax: Matplotlib axes
            pattern: Harmonic pattern
        """
        ratio_color = self.ACCENT
        ratio_style = '--'
        ratio_width = 2.5
        ratio_alpha = 0.6

        if pattern.pattern_type == '5-0':
            reciprocal_ratio = (
                abs(pattern.d.price - pattern.c.price)
                / abs(pattern.b.price - pattern.a.price)
            )
            vectors = [
                (
                    pattern.x, pattern.b, pattern.ab_xa_ratio,
                    f'{pattern.ab_xa_ratio:.3f} XA'
                ),
                (
                    pattern.a, pattern.c, pattern.bc_ab_ratio,
                    f'{pattern.bc_ab_ratio:.3f} AB'
                ),
                (
                    pattern.b, pattern.d, pattern.cd_bc_ratio,
                    f'{pattern.cd_bc_ratio:.3f} BC'
                ),
                (
                    pattern.c, pattern.d, reciprocal_ratio,
                    f'AB=CD {reciprocal_ratio:.3f}'
                ),
            ]
            for start, end, ratio, label in vectors:
                self._draw_ratio_vector(
                    ax, start.date, start.price, end.date, end.price,
                    ratio, ratio_color, ratio_style, ratio_width, ratio_alpha,
                    label=label
                )
            return

        # Vector 1: X → B (AB/XA ratio)
        self._draw_ratio_vector(
            ax, pattern.x.date, pattern.x.price,
            pattern.b.date, pattern.b.price,
            pattern.ab_xa_ratio, ratio_color, ratio_style,
            ratio_width, ratio_alpha
        )

        # Vector 2: A → C (BC/AB ratio)
        self._draw_ratio_vector(
            ax, pattern.a.date, pattern.a.price,
            pattern.c.date, pattern.c.price,
            pattern.bc_ab_ratio, ratio_color, ratio_style,
            ratio_width, ratio_alpha
        )

        # Vector 3: B → D (BC projection)
        self._draw_ratio_vector(
            ax, pattern.b.date, pattern.b.price,
            pattern.d.date, pattern.d.price,
            pattern.bc_projection, ratio_color, ratio_style,
            ratio_width, ratio_alpha
        )

        # Vector 4: X → D (AD/XA ratio)
        self._draw_ratio_vector(
            ax, pattern.x.date, pattern.x.price,
            pattern.d.date, pattern.d.price,
            pattern.ad_xa_ratio, ratio_color, ratio_style,
            ratio_width, ratio_alpha
        )

    def _draw_ratio_vector(
        self,
        ax: plt.Axes,
        date1: pd.Timestamp,
        price1: float,
        date2: pd.Timestamp,
        price2: float,
        ratio: float,
        color: str,
        style: str,
        width: float,
        alpha: float,
        label: Optional[str] = None
    ) -> None:
        """Draw a single ratio vector with label."""
        # Draw line
        ax.plot(
            [date1, date2],
            [price1, price2],
            color=color,
            linewidth=width,
            linestyle=style,
            alpha=alpha,
            zorder=8
        )

        # Calculate midpoint for label
        mid_date = date1 + (date2 - date1) / 2
        mid_price = (price1 + price2) / 2

        # Add ratio label
        ax.text(
            mid_date, mid_price,
            label or f'{ratio:.3f}',
            fontsize=9,
            ha='center',
            va='center',
            fontweight='bold',
            color=self.ACCENT,
            zorder=14,
            bbox=dict(
                boxstyle='round,pad=0.4',
                facecolor=self.SURFACE,
                alpha=0.85,
                edgecolor=color,
                linewidth=1.5
            )
        )

    def _plot_reaction_markers(
        self,
        ax: plt.Axes,
        pattern: 'HarmonicPattern',
        reaction_data: 'ReactionData'
    ) -> None:
        """Draw only the retest area, below candles so prices stay readable."""
        low = reaction_data.type2_reaction_area_low
        high = reaction_data.type2_reaction_area_high
        if low is not None and high is not None:
            if low == high:
                ax.axhline(
                    low, color='#90ee90', alpha=0.2, zorder=0.5,
                    label='Type 2 reaction area',
                )
            else:
                ax.axhspan(
                    low, high, color='#90ee90', alpha=0.2, zorder=0.5,
                    label='Type 2 reaction area',
                )

    def _add_chart_labels(
        self,
        ax: plt.Axes,
        pattern: 'HarmonicPattern',
        ticker: str,
        interval: str
    ) -> None:
        """Add title and axis labels."""
        direction = "BULLISH" if pattern.is_bullish else "BEARISH"
        interval_name = {
            '1d': 'Daily',
            '3d': '3-Day',
            '1wk': 'Weekly',
            '1mo': 'Monthly'
        }.get(interval, interval.upper())

        title = f"{ticker} - {direction} {pattern.pattern_type.upper()}"
        subtitle = (
            f"{interval_name} Chart | Grade: {pattern.grade} | "
            f"Detected: {pattern.d.date.date()} | R/R: {pattern.risk_reward:.2f}:1"
        )

        ax.set_title(
            f"{title}\n{subtitle}",
            fontsize=14,
            fontweight='bold',
            color=self.TEXT,
        )
        ax.set_xlabel('Date', fontsize=12, color=self.TEXT)
        ax.set_ylabel('Price (\\$)', fontsize=12, color=self.TEXT)

    def _add_info_box(
        self,
        ax: plt.Axes,
        pattern: 'HarmonicPattern',
        reaction_data: Optional['ReactionData']
    ) -> None:
        """Add trading information box to the chart."""
        risk_pct = abs((pattern.entry_price - pattern.stop_loss) / pattern.entry_price * 100)

        # Keep the selected strategy separate from each target's provenance.
        tp_strategy_display = ""
        strategy_name = getattr(pattern, 'tp_strategy_name', '')
        if not strategy_name:
            legacy_strategy = getattr(pattern, 'tp_strategy_used', '')
            if legacy_strategy and not legacy_strategy.startswith("T1:"):
                strategy_name = legacy_strategy
        if strategy_name:
            tp_strategy_display = f"\nStrategy: {strategy_name}"

        # PRZ range display
        prz_range_text = ""
        if pattern.d_point_range_min > 0 and pattern.d_point_range_max > 0:
            range_pct = ((pattern.d_point_range_max - pattern.entry_price) / pattern.entry_price) * 100
            prz_range_text = f"Entry Zone: \\${pattern.d_point_range_min:.2f} - \\${pattern.d_point_range_max:.2f} (+/-{range_pct:.1f}%)\n"

        targets = (pattern.ipo_target_1, pattern.ipo_target_2, pattern.target_point_a)
        allocations = target_allocations(
            targets, (POSITION_SIZE_T1, POSITION_SIZE_T2, POSITION_SIZE_T3)
        )
        target_details = getattr(
            pattern, 'tp_target_details', (None, None, None)
        )
        target_text = "".join(
            f"T{index}: {format_target(price)}"
            + (f" ({detail})" if detail else "")
            + (f" ({allocation:.0%})" if targets[2] is None else "")
            + "\n"
            for index, (price, allocation, detail) in enumerate(
                zip(targets, allocations, target_details), 1
            )
            if price is not None
        ).rstrip("\n").replace("$", r"\$")
        # Build info text (escape $ to prevent matplotlib LaTeX parsing)
        info_text = (
            f"TRADING LEVELS\n"
            f"{'─' * 20}\n"
            f"Entry: \\${pattern.entry_price:.2f}\n"
            f"{prz_range_text}"
            f"Stop:  \\${pattern.stop_loss:.2f}\n"
            f"Risk:  {risk_pct:.1f}%\n"
            f"\n"
            f"PROFIT TARGETS\n"
            f"{'─' * 20}\n"
            f"{target_text}{tp_strategy_display}\n"
        )

        # Add reaction info
        info_text += self._format_reaction_info(reaction_data)
        info_text += "\n" + self._format_divergence_summary(getattr(pattern, 'divergence', None))

        # Add text box
        ax.text(
            0.02, 0.98,
            info_text,
            transform=ax.transAxes,
            fontsize=9,
            color=self.TEXT,
            verticalalignment='top',
            horizontalalignment='left',
            family='monospace',
            zorder=20,
            bbox=dict(
                boxstyle='round,pad=0.8',
                facecolor=self.SURFACE,
                edgecolor=self.BORDER,
                alpha=0.95,
                linewidth=2
            )
        )

    def _format_reaction_info(self, reaction_data: Optional['ReactionData']) -> str:
        """A Type 2 hit requires the second reversal, not merely a zone touch."""
        info = f"\nREACTION ANALYSIS\n{'─' * 20}\n"
        if reaction_data is None:
            return info + "Type 2 Hit: NO\n  Not evaluated\nType 2 reaction area: N/A\n"
        info += f"Type 2 Hit: {'YES' if reaction_data.type2_detected else 'NO'}\n"
        low, high = reaction_data.type2_reaction_area_low, reaction_data.type2_reaction_area_high
        info += "Type 2 reaction area:\n"
        if low is not None and high is not None:
            info += f"  \\${low:.2f}"
            if low != high:
                info += f" - \\${high:.2f}"
            info += "\n"
        elif reaction_data.type2_retest_price is not None:
            info += f"  \\${reaction_data.type2_retest_price:.2f} (retest)\n"
        else:
            info += "  N/A\n"
        if low is not None and high is not None and reaction_data.type2_retest_price is not None:
            info += f"Retest price: \\${reaction_data.type2_retest_price:.2f}\n"
        if reaction_data.type2_retest_date and not reaction_data.type2_detected:
            info += "Retested; awaiting reversal\n"
        return info

    def _format_sector_etf_info(
        self,
        analysis: 'SectorETFAnalysis'
    ) -> str:
        """Format sector ETF trend confluence for the chart info box."""
        trend_marker = {"UP": "+", "DOWN": "-", "MIXED": "~"}.get(
            analysis.trend,
            "?",
        )
        return (
            f"\nRELEVANT ETF CONFLUENCE\n"
            f"{'-' * 20}\n"
            f"{analysis.theme}: {analysis.etf_ticker}\n"
            f"Trend: {trend_marker} {analysis.trend}\n"
            f"20-period return: {analysis.return_20_period_pct:+.1f}%\n"
            f"Price / SMA20 / SMA50:\n"
            f"  \\${analysis.current_price:.2f} / "
            f"\\${analysis.sma_20:.2f} / \\${analysis.sma_50:.2f}\n"
            f"Signal: {analysis.confluence_label}\n"
        )

    def _add_sector_etf_box(
        self,
        ax: plt.Axes,
        analysis: 'SectorETFAnalysis'
    ) -> None:
        """Add a prominent relevant ETF confluence card."""
        if analysis.confirms_signal:
            facecolor = "#132d28"
            edgecolor = self.BULLISH
        elif analysis.trend == "MIXED":
            facecolor = "#302919"
            edgecolor = "#e3b341"
        else:
            facecolor = "#321e25"
            edgecolor = self.BEARISH

        ax.text(
            0.98,
            0.98,
            self._format_sector_etf_info(analysis),
            transform=ax.transAxes,
            fontsize=9,
            color=self.TEXT,
            verticalalignment="top",
            horizontalalignment="right",
            family="monospace",
            zorder=20,
            bbox=dict(
                boxstyle="round,pad=0.8",
                facecolor=facecolor,
                edgecolor=edgecolor,
                alpha=0.95,
                linewidth=2,
            ),
        )

    def _configure_axes(
        self,
        ax: plt.Axes,
        pattern: 'HarmonicPattern',
        reaction_data: Optional['ReactionData']
    ) -> None:
        """Configure x-axis with important dates."""
        important_dates = [
            pattern.x.date, pattern.a.date, pattern.b.date,
            pattern.c.date, pattern.d.date
        ]
        important_labels = ['X', 'A', 'B', 'C', 'D']

        # Set x-axis ticks
        ax.set_xticks(important_dates)
        ax.set_xticklabels(
            [f"{label}\n{date.strftime('%Y-%m-%d')}"
             for label, date in zip(important_labels, important_dates)],
            rotation=45,
            ha='right',
            fontsize=9,
            fontweight='bold'
        )

        # Add minor ticks
        ax.xaxis.set_minor_locator(mdates.AutoDateLocator())
        ax.xaxis.set_minor_formatter(mdates.DateFormatter('%m/%d'))

    def _apply_chart_styling(self, ax: plt.Axes) -> None:
        """Apply grid and styling to the chart."""
        ax.grid(True, color=self.BORDER, alpha=0.5, linestyle='--', linewidth=0.5, zorder=0)
        ax.set_facecolor(self.BACKGROUND)
        ax.tick_params(axis='both', which='both', colors=self.MUTED)
        ax.xaxis.get_offset_text().set_color(self.MUTED)
        ax.yaxis.get_offset_text().set_color(self.MUTED)
        for spine in ax.spines.values():
            spine.set_color(self.BORDER)

    def _add_watermark(self, fig: plt.Figure) -> None:
        """Add timestamp watermark to the chart."""
        fig.text(
            0.99, 0.01,
            f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
            ha='right',
            va='bottom',
            fontsize=8,
            color=self.MUTED,
            alpha=0.8
        )

    def _save_chart(
        self,
        fig: plt.Figure,
        ticker: str,
        pattern: 'HarmonicPattern',
        chart_dir: str
    ) -> str:
        """Save chart to file and return path."""
        fig.tight_layout(rect=(0, 0.03, 1, 1))

        chart_filename = (
            f"{ticker}_{pattern.pattern_type.replace(' ', '_')}_"
            f"{pattern.d.date.date()}.png"
        )
        chart_path = Path(chart_dir) / chart_filename

        fig.savefig(
            str(chart_path),  # Convert Path to str for matplotlib
            dpi=self.dpi,
            bbox_inches='tight',
            facecolor=self.BACKGROUND,
            edgecolor='none'
        )

        return str(chart_path)  # Return as string for backward compatibility
