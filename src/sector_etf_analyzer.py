"""Relevant ETF selection and trend analysis for stock signal confluence."""

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

import pandas as pd

from data_downloader import download_stock_data
from logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ThemeRule:
    label: str
    keywords: Tuple[str, ...]
    etfs: Tuple[Tuple[str, int], ...]


@dataclass(frozen=True)
class ETFCandidate:
    ticker: str
    theme_score: int
    verified_holder: bool = False
    position_market_value: float = 0.0


@dataclass(frozen=True)
class SectorETFAnalysis:
    """Trend context for the most relevant ETF."""

    theme: str
    etf_ticker: str
    selection_reason: str
    ranked_candidates: Tuple[ETFCandidate, ...]
    trend: str
    current_price: float
    sma_20: float
    sma_50: float
    return_20_period_pct: float
    confirms_signal: bool

    @property
    def confluence_label(self) -> str:
        return "CONFIRMED" if self.confirms_signal else "NOT CONFIRMED"


VALIDATED_ETF_MATCHES: Dict[str, Optional[Tuple[str, str]]] = {
    "ADEA": ("VGT", "Information Technology"),
    "ALMU": ("WQTM", "Quantum Computing"),
    "ANAB": ("XBI", "Biotechnology"),
    "APLD": ("DTCR", "Data Centers & Digital Infrastructure"),
    "ASPI": ("NUKZ", "Nuclear Fuel & Energy"),
    "AUGO": ("GDX", "Gold Mining"),
    "AVR": ("XHE", "Health Care Equipment"),
    "BCAR": None,
    "BEAM": ("ARKG", "Genomics"),
    "CDZI": ("CGW", "Water Infrastructure"),
    "CENX": ("XME", "Metals & Mining"),
    "FEIM": ("UFO", "Space & Satellite Technology"),
    "FLNC": ("GRID", "Smart Grid & Energy Storage"),
    "GILT": ("UFO", "Space & Satellite Technology"),
    "GOSS": ("IBB", "Biotechnology"),
    "INOD": ("IVES", "Artificial Intelligence"),
    "INV": None,
    "JTAI": None,
    "LTBR": ("NUKZ", "Nuclear Fuel & Energy"),
}

THEME_RULES = (
    ThemeRule(
        "Water Infrastructure",
        ("water supply", "water storage", "water filtration", "wastewater"),
        (("CGW", 100), ("FIW", 95), ("PHO", 90)),
    ),
    ThemeRule(
        "Metals & Mining",
        ("aluminum", "alumina", "smelter", "bauxite"),
        (("XME", 100), ("PAVE", 70)),
    ),
    ThemeRule(
        "Space & Satellite Technology",
        ("satellite", "space-related", "spacecraft", "aerospace"),
        (("UFO", 100), ("UFOX", 95)),
    ),
    ThemeRule(
        "Smart Grid & Energy Storage",
        ("energy storage", "smart grid", "grid infrastructure", "electric grid"),
        (("GRID", 100), ("LIT", 85), ("ICLN", 75)),
    ),
    ThemeRule(
        "Biotechnology",
        ("biotechnology", "biopharmaceutical", "clinical-stage", "therapeutics"),
        (("XBI", 100), ("IBB", 100), ("VHT", 70)),
    ),
    ThemeRule(
        "Data Centers & Digital Infrastructure",
        ("data center", "digital infrastructure", "high-performance computing"),
        (("DTCR", 100), ("SRVR", 90)),
    ),
    ThemeRule(
        "Artificial Intelligence",
        ("artificial intelligence", "ai training", "machine learning", "model evaluation"),
        (("IVES", 100), ("AIQ", 90), ("BOTZ", 80)),
    ),
    ThemeRule(
        "Nuclear Fuel & Energy",
        ("nuclear fuel", "uranium", "haleu", "nuclear energy", "nuclear reactor"),
        (("NUKZ", 100), ("NLR", 95), ("URA", 95)),
    ),
    ThemeRule(
        "Gold Mining",
        ("gold production", "gold mine", "gold and copper", "gold deposits"),
        (("GDX", 100), ("GDXJ", 100)),
    ),
    ThemeRule(
        "Health Care Equipment",
        ("medical devices", "heart valve", "aortic valve", "medical instruments"),
        (("XHE", 100), ("IHI", 95)),
    ),
    ThemeRule(
        "Genomics",
        ("genetic medicine", "gene editing", "genomics", "gene therapy"),
        (("ARKG", 100), ("GNOM", 95), ("IDNA", 90)),
    ),
    ThemeRule(
        "Semiconductors",
        ("semiconductor", "optoelectronic", "microelectronics", "chips"),
        (("XSD", 100), ("SMH", 95), ("SOXX", 95), ("VGT", 75)),
    ),
    ThemeRule(
        "Quantum Computing",
        ("quantum computing", "quantum technology"),
        (("WQTM", 100), ("QTUM", 90)),
    ),
)

HOLDER_NAME_PATTERNS = (
    ("junior gold miners", "GDXJ"),
    ("gold miners etf", "GDX"),
    ("s&p biotech etf", "XBI"),
    ("ishares biotechnology etf", "IBB"),
    ("data center & digital infrastructure", "DTCR"),
    ("range nuclear renaissance", "NUKZ"),
    ("vaneck uranium and nuclear", "NLR"),
    ("global x uranium", "URA"),
    ("global water index etf", "CGW"),
    ("s&p metals & mining etf", "XME"),
    ("u.s. infrastructure development etf", "PAVE"),
    ("clean edge smart grid", "GRID"),
    ("procure space etf", "UFO"),
    ("space and connective tech etf", "UFOX"),
    ("ai revolution etf", "IVES"),
    ("genomic revolution etf", "ARKG"),
    ("health care equipment etf", "XHE"),
    ("medical devices etf", "IHI"),
    ("information technology index fund", "VGT"),
    ("quantum computing fund", "WQTM"),
)


class SectorETFAnalyzer:
    """Select and analyze the most relevant ETF for a stock."""

    def __init__(
        self,
        data_downloader: Callable[..., pd.DataFrame] = download_stock_data,
        metadata_provider: Optional[Callable[[str], Dict[str, object]]] = None,
        holders_provider: Optional[Callable[[str], pd.DataFrame]] = None,
    ) -> None:
        self.data_downloader = data_downloader
        self.metadata_provider = metadata_provider or self._fetch_yfinance_metadata
        self.holders_provider = holders_provider or self._fetch_yfinance_holders

    def analyze(
        self,
        ticker: str,
        signal: str,
        interval: str,
        period: str,
    ) -> Optional[SectorETFAnalysis]:
        """Select the relevant ETF and calculate its trend."""
        metadata = (
            {}
            if ticker in VALIDATED_ETF_MATCHES
            else self.metadata_provider(ticker)
        )
        selection = self.select_relevant_etf(ticker, metadata)
        if selection is None:
            logger.info("%s: No meaningful ETF match found", ticker)
            return None

        etf_ticker, theme, reason, ranked_candidates = selection
        etf_data = self.data_downloader(
            ticker=etf_ticker,
            period=period,
            interval=interval,
            auto_adjust=False,
        )
        if etf_data.empty:
            logger.warning("%s: No trend data available for relevant ETF %s", ticker, etf_ticker)
            return None

        close = self._get_close_series(etf_data)
        if len(close) < 50:
            logger.warning(
                "%s: Relevant ETF %s has only %d bars; 50 are required",
                ticker,
                etf_ticker,
                len(close),
            )
            return None

        sma_20_series = close.rolling(20).mean()
        sma_50_series = close.rolling(50).mean()
        current_price = float(close.iloc[-1])
        sma_20 = float(sma_20_series.iloc[-1])
        sma_50 = float(sma_50_series.iloc[-1])
        sma_20_prior = float(sma_20_series.iloc[-6])

        if current_price > sma_20 > sma_50 and sma_20 > sma_20_prior:
            trend = "UP"
        elif current_price < sma_20 < sma_50 and sma_20 < sma_20_prior:
            trend = "DOWN"
        else:
            trend = "MIXED"

        return_20_period_pct = float((current_price / close.iloc[-21] - 1) * 100)
        confirms_signal = (
            (signal == "BUY" and trend == "UP")
            or (signal == "SELL" and trend == "DOWN")
        )

        return SectorETFAnalysis(
            theme=theme,
            etf_ticker=etf_ticker,
            selection_reason=reason,
            ranked_candidates=ranked_candidates,
            trend=trend,
            current_price=current_price,
            sma_20=sma_20,
            sma_50=sma_50,
            return_20_period_pct=return_20_period_pct,
            confirms_signal=confirms_signal,
        )

    def select_relevant_etf(
        self,
        ticker: str,
        metadata: Dict[str, object],
    ) -> Optional[Tuple[str, str, str, Tuple[ETFCandidate, ...]]]:
        """Rank relevant ETF candidates before downloading price data."""
        if ticker in VALIDATED_ETF_MATCHES:
            validated = VALIDATED_ETF_MATCHES[ticker]
            if validated is None:
                return None
            etf_ticker, theme = validated
            candidate = ETFCandidate(etf_ticker, 100, True)
            return (
                etf_ticker,
                theme,
                "Validated relevant ETF",
                (candidate,),
            )

        quote_type = str(metadata.get("quoteType") or "").upper()
        if quote_type == "ETF":
            candidate = ETFCandidate(ticker, 100, True)
            return ticker, "ETF", "Signal asset is already an ETF", (candidate,)

        text = " ".join(
            str(metadata.get(field) or "")
            for field in ("sector", "industry", "industryKey", "longBusinessSummary")
        ).lower()
        if self._is_shell_company(text):
            return None

        matched_rules = [
            rule for rule in THEME_RULES
            if any(keyword in text for keyword in rule.keywords)
        ]
        if not matched_rules:
            return None

        candidate_map: Dict[str, ETFCandidate] = {}
        candidate_themes: Dict[str, str] = {}
        for rule in matched_rules:
            keyword_count = sum(keyword in text for keyword in rule.keywords)
            bonus = min(10, max(0, keyword_count - 1) * 2)
            for etf_ticker, base_score in rule.etfs:
                score = min(100, base_score + bonus)
                existing = candidate_map.get(etf_ticker)
                if existing is None or score > existing.theme_score:
                    candidate_map[etf_ticker] = ETFCandidate(etf_ticker, score)
                    candidate_themes[etf_ticker] = rule.label

        holders = self.holders_provider(ticker)
        if holders is not None and not holders.empty:
            for _, row in holders.iterrows():
                holder_ticker = self._resolve_holder_ticker(str(row.get("Holder") or ""))
                if holder_ticker not in candidate_map:
                    continue
                existing = candidate_map[holder_ticker]
                candidate_map[holder_ticker] = ETFCandidate(
                    ticker=holder_ticker,
                    theme_score=existing.theme_score,
                    verified_holder=True,
                    position_market_value=float(row.get("Value") or 0.0),
                )

        ranked_candidates = tuple(sorted(
            candidate_map.values(),
            key=lambda candidate: (
                candidate.verified_holder,
                candidate.theme_score,
                candidate.position_market_value,
            ),
            reverse=True,
        ))
        winner = ranked_candidates[0]
        theme = candidate_themes[winner.ticker]
        reason = (
            "Verified holder ranked by thematic relevance and position market value"
            if winner.verified_holder
            else "Metadata-ranked thematic ETF; holder list was incomplete"
        )
        return winner.ticker, theme, reason, ranked_candidates

    @staticmethod
    def _is_shell_company(text: str) -> bool:
        return (
            "shell companies" in text
            or "blank-check" in text
            or "business combination with one or more businesses" in text
        )

    @staticmethod
    def _resolve_holder_ticker(holder_name: str) -> Optional[str]:
        normalized = holder_name.lower()
        for pattern, ticker in HOLDER_NAME_PATTERNS:
            if pattern in normalized:
                return ticker
        return None

    @staticmethod
    def _fetch_yfinance_metadata(ticker: str) -> Dict[str, object]:
        try:
            import yfinance as yf

            return dict(yf.Ticker(ticker).info)
        except Exception as exc:
            logger.warning("%s: Could not fetch company metadata: %s", ticker, exc)
            return {}

    @staticmethod
    def _fetch_yfinance_holders(ticker: str) -> pd.DataFrame:
        try:
            import yfinance as yf

            holders = yf.Ticker(ticker).mutualfund_holders
            return holders if holders is not None else pd.DataFrame()
        except Exception as exc:
            logger.warning("%s: Could not fetch ETF holder candidates: %s", ticker, exc)
            return pd.DataFrame()

    @staticmethod
    def _get_close_series(df: pd.DataFrame) -> pd.Series:
        close_column = "close" if "close" in df.columns else "Close"
        return pd.to_numeric(df[close_column], errors="coerce").dropna()
