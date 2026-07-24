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
    - Include Type 1/Type 2 reaction markers
    - Add trading level information boxes
    """

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
            fig, ax = plt.subplots(figsize=self.figsize)

            # Filter data to relevant time window
            df_window = self._get_chart_window(df, pattern)

            # Plot candlesticks
            self._plot_candlesticks(ax, df_window, interval)

            # Overlay harmonic pattern
            self._plot_pattern_overlay(ax, pattern)

            # Add Fibonacci ratio vectors
            self._plot_fibonacci_ratios(ax, pattern)

            # Add Type 1/Type 2 reaction markers
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
            body_color = '#26a69a'  # Teal green (bullish)
            edge_color = '#1a7a6d'
        else:
            body_color = '#ef5350'  # Red (bearish)
            edge_color = '#c62828'

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
        pattern_line_color = '#2962ff' if pattern.is_bullish else '#ff6d00'

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
        first_color = '#d32f2f' if pattern.is_bullish else '#388e3c'
        second_color = '#388e3c' if pattern.is_bullish else '#d32f2f'
        point_colors = [
            first_color if i % 2 == 0 else second_color
            for i in range(len(labels))
        ]

        y_offset = (max(prices) - min(prices)) * 0.03

        for date, price, label, color in zip(dates, prices, labels, point_colors):
            # Outer circle
            ax.scatter(
                date, price,
                c='white',
                s=300,
                zorder=11,
                edgecolors='black',
                linewidth=3
            )
            # Inner circle
            ax.scatter(
                date, price,
                c=color,
                s=250,
                zorder=12,
                edgecolors='black',
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
                color='white',
                zorder=13,
                bbox=dict(
                    boxstyle='round,pad=0.4',
                    facecolor='black',
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
                color='black',
                zorder=13,
                bbox=dict(
                    boxstyle='round,pad=0.3',
                    facecolor='white',
                    alpha=0.9,
                    edgecolor='gray',
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
        ratio_color = '#1e88e5'
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
            color='white',
            zorder=14,
            bbox=dict(
                boxstyle='round,pad=0.4',
                facecolor=color,
                alpha=0.85,
                edgecolor='white',
                linewidth=1.5
            )
        )

    def _plot_reaction_markers(
        self,
        ax: plt.Axes,
        pattern: 'HarmonicPattern',
        reaction_data: 'ReactionData'
    ) -> None:
        """
        Plot Type 1 and Type 2 reaction markers.

        Args:
            ax: Matplotlib axes
            pattern: Harmonic pattern
            reaction_data: Reaction analysis data
        """
        # Mark Terminal Bar (T-Bar) at point D
        ax.axvline(
            x=pattern.d.date,
            color='purple',
            linestyle=':',
            linewidth=3,
            alpha=0.8,
            zorder=15
        )

        # Type 1 Reaction
        if reaction_data.type1_detected and reaction_data.type1_reversal_date:
            self._plot_type1_reaction(ax, pattern, reaction_data)

        # Type 2 Reaction
        if reaction_data.type2_detected:
            self._plot_type2_reaction(ax, reaction_data)

    def _plot_type1_reaction(
        self,
        ax: plt.Axes,
        pattern: 'HarmonicPattern',
        reaction_data: 'ReactionData'
    ) -> None:
        """Plot Type 1 reaction markers."""
        # Mark Type 1 reversal bar
        ax.axvline(
            x=reaction_data.type1_reversal_date,
            color='#ff9800',
            linestyle='-.',
            linewidth=2.5,
            alpha=0.8,
            zorder=15
        )

        # Draw arrow showing Type 1 move
        ax.annotate(
            '',
            xy=(reaction_data.type1_reversal_date, reaction_data.type1_max_move),
            xytext=(pattern.d.date, pattern.d.price),
            arrowprops=dict(
                arrowstyle='->',
                color='#ff9800',
                lw=2.5,
                alpha=0.7
            ),
            zorder=14
        )

        # Mark 38.2% target if reached
        if reaction_data.type1_reached_382:
            ax.scatter(
                reaction_data.type1_reversal_date,
                reaction_data.target_382,
                marker='*',
                s=400,
                c='gold',
                edgecolors='black',
                linewidth=2,
                zorder=16
            )

        # Mark 61.8% target if reached
        if reaction_data.type1_reached_618:
            ax.scatter(
                reaction_data.type1_reversal_date,
                reaction_data.target_618,
                marker='*',
                s=500,
                c='lime',
                edgecolors='black',
                linewidth=2,
                zorder=16
            )

    def _plot_type2_reaction(
        self,
        ax: plt.Axes,
        reaction_data: 'ReactionData'
    ) -> None:
        """Plot Type 2 reaction markers."""
        if reaction_data.type2_retest_date:
            # Mark Type 2 retest
            ax.axvline(
                x=reaction_data.type2_retest_date,
                color='magenta',
                linestyle='--',
                linewidth=2.5,
                alpha=0.8,
                zorder=15
            )

            # Mark Type 2 terminal bar
            if reaction_data.type2_terminal_bar_date:
                ax.axvline(
                    x=reaction_data.type2_terminal_bar_date,
                    color='cyan',
                    linestyle=':',
                    linewidth=2.5,
                    alpha=0.8,
                    zorder=15
                )

                # Highlight retest zone
                ax.axvspan(
                    reaction_data.type2_retest_date,
                    reaction_data.type2_terminal_bar_date,
                    alpha=0.15,
                    color='magenta',
                    zorder=5
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
            fontweight='bold'
        )
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Price (\\$)', fontsize=12)

    def _add_info_box(
        self,
        ax: plt.Axes,
        pattern: 'HarmonicPattern',
        reaction_data: Optional['ReactionData']
    ) -> None:
        """Add trading information box to the chart."""
        risk_pct = abs((pattern.entry_price - pattern.stop_loss) / pattern.entry_price * 100)

        # TP strategy display
        tp_strategy_display = ""
        if hasattr(pattern, 'tp_strategy_used') and pattern.tp_strategy_used:
            tp_strategy_display = f"\nStrategy: {pattern.tp_strategy_used}"

        # PRZ range display
        prz_range_text = ""
        if pattern.d_point_range_min > 0 and pattern.d_point_range_max > 0:
            range_pct = ((pattern.d_point_range_max - pattern.entry_price) / pattern.entry_price) * 100
            prz_range_text = f"Entry Zone: \\${pattern.d_point_range_min:.2f} - \\${pattern.d_point_range_max:.2f} (+/-{range_pct:.1f}%)\n"

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
            f"T1: \\${pattern.ipo_target_1:.2f}\n"
            f"T2: \\${pattern.ipo_target_2:.2f}\n"
            f"T3: \\${pattern.target_point_a:.2f}{tp_strategy_display}\n"
            f"\n"
            f"PATTERN METRICS\n"
            f"{'─' * 20}\n"
            f"Tolerance: {pattern.tolerance_level}\n"
            f"Grade:     {pattern.grade}\n"
        )

        # Add reaction info
        if reaction_data:
            info_text += self._format_reaction_info(reaction_data)

        # Add text box
        ax.text(
            0.02, 0.98,
            info_text,
            transform=ax.transAxes,
            fontsize=9,
            verticalalignment='top',
            horizontalalignment='left',
            family='monospace',
            zorder=20,
            bbox=dict(
                boxstyle='round,pad=0.8',
                facecolor='white',
                edgecolor='gray',
                alpha=0.95,
                linewidth=2
            )
        )

    def _format_reaction_info(self, reaction_data: 'ReactionData') -> str:
        """Format reaction information for info box."""
        info = f"\nREACTION ANALYSIS\n{'─' * 20}\n"

        # Type 1 info
        if reaction_data.type1_detected:
            info += "Type 1: YES\n"
            if reaction_data.type1_max_move:
                info += f"  Price: \\${reaction_data.type1_max_move:.2f}\n"
            if reaction_data.target_382:
                status_382 = "✓" if reaction_data.type1_reached_382 else "○"
                info += f"  38.2% ({status_382}): \\${reaction_data.target_382:.2f}\n"
            if reaction_data.target_618:
                status_618 = "✓" if reaction_data.type1_reached_618 else "○"
                info += f"  61.8% ({status_618}): \\${reaction_data.target_618:.2f}\n"
            if reaction_data.type1_trendline_broken:
                info += "  Trendline: BROKEN\n"
        else:
            info += "Type 1: PENDING\n"

        # Type 2 info
        if reaction_data.type2_detected:
            info += "Type 2: YES\n  PRZ Retested\n"
            if hasattr(reaction_data, 'type2_retest_price') and reaction_data.type2_retest_price:
                info += f"  Price: \\${reaction_data.type2_retest_price:.2f}\n"
        elif reaction_data.type1_trendline_broken:
            info += "Type 2: WATCHING\n"

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
            facecolor = "#e8f5e9"
            edgecolor = "#2e7d32"
        elif analysis.trend == "MIXED":
            facecolor = "#fff8e1"
            edgecolor = "#f9a825"
        else:
            facecolor = "#ffebee"
            edgecolor = "#c62828"

        ax.text(
            0.98,
            0.98,
            self._format_sector_etf_info(analysis),
            transform=ax.transAxes,
            fontsize=9,
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

        # Add reaction dates
        if reaction_data:
            if reaction_data.type1_detected and reaction_data.type1_reversal_date:
                important_dates.append(reaction_data.type1_reversal_date)
                important_labels.append('T1')
            if reaction_data.type2_detected and reaction_data.type2_terminal_bar_date:
                important_dates.append(reaction_data.type2_terminal_bar_date)
                important_labels.append('T2')

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
        ax.grid(True, alpha=0.2, linestyle='--', linewidth=0.5, zorder=0)
        ax.set_facecolor('#f8f9fa')

    def _add_watermark(self, fig: plt.Figure) -> None:
        """Add timestamp watermark to the chart."""
        fig.text(
            0.99, 0.01,
            f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
            ha='right',
            va='bottom',
            fontsize=8,
            color='gray',
            alpha=0.5
        )

    def _save_chart(
        self,
        fig: plt.Figure,
        ticker: str,
        pattern: 'HarmonicPattern',
        chart_dir: str
    ) -> str:
        """Save chart to file and return path."""
        plt.tight_layout()

        chart_filename = (
            f"{ticker}_{pattern.pattern_type.replace(' ', '_')}_"
            f"{pattern.d.date.date()}.png"
        )
        chart_path = Path(chart_dir) / chart_filename

        fig.savefig(
            str(chart_path),  # Convert Path to str for matplotlib
            dpi=self.dpi,
            bbox_inches='tight',
            facecolor='white',
            edgecolor='none'
        )

        return str(chart_path)  # Return as string for backward compatibility
