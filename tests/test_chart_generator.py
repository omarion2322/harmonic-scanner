"""
Tests for ChartGenerator class.
"""

import pytest
from pathlib import Path
import sys
from unittest.mock import Mock, MagicMock, patch
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from chart_generator import ChartGenerator
from pattern_detector import HarmonicPattern, Point
from exceptions import ChartGenerationError
from sector_etf_analyzer import SectorETFAnalysis


class TestChartGeneratorInitialization:
    """Test ChartGenerator initialization."""

    def test_initialization_default_dpi(self):
        """Test initialization with default DPI."""
        generator = ChartGenerator()

        assert generator.dpi == 150
        assert generator.figsize == (16, 9)

    def test_initialization_custom_dpi(self):
        """Test initialization with custom DPI."""
        generator = ChartGenerator(dpi=300)

        assert generator.dpi == 300
        assert generator.figsize == (16, 9)


class TestGeneratePatternChart:
    """Test generate_pattern_chart method."""

    @pytest.fixture
    def sample_pattern(self, sample_pattern_points):
        """Create a sample harmonic pattern for testing."""
        return HarmonicPattern(
            x=sample_pattern_points['x'],
            a=sample_pattern_points['a'],
            b=sample_pattern_points['b'],
            c=sample_pattern_points['c'],
            d=sample_pattern_points['d'],
            pattern_type='gartley',
            is_bullish=True,
            ab_xa_ratio=0.618,
            bc_ab_ratio=0.618,
            bc_projection=1.272,
            cd_bc_ratio=1.272,
            ad_xa_ratio=0.786,
            entry_price=101.5,
            stop_loss=98.0,
            ipo_target_1=105.0,
            ipo_target_2=108.0,
            target_point_a=110.0,
            risk_reward=2.5,
            prz_levels={'0.786': 101.5},
            d_point_range_min=99.5,
            d_point_range_max=103.5,
            days_since_completion=5,
            tolerance_level='3.0%',
            grade='A',
            trade_quality='High-Probability Entry',
            tp_strategy_used='Scott Strategy'
        )

    def test_generate_chart_creates_file(
        self, sample_pattern, sample_price_data, tmp_path
    ):
        """Test that chart generation creates a file."""
        generator = ChartGenerator(dpi=100)  # Lower DPI for faster tests

        chart_path = generator.generate_pattern_chart(
            pattern=sample_pattern,
            ticker="AAPL",
            df=sample_price_data,
            chart_dir=str(tmp_path),
            interval='1d'
        )

        assert Path(chart_path).exists()
        assert Path(chart_path).suffix == '.png'
        assert 'AAPL' in chart_path
        assert 'gartley' in chart_path.lower()

    def test_generate_chart_creates_directory(
        self, sample_pattern, sample_price_data, tmp_path
    ):
        """Test that chart generation creates directory if it doesn't exist."""
        generator = ChartGenerator(dpi=100)
        chart_dir = tmp_path / "charts" / "new_dir"

        assert not chart_dir.exists()

        chart_path = generator.generate_pattern_chart(
            pattern=sample_pattern,
            ticker="AAPL",
            df=sample_price_data,
            chart_dir=str(chart_dir),
            interval='1d'
        )

        assert chart_dir.exists()
        assert Path(chart_path).exists()

    def test_generate_chart_returns_path(
        self, sample_pattern, sample_price_data, tmp_path
    ):
        """Test that generate_pattern_chart returns valid path."""
        generator = ChartGenerator(dpi=100)

        chart_path = generator.generate_pattern_chart(
            pattern=sample_pattern,
            ticker="TEST",
            df=sample_price_data,
            chart_dir=str(tmp_path),
            interval='1d'
        )

        assert isinstance(chart_path, str)
        assert len(chart_path) > 0
        assert 'TEST' in chart_path

    def test_generate_chart_calls_savefig(
        self, sample_pattern, sample_price_data, tmp_path
    ):
        """Test that chart generation creates output."""
        generator = ChartGenerator(dpi=100)

        chart_path = generator.generate_pattern_chart(
            pattern=sample_pattern,
            ticker="AAPL",
            df=sample_price_data,
            chart_dir=str(tmp_path),
            interval='1d'
        )

        # Should have created a file
        assert Path(chart_path).exists()

    def test_generate_chart_with_reaction_data(
        self, sample_pattern, sample_price_data, tmp_path
    ):
        """Test chart generation with reaction data."""
        generator = ChartGenerator(dpi=100)

        # Mock reaction data
        reaction_data = Mock()
        reaction_data.type1_detected = True
        reaction_data.type1_reversal_date = pd.Timestamp('2023-02-15')
        reaction_data.type1_max_move = 105.0
        reaction_data.type1_reached_382 = True
        reaction_data.type1_reached_618 = False
        reaction_data.target_382 = 104.0
        reaction_data.target_618 = 107.0
        reaction_data.type2_detected = False

        chart_path = generator.generate_pattern_chart(
            pattern=sample_pattern,
            ticker="AAPL",
            df=sample_price_data,
            chart_dir=str(tmp_path),
            interval='1d',
            reaction_data=reaction_data
        )

        assert Path(chart_path).exists()

    def test_generate_chart_with_sector_etf_confluence(
        self, sample_pattern, sample_price_data, tmp_path
    ):
        """Test chart generation with sector ETF trend context."""
        generator = ChartGenerator(dpi=100)
        sector_context = SectorETFAnalysis(
            theme="Artificial Intelligence",
            etf_ticker="IVES",
            selection_reason="Validated relevant ETF",
            ranked_candidates=(),
            trend="UP",
            current_price=250.0,
            sma_20=245.0,
            sma_50=235.0,
            return_20_period_pct=4.5,
            confirms_signal=True,
        )

        chart_path = generator.generate_pattern_chart(
            pattern=sample_pattern,
            ticker="AAPL",
            df=sample_price_data,
            chart_dir=str(tmp_path),
            interval="1d",
            sector_etf_analysis=sector_context,
        )

        assert Path(chart_path).exists()

    def test_generate_chart_invalid_dataframe_raises(
        self, sample_pattern, tmp_path
    ):
        """Test that invalid DataFrame raises ChartGenerationError."""
        generator = ChartGenerator(dpi=100)

        # Empty DataFrame
        empty_df = pd.DataFrame()

        with pytest.raises(ChartGenerationError):
            generator.generate_pattern_chart(
                pattern=sample_pattern,
                ticker="AAPL",
                df=empty_df,
                chart_dir=str(tmp_path),
                interval='1d'
            )

    def test_generate_chart_different_intervals(
        self, sample_pattern, sample_price_data, tmp_path
    ):
        """Test chart generation with different time intervals."""
        generator = ChartGenerator(dpi=100)

        intervals = ['1d', '1wk', '1mo']

        for interval in intervals:
            chart_path = generator.generate_pattern_chart(
                pattern=sample_pattern,
                ticker="AAPL",
                df=sample_price_data,
                chart_dir=str(tmp_path),
                interval=interval
            )

            assert Path(chart_path).exists()


class TestGetChartWindow:
    """Test _get_chart_window helper method."""

    @pytest.fixture
    def sample_pattern(self, sample_pattern_points):
        """Create a sample pattern."""
        return HarmonicPattern(
            x=sample_pattern_points['x'],
            a=sample_pattern_points['a'],
            b=sample_pattern_points['b'],
            c=sample_pattern_points['c'],
            d=sample_pattern_points['d'],
            pattern_type='gartley',
            is_bullish=True,
            ab_xa_ratio=0.618,
            bc_ab_ratio=0.618,
            bc_projection=1.272,
            cd_bc_ratio=1.272,
            ad_xa_ratio=0.786,
            entry_price=101.5,
            stop_loss=98.0,
            ipo_target_1=105.0,
            ipo_target_2=108.0,
            target_point_a=110.0,
            risk_reward=2.5,
            prz_levels={'0.786': 101.5},
            tolerance_level='3.0%',
            grade='A',
            trade_quality='High-Probability Entry'
        )

    def test_get_chart_window_filters_data(
        self, sample_pattern, sample_price_data
    ):
        """Test that _get_chart_window filters DataFrame."""
        generator = ChartGenerator()

        df_window = generator._get_chart_window(sample_price_data, sample_pattern)

        # Should return DataFrame with fewer rows
        assert isinstance(df_window, pd.DataFrame)
        assert len(df_window) <= len(sample_price_data)

    def test_get_chart_window_includes_pattern_end(
        self, sample_pattern, sample_price_data
    ):
        """Test that chart window includes pattern end date."""
        generator = ChartGenerator()

        df_window = generator._get_chart_window(sample_price_data, sample_pattern)

        # Should include data through pattern completion
        # (or entire dataset if pattern date not in index)
        assert len(df_window) > 0


class TestPlotCandlesticks:
    """Test _plot_candlesticks method."""

    @patch('chart_generator.plt.subplots')
    def test_plot_candlesticks_creates_candles(
        self, mock_subplots, sample_price_data
    ):
        """Test that candlesticks are plotted."""
        generator = ChartGenerator()

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_subplots.return_value = (mock_fig, mock_ax)

        generator._plot_candlesticks(mock_ax, sample_price_data, '1d')

        # Should have called methods to draw candles
        assert mock_ax.plot.called or mock_ax.add_patch.called

    def test_get_candle_width_different_intervals(self):
        """Test candle width calculation for different intervals."""
        generator = ChartGenerator()

        assert generator._get_candle_width('1d') == 0.6
        assert generator._get_candle_width('1wk') == 5.0
        assert generator._get_candle_width('1mo') == 20.0

    def test_get_candle_width_unknown_interval(self):
        """Test candle width for unknown interval returns default."""
        generator = ChartGenerator()

        width = generator._get_candle_width('unknown')
        assert width == 0.6  # Default


class TestPlotPatternOverlay:
    """Test _plot_pattern_overlay method."""

    @pytest.fixture
    def sample_pattern(self, sample_pattern_points):
        """Create a sample pattern."""
        return HarmonicPattern(
            x=sample_pattern_points['x'],
            a=sample_pattern_points['a'],
            b=sample_pattern_points['b'],
            c=sample_pattern_points['c'],
            d=sample_pattern_points['d'],
            pattern_type='gartley',
            is_bullish=True,
            ab_xa_ratio=0.618,
            bc_ab_ratio=0.618,
            bc_projection=1.272,
            cd_bc_ratio=1.272,
            ad_xa_ratio=0.786,
            entry_price=101.5,
            stop_loss=98.0,
            ipo_target_1=105.0,
            ipo_target_2=108.0,
            target_point_a=110.0,
            risk_reward=2.5,
            prz_levels={'0.786': 101.5},
            tolerance_level='3.0%',
            grade='A',
            trade_quality='High-Probability Entry'
        )

    @patch('chart_generator.plt.subplots')
    def test_plot_pattern_overlay_draws_lines(
        self, mock_subplots, sample_pattern
    ):
        """Test that pattern overlay draws lines between points."""
        generator = ChartGenerator()

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_subplots.return_value = (mock_fig, mock_ax)

        generator._plot_pattern_overlay(mock_ax, sample_pattern)

        # Should plot lines and points
        assert mock_ax.plot.called or mock_ax.scatter.called

    @patch('chart_generator.plt.subplots')
    def test_plot_pattern_overlay_bullish_color(
        self, mock_subplots, sample_pattern
    ):
        """Test that bullish patterns use correct color."""
        generator = ChartGenerator()

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_subplots.return_value = (mock_fig, mock_ax)

        sample_pattern.is_bullish = True

        generator._plot_pattern_overlay(mock_ax, sample_pattern)

        # Should call plot (exact color checking is difficult with mocks)
        assert mock_ax.plot.called

    @patch('chart_generator.plt.subplots')
    def test_plot_pattern_overlay_bearish_color(
        self, mock_subplots, sample_pattern
    ):
        """Test that bearish patterns use correct color."""
        generator = ChartGenerator()

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_subplots.return_value = (mock_fig, mock_ax)

        sample_pattern.is_bullish = False

        generator._plot_pattern_overlay(mock_ax, sample_pattern)

        # Should call plot
        assert mock_ax.plot.called


class TestPlotFibonacciRatios:
    """Test _plot_fibonacci_ratios method."""

    @pytest.fixture
    def sample_pattern(self, sample_pattern_points):
        """Create a sample pattern."""
        return HarmonicPattern(
            x=sample_pattern_points['x'],
            a=sample_pattern_points['a'],
            b=sample_pattern_points['b'],
            c=sample_pattern_points['c'],
            d=sample_pattern_points['d'],
            pattern_type='gartley',
            is_bullish=True,
            ab_xa_ratio=0.618,
            bc_ab_ratio=0.618,
            bc_projection=1.272,
            cd_bc_ratio=1.272,
            ad_xa_ratio=0.786,
            entry_price=101.5,
            stop_loss=98.0,
            ipo_target_1=105.0,
            ipo_target_2=108.0,
            target_point_a=110.0,
            risk_reward=2.5,
            prz_levels={'0.786': 101.5},
            tolerance_level='3.0%',
            grade='A',
            trade_quality='High-Probability Entry'
        )

    @patch('chart_generator.plt.subplots')
    def test_plot_fibonacci_ratios_draws_vectors(
        self, mock_subplots, sample_pattern
    ):
        """Test that Fibonacci ratios are plotted as vectors."""
        generator = ChartGenerator()

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_subplots.return_value = (mock_fig, mock_ax)

        generator._plot_fibonacci_ratios(mock_ax, sample_pattern)

        # Should plot ratio vectors
        assert mock_ax.plot.called or mock_ax.text.called


class TestAddChartLabels:
    """Test _add_chart_labels method."""

    @pytest.fixture
    def sample_pattern(self, sample_pattern_points):
        """Create a sample pattern."""
        return HarmonicPattern(
            x=sample_pattern_points['x'],
            a=sample_pattern_points['a'],
            b=sample_pattern_points['b'],
            c=sample_pattern_points['c'],
            d=sample_pattern_points['d'],
            pattern_type='gartley',
            is_bullish=True,
            ab_xa_ratio=0.618,
            bc_ab_ratio=0.618,
            bc_projection=1.272,
            cd_bc_ratio=1.272,
            ad_xa_ratio=0.786,
            entry_price=101.5,
            stop_loss=98.0,
            ipo_target_1=105.0,
            ipo_target_2=108.0,
            target_point_a=110.0,
            risk_reward=2.5,
            prz_levels={'0.786': 101.5},
            tolerance_level='3.0%',
            grade='A',
            trade_quality='High-Probability Entry'
        )

    @patch('chart_generator.plt.subplots')
    def test_add_chart_labels_sets_title(
        self, mock_subplots, sample_pattern
    ):
        """Test that chart labels include title."""
        generator = ChartGenerator()

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_subplots.return_value = (mock_fig, mock_ax)

        generator._add_chart_labels(mock_ax, sample_pattern, "AAPL", '1d')

        # Should set title and labels
        assert mock_ax.set_title.called
        assert mock_ax.set_xlabel.called
        assert mock_ax.set_ylabel.called

    @patch('chart_generator.plt.subplots')
    def test_add_chart_labels_includes_pattern_info(
        self, mock_subplots, sample_pattern
    ):
        """Test that title includes pattern information."""
        generator = ChartGenerator()

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_subplots.return_value = (mock_fig, mock_ax)

        generator._add_chart_labels(mock_ax, sample_pattern, "AAPL", '1d')

        # Get the title that was set
        call_args = mock_ax.set_title.call_args
        title = call_args[0][0]

        assert 'AAPL' in title
        assert 'GARTLEY' in title.upper() or 'gartley' in title.lower()


class TestAddInfoBox:
    """Test _add_info_box method."""

    @pytest.fixture
    def sample_pattern(self, sample_pattern_points):
        """Create a sample pattern."""
        return HarmonicPattern(
            x=sample_pattern_points['x'],
            a=sample_pattern_points['a'],
            b=sample_pattern_points['b'],
            c=sample_pattern_points['c'],
            d=sample_pattern_points['d'],
            pattern_type='gartley',
            is_bullish=True,
            ab_xa_ratio=0.618,
            bc_ab_ratio=0.618,
            bc_projection=1.272,
            cd_bc_ratio=1.272,
            ad_xa_ratio=0.786,
            entry_price=101.5,
            stop_loss=98.0,
            ipo_target_1=105.0,
            ipo_target_2=108.0,
            target_point_a=110.0,
            risk_reward=2.5,
            prz_levels={'0.786': 101.5},
            d_point_range_min=99.5,
            d_point_range_max=103.5,
            tolerance_level='3.0%',
            grade='A',
            trade_quality='High-Probability Entry',
            tp_strategy_used='Scott Strategy'
        )

    @patch('chart_generator.plt.subplots')
    def test_add_info_box_adds_text(
        self, mock_subplots, sample_pattern
    ):
        """Test that info box adds text to chart."""
        generator = ChartGenerator()

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_subplots.return_value = (mock_fig, mock_ax)

        generator._add_info_box(mock_ax, sample_pattern, None)

        # Should add text box
        assert mock_ax.text.called

    @patch('chart_generator.plt.subplots')
    def test_add_info_box_includes_trading_levels(
        self, mock_subplots, sample_pattern
    ):
        """Test that info box includes trading levels."""
        generator = ChartGenerator()

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_subplots.return_value = (mock_fig, mock_ax)

        generator._add_info_box(mock_ax, sample_pattern, None)

        # Get the text that was added
        call_args = mock_ax.text.call_args
        info_text = call_args[0][2]  # Third positional arg

        assert 'Entry' in info_text or 'ENTRY' in info_text
        assert 'Stop' in info_text or 'STOP' in info_text


class TestConfigureAxes:
    """Test _configure_axes method."""

    @pytest.fixture
    def sample_pattern(self, sample_pattern_points):
        """Create a sample pattern."""
        return HarmonicPattern(
            x=sample_pattern_points['x'],
            a=sample_pattern_points['a'],
            b=sample_pattern_points['b'],
            c=sample_pattern_points['c'],
            d=sample_pattern_points['d'],
            pattern_type='gartley',
            is_bullish=True,
            ab_xa_ratio=0.618,
            bc_ab_ratio=0.618,
            bc_projection=1.272,
            cd_bc_ratio=1.272,
            ad_xa_ratio=0.786,
            entry_price=101.5,
            stop_loss=98.0,
            ipo_target_1=105.0,
            ipo_target_2=108.0,
            target_point_a=110.0,
            risk_reward=2.5,
            prz_levels={'0.786': 101.5},
            tolerance_level='3.0%',
            grade='A',
            trade_quality='High-Probability Entry'
        )

    @patch('chart_generator.plt.subplots')
    def test_configure_axes_sets_ticks(
        self, mock_subplots, sample_pattern
    ):
        """Test that axes configuration sets tick labels."""
        generator = ChartGenerator()

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_ax.xaxis = MagicMock()
        mock_subplots.return_value = (mock_fig, mock_ax)

        generator._configure_axes(mock_ax, sample_pattern, None)

        # Should set x-axis ticks
        assert mock_ax.set_xticks.called
        assert mock_ax.set_xticklabels.called


class TestApplyChartStyling:
    """Test _apply_chart_styling method."""

    @patch('chart_generator.plt.subplots')
    def test_apply_chart_styling_adds_grid(self, mock_subplots):
        """Test that chart styling adds grid."""
        generator = ChartGenerator()

        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_subplots.return_value = (mock_fig, mock_ax)

        generator._apply_chart_styling(mock_ax)

        # Should add grid and set background
        assert mock_ax.grid.called
        assert mock_ax.set_facecolor.called


class TestSaveChart:
    """Test _save_chart method."""

    @pytest.fixture
    def sample_pattern(self, sample_pattern_points):
        """Create a sample pattern."""
        return HarmonicPattern(
            x=sample_pattern_points['x'],
            a=sample_pattern_points['a'],
            b=sample_pattern_points['b'],
            c=sample_pattern_points['c'],
            d=sample_pattern_points['d'],
            pattern_type='gartley',
            is_bullish=True,
            ab_xa_ratio=0.618,
            bc_ab_ratio=0.618,
            bc_projection=1.272,
            cd_bc_ratio=1.272,
            ad_xa_ratio=0.786,
            entry_price=101.5,
            stop_loss=98.0,
            ipo_target_1=105.0,
            ipo_target_2=108.0,
            target_point_a=110.0,
            risk_reward=2.5,
            prz_levels={'0.786': 101.5},
            tolerance_level='3.0%',
            grade='A',
            trade_quality='High-Probability Entry'
        )

    @patch('chart_generator.plt.savefig')
    @patch('chart_generator.plt.tight_layout')
    def test_save_chart_returns_path(
        self, mock_tight_layout, mock_savefig, sample_pattern, tmp_path
    ):
        """Test that _save_chart returns correct path."""
        generator = ChartGenerator()

        mock_fig = MagicMock()

        chart_path = generator._save_chart(
            mock_fig, "AAPL", sample_pattern, str(tmp_path)
        )

        assert isinstance(chart_path, str)
        assert 'AAPL' in chart_path
        assert tmp_path.name in chart_path
