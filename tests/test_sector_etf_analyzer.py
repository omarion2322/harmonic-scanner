"""Tests for relevant ETF selection and trend confluence."""

from unittest.mock import Mock

import numpy as np
import pandas as pd

from sector_etf_analyzer import SectorETFAnalyzer


def _price_data(closes: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {"Close": closes},
        index=pd.date_range("2024-01-01", periods=len(closes), freq="D"),
    )


def test_validated_match_uses_relevant_etf_and_confirms_buy():
    downloader = Mock(return_value=_price_data(np.linspace(100, 160, 80)))
    metadata_provider = Mock()
    holders_provider = Mock()
    analyzer = SectorETFAnalyzer(
        downloader,
        metadata_provider,
        holders_provider,
    )

    result = analyzer.analyze("CDZI", "BUY", "1d", "1y")

    assert result is not None
    assert result.etf_ticker == "CGW"
    assert result.theme == "Water Infrastructure"
    assert result.trend == "UP"
    assert result.confirms_signal is True
    metadata_provider.assert_not_called()
    holders_provider.assert_not_called()


def test_validated_match_confirms_sell_when_etf_trends_down():
    downloader = Mock(return_value=_price_data(np.linspace(160, 100, 80)))
    analyzer = SectorETFAnalyzer(downloader, Mock(), Mock())

    result = analyzer.analyze("CENX", "SELL", "1wk", "3y")

    assert result is not None
    assert result.etf_ticker == "XME"
    assert result.trend == "DOWN"
    assert result.confirms_signal is True


def test_validated_no_match_skips_etf_download():
    downloader = Mock()
    analyzer = SectorETFAnalyzer(downloader, Mock(), Mock())

    result = analyzer.analyze("INV", "BUY", "1d", "1y")

    assert result is None
    downloader.assert_not_called()


def test_verified_holder_beats_unverified_candidate_with_equal_theme_score():
    metadata = {
        "industry": "Biotechnology",
        "longBusinessSummary": "A clinical-stage biotechnology company.",
    }
    holders = pd.DataFrame([
        {
            "Holder": "iShares Trust-iShares Biotechnology ETF",
            "Value": 5_000_000,
        }
    ])
    analyzer = SectorETFAnalyzer(
        Mock(),
        Mock(return_value=metadata),
        Mock(return_value=holders),
    )

    selection = analyzer.select_relevant_etf("TEST", metadata)

    assert selection is not None
    assert selection[0] == "IBB"
    assert selection[3][0].verified_holder is True


def test_position_market_value_breaks_equal_theme_tie():
    metadata = {
        "industry": "Gold",
        "longBusinessSummary": "The company operates gold mines and produces gold.",
    }
    holders = pd.DataFrame([
        {"Holder": "VanEck ETF Trust-VanEck Gold Miners ETF", "Value": 20_000_000},
        {
            "Holder": "VanEck ETF Trust-VanEck Junior Gold Miners ETF",
            "Value": 10_000_000,
        },
    ])
    analyzer = SectorETFAnalyzer(
        Mock(),
        Mock(return_value=metadata),
        Mock(return_value=holders),
    )

    selection = analyzer.select_relevant_etf("TEST", metadata)

    assert selection is not None
    assert selection[0] == "GDX"


def test_metadata_theme_is_used_when_holder_list_is_incomplete():
    metadata = {
        "industry": "Communication Equipment",
        "longBusinessSummary": "Builds precision timing products for communication satellites.",
    }
    analyzer = SectorETFAnalyzer(
        Mock(),
        Mock(return_value=metadata),
        Mock(return_value=pd.DataFrame()),
    )

    selection = analyzer.select_relevant_etf("TEST", metadata)

    assert selection is not None
    assert selection[0] == "UFO"
    assert "holder list was incomplete" in selection[2]


def test_shell_company_returns_no_meaningful_match():
    metadata = {
        "industry": "Shell Companies",
        "longBusinessSummary": "Seeks a business combination with one or more businesses.",
    }
    analyzer = SectorETFAnalyzer(Mock(), Mock(), Mock())

    assert analyzer.select_relevant_etf("TEST", metadata) is None
