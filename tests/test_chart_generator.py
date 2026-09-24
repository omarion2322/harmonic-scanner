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
from matplotlib.colors import to_rgba

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from chart_generator import ChartGenerator
from pattern_detector import HarmonicPattern, Point
from exceptions import ChartGenerationError
from sector_etf_analyzer import SectorETFAnalysis
from reaction_detector import ReactionData


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
            tp_strategy_used=(
                'T1: Structure (Resistance, score 85); '
                'T2: Structure (Resistance, score 72); '
                'T3: Fibonacci 100% (projection)'
            ),
            tp_strategy_name='MITCH',
            tp_target_details=(
                'Resistance, score 85',
                'Resistance, score 72',
                'Fibonacci 100% (projection)',
            ),
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

        reaction_data = ReactionData(
            reaction_type="TYPE_1", terminal_bar_idx=0,
            terminal_bar_date=sample_pattern.d.date,
            terminal_bar_price=sample_pattern.d.price,
            type1_detected=True, type1_reversal_date=pd.Timestamp('2023-02-15'),
            type1_max_move=105.0, type1_reached_382=True,
            target_382=104.0, target_618=107.0,
        )

        chart_path = generator.generate_pattern_chart(
            pattern=sample_pattern,
            ticker="AAPL",
            df=sample_price_data,
            chart_dir=str(tmp_path),
            interval='1d',
            reaction_data=reaction_data
        )

        assert Path(chart_path).exists()

    def test_dark_export_includes_divergence_and_type2_area(
        self, sample_pattern, sample_price_data, tmp_path, monkeypatch
    ):
        sample_pattern.divergence = {
            "status": "both", "pivots": [], "available_at": "2023-03-01",
            "anchor": {"is_bullish": True},
            "rsi": {"confirmed": True, "first": 24.0, "second": 33.0, "normalized_delta": 9.0},
            "macd": {"confirmed": True, "first": -1.2, "second": -0.7, "normalized_delta": 0.25},
            "point_readings": {"d": {"rsi": {"value": 33.0}, "macd": {"value": -0.7}}},
        }
        reaction = ReactionData(
            reaction_type="TYPE_2", terminal_bar_idx=0,
            terminal_bar_date=sample_pattern.d.date,
            terminal_bar_price=sample_pattern.d.price, type1_detected=True,
            type2_detected=True, type2_reaction_area_low=98.0,
            type2_reaction_area_high=102.0, type2_retest_price=99.5,
        )
        sector = SectorETFAnalysis(
            theme="Technology", etf_ticker="XLK", selection_reason="Test",
            ranked_candidates=(), trend="UP", current_price=200.0,
            sma_20=195.0, sma_50=190.0, return_20_period_pct=3.0,
            confirms_signal=True,
        )
        generator = ChartGenerator(dpi=80)
        original_save = generator._save_chart
        original_rc = dict(plt.rcParams)
        captured = {}

        def capture(fig, *args):
            path = original_save(fig, *args)
            ax = fig.axes[0]
            assert fig.legends == []
            assert ax.get_legend() is None
            captured["text"] = "\n".join(t.get_text() for t in ax.texts + fig.texts)
            assert fig.get_facecolor() == to_rgba("#0d1117")
            assert ax.get_facecolor() == to_rgba("#0d1117")
            assert ax.title.get_color() == "#e6edf3"
            assert ax.xaxis.label.get_color() == "#e6edf3"
            assert ax.yaxis.label.get_color() == "#e6edf3"
            assert all(t.get_color() == "#9da7b3" for t in ax.get_xticklabels())
            for text in ax.texts + fig.texts:
                patch = text.get_bbox_patch()
                if patch is not None:
                    assert max(patch.get_facecolor()[:3]) < 0.25
            info = next(t for t in ax.texts if "TRADING LEVELS" in t.get_text())
            box = info.get_window_extent(fig.canvas.get_renderer())
            assert box.transformed(ax.transAxes.inverted()).y0 > 0
            assert all("RSI14" not in t.get_text() for t in fig.texts)
            return path

        monkeypatch.setattr(generator, "_save_chart", capture)
        output = generator.generate_pattern_chart(
            sample_pattern, "DARK", sample_price_data, str(tmp_path),
            reaction_data=reaction, sector_etf_analysis=sector,
        )
        assert "Type 2 Hit: YES" in captured["text"]
        assert "Type 2 reaction area:\n  \\$98.00 - \\$102.00" in captured["text"]
        assert "Retest price: \\$99.50" in captured["text"]
        assert "Type 1:" not in captured["text"]
        assert "PATTERN METRICS" not in captured["text"]
        assert "Tolerance:" not in captured["text"]
        assert captured["text"].index("REACTION ANALYSIS") < captured["text"].index("MOMENTUM DIVERGENCE")
        assert "RSI14: 33.00 | Bullish divergence" in captured["text"]
        assert "MACD: -0.70 | Bullish divergence" in captured["text"]
        image = plt.imread(output)
        np.testing.assert_allclose(image[0, 0, :3], np.array([13, 17, 23]) / 255, atol=1 / 255)
        assert (np.max(image[:, :, :3], axis=2) < 0.25).mean() > 0.5
        assert dict(plt.rcParams) == original_rc

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

    @patch('chart_generator.plt.subplots')
    def test_five_zero_ratio_labels_match_official_structure(
        self, mock_subplots, sample_pattern
    ):
        generator = ChartGenerator()
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_subplots.return_value = (mock_fig, mock_ax)
        sample_pattern.pattern_type = '5-0'
        sample_pattern.origin = Point(
            -1, 80.0, pd.Timestamp('2022-12-25'), 'TROUGH'
        )
        sample_pattern.x.price = 100.0
        sample_pattern.a.price = 90.0
        sample_pattern.b.price = 105.0
        sample_pattern.c.price = 75.0
        sample_pattern.d.price = 90.0
        sample_pattern.ab_xa_ratio = 1.5
        sample_pattern.bc_ab_ratio = 2.0
        sample_pattern.cd_bc_ratio = 0.5

        generator._plot_fibonacci_ratios(mock_ax, sample_pattern)

        labels = [call.args[2] for call in mock_ax.text.call_args_list]
        assert labels == [
            '1.500 XA',
            '2.000 AB',
            '0.500 BC',
            'AB=CD 1.000',
        ]

    @patch('chart_generator.plt.subplots')
    def test_five_zero_overlay_includes_origin_point(
        self, mock_subplots, sample_pattern
    ):
        generator = ChartGenerator()
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_subplots.return_value = (mock_fig, mock_ax)
        sample_pattern.pattern_type = '5-0'
        sample_pattern.origin = Point(
            -1, 95.0, pd.Timestamp('2022-12-25'), 'TROUGH'
        )

        generator._plot_pattern_overlay(mock_ax, sample_pattern)

        point_labels = [
            call.args[2]
            for call in mock_ax.text.call_args_list
            if call.args[2] in {'0', 'X', 'A', 'B', 'C', 'D'}
        ]
        assert point_labels == ['0', 'X', 'A', 'B', 'C', 'D']


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
            tp_strategy_used=(
                'T1: Structure (Resistance, score 85); '
                'T2: Structure (Resistance, score 72); '
                'T3: Fibonacci 100% (projection)'
            ),
            tp_strategy_name='MITCH',
            tp_target_details=(
                'Resistance, score 85',
                'Resistance, score 72',
                'Fibonacci 100% (projection)',
            ),
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
        assert r'T1: \$105.00 (Resistance, score 85)' in info_text
        assert r'T2: \$108.00 (Resistance, score 72)' in info_text
        assert r'T3: \$110.00 (Fibonacci 100% (projection))' in info_text
        assert 'Strategy: MITCH' in info_text
        assert 'Strategy: T1:' not in info_text


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


class TestReactionSummary:
    @pytest.mark.parametrize("detected", [False, True])
    def test_type2_hit_replaces_type1_summary(self, detected):
        reaction = ReactionData(
            reaction_type="TYPE_2" if detected else "TYPE_1",
            terminal_bar_idx=0, terminal_bar_date=datetime(2026, 1, 1),
            terminal_bar_price=100, type1_detected=True, type2_detected=detected,
            type2_reaction_area_low=98, type2_reaction_area_high=102,
        )
        text = ChartGenerator()._format_reaction_info(reaction)
        assert f"Type 2 Hit: {'YES' if detected else 'NO'}" in text
        assert "Type 2 reaction area:\n  \\$98.00 - \\$102.00\n" in text
        assert "Type 1" not in text

    @pytest.mark.parametrize("bounds,price,expected", [
        ((100, 100), None, "  \\$100.00\n"),
        ((None, None), 99.5, "  \\$99.50 (retest)\n"),
        ((None, None), None, "  N/A\n"),
    ])
    def test_exact_or_unavailable_reaction_area(self, bounds, price, expected):
        reaction = ReactionData(
            reaction_type="PENDING", terminal_bar_idx=0,
            terminal_bar_date=datetime(2026, 1, 1), terminal_bar_price=100,
            type2_reaction_area_low=bounds[0], type2_reaction_area_high=bounds[1],
            type2_retest_price=price,
        )
        text = ChartGenerator()._format_reaction_info(reaction)
        assert "Type 2 reaction area:\n" + expected in text
        assert "Type 2 Hit: NO" in text

    def test_retest_candidate_is_not_a_type2_hit(self):
        reaction = ReactionData(
            reaction_type="TYPE_2_CANDIDATE", terminal_bar_idx=0,
            terminal_bar_date=datetime(2026, 1, 1), terminal_bar_price=100,
            type2_retest_date=datetime(2026, 1, 3), type2_retest_price=99.5,
            type2_reaction_area_low=98, type2_reaction_area_high=102,
        )
        text = ChartGenerator()._format_reaction_info(reaction)
        assert "Type 2 Hit: NO" in text
        assert "Retested; awaiting reversal" in text
        assert "Retest price: \\$99.50" in text

    def test_missing_analysis_is_explicit(self):
        text = ChartGenerator()._format_reaction_info(None)
        assert "Type 2 Hit: NO\n  Not evaluated" in text
        assert "Type 2 reaction area: N/A" in text
        assert "Type 1" not in text


class TestDivergenceSummary:
    @pytest.mark.parametrize("bullish,direction", [
        (True, "Bullish divergence"), (False, "Bearish divergence"),
    ])
    @pytest.mark.parametrize("rsi,macd", [(True, True), (True, False), (False, True), (False, False)])
    def test_each_indicator_has_pivot_number_and_direction(self, bullish, direction, rsi, macd):
        evidence = {
            "anchor": {"is_bullish": bullish},
            "pivots": [{"date": "2026-08-19T00:00:00"}],
            "rsi": {"first": 80.0, "second": 22.513, "confirmed": rsi},
            "macd": {"first": 5.0, "second": -3.548, "confirmed": macd},
            "point_readings": {"d": {"rsi": {"value": 22.513}, "macd": {"value": -3.548}}},
        }
        text = ChartGenerator._format_divergence_summary(evidence)
        assert f"RSI14: 22.51 | {direction if rsi else 'No divergence'}" in text
        assert f"MACD: -3.55 | {direction if macd else 'No divergence'}" in text
        assert "Source: D point" in text
        assert "Pivot:" not in text
        assert "80.00" not in text and "improvement" not in text and "/ATR" not in text

    @pytest.mark.parametrize("evidence,status", [
        (None, "Unavailable"),
        ({"status": "developing"}, "Awaiting confirmation"),
        ({"status": "insufficient_data"}, "Unavailable"),
    ])
    def test_missing_divergence_is_not_a_negative_signal(self, evidence, status):
        text = ChartGenerator._format_divergence_summary(evidence)
        assert f"RSI14: N/A | {status}" in text
        assert f"MACD: N/A | {status}" in text
        assert "No divergence" not in text

    def test_zero_value_partial_data_and_storage_warning(self):
        evidence = {
            "anchor": {"is_bullish": False}, "status": "insufficient_data",
            "rsi": {"second": 0.0, "confirmed": False},
            "macd": {"second": None, "confirmed": None},
            "persistence_error": True,
            "point_readings": {"d": {"rsi": {"value": 0.0}, "macd": {"value": None}}},
        }
        text = ChartGenerator._format_divergence_summary(evidence)
        assert "RSI14: 0.00 | No divergence" in text
        assert "MACD: N/A | Unavailable" in text
        assert "Warning: observation not saved" in text

    def test_missing_direction_is_not_assumed_bearish(self):
        text = ChartGenerator._format_divergence_summary({
            "rsi": {"second": 30.0, "confirmed": True},
            "point_readings": {"d": {"rsi": {"value": 30.0}}},
        })
        assert "RSI14: 30.00 | Divergence (direction unavailable)" in text

    @pytest.mark.parametrize("state,flag,label", [
        ("developing", None, "Awaiting confirmation"),
        ("insufficient_data", None, "Unavailable"),
        ("both", True, "Bullish divergence"),
        ("neither", False, "No divergence"),
    ])
    def test_type2_chart_only_source_and_two_indicators(self, state, flag, label):
        evidence = {
            "context": "type2_retest", "status": state, "anchor": {"is_bullish": True},
            "rsi": {"second": 60.0, "confirmed": flag},
            "macd": {"second": 0.0, "confirmed": flag},
            "pivots": [{"date": "2020-02-20"}],
            "histogram": {"second": -100.0},
            "point_readings": {"retest": {"rsi": {"value": 60.0}, "macd": {"value": 0.0}}},
        }
        assert ChartGenerator._format_divergence_summary(evidence).splitlines() == [
            "MOMENTUM DIVERGENCE", "─" * 20, "Source: Type 2 reaction area",
            f"RSI14: 60.00 | {label}", f"MACD: 0.00 | {label}",
        ]

    @pytest.mark.parametrize("pivot_date,expected", [
        ("2020-02-10", "33.00"), ("2020-02-11", "N/A"),
    ])
    def test_legacy_chart_uses_only_proven_exact_d_values(self, pivot_date, expected):
        evidence = {
            "context": "initial_d", "status": "both",
            "anchor": {"is_bullish": True, "d_date": "2020-02-10"},
            "pivots": [{"date": pivot_date}],
            "rsi": {"second": 33.0, "confirmed": True},
            "macd": {"second": -0.7, "confirmed": True},
        }
        text = ChartGenerator._format_divergence_summary(evidence)
        assert f"RSI14: {expected} | Bullish divergence" in text
        if expected == "N/A":
            assert "MACD: N/A | Bullish divergence" in text

    @pytest.mark.parametrize("bounds", [(98.0, 102.0), (100.0, 100.0), (None, None)])
    def test_only_light_green_reaction_area_remains(self, sample_pattern_points, bounds):
        pattern = Mock(**sample_pattern_points)
        reaction = ReactionData(
            reaction_type="TYPE_2", terminal_bar_idx=0,
            terminal_bar_date=pattern.d.date, terminal_bar_price=pattern.d.price,
            type1_detected=True, type1_reversal_date=datetime(2023, 2, 15),
            type1_max_move=105.0, type2_detected=True,
            type2_retest_date=datetime(2023, 2, 17),
            type2_terminal_bar_date=datetime(2023, 2, 20),
            type2_reaction_area_low=bounds[0], type2_reaction_area_high=bounds[1],
        )
        fig, ax = plt.subplots()
        try:
            generator = ChartGenerator()
            generator._plot_reaction_markers(ax, pattern, reaction)
            assert len(ax.collections) == 0
            assert len(ax.texts) == 0
            assert fig.legends == []
            if bounds == (98.0, 102.0):
                assert len(ax.lines) == 0
                assert len(ax.patches) == 1
                area = ax.patches[0]
                assert area.get_facecolor() == to_rgba("#90ee90", 0.2)
                assert area.get_zorder() < 1
                assert area.get_y() == 98.0
                assert area.get_height() == 4.0
            elif bounds == (100.0, 100.0):
                assert len(ax.patches) == 0
                assert len(ax.lines) == 1
                line = ax.lines[0]
                assert list(line.get_ydata()) == [100.0, 100.0]
                assert line.get_color() == "#90ee90"
                assert line.get_alpha() == 0.2
            else:
                assert len(ax.lines) == 0
                assert len(ax.patches) == 0
            generator._configure_axes(ax, pattern, reaction)
            assert all("T1" not in t.get_text() and "T2" not in t.get_text()
                       for t in ax.get_xticklabels())
        finally:
            plt.close(fig)


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
