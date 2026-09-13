"""
Pydantic-based Configuration Management for Harmonic Trading System

This module provides type-safe, validated configuration using Pydantic BaseSettings.
Environment variables can be used with the HARMONIC_ prefix.

Example:
    export HARMONIC_DATA_INTERVAL=1wk
    export HARMONIC_ENABLE_PAPER_TRADING=true
"""

from typing import Optional, Literal, List
from pathlib import Path
from pydantic import BaseModel, Field, field_validator, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TimeframeConfig(BaseModel):
    """Timeframe-specific configuration settings."""
    model_config = SettingsConfigDict(frozen=True)

    swing_window: int = Field(4, ge=2, le=10, description="Swing point detection window")
    max_days_since_pattern: int = Field(7, ge=1, le=365, description="Max days allowed for the initial entry")
    max_bars_to_monitor_reaction: int = Field(
        30, ge=3, le=120, description="Bars to monitor for an ordered Type 2 reaction"
    )
    data_period: str = Field("5y", description="Historical data period")
    min_allowed_stop_loss_pct: float = Field(8.0, ge=1.0, le=30.0, description="Min stop loss percentage")
    max_allowed_stop_loss_pct: float = Field(15.0, ge=1.0, le=50.0, description="Max stop loss percentage")
    min_long_risk_reward_ratio: float = Field(10.0, ge=0.5, le=50.0, description="Min R/R for long trades")
    min_short_risk_reward_ratio: float = Field(4.0, ge=0.5, le=50.0, description="Min R/R for short trades")
    timeframe_notes: str = Field("", description="Trading style description")

    @field_validator('max_allowed_stop_loss_pct')
    @classmethod
    def validate_stop_loss_range(cls, v: float, info) -> float:
        """Ensure max_allowed_stop_loss_pct >= min_allowed_stop_loss_pct."""
        if 'min_allowed_stop_loss_pct' in info.data and v < info.data['min_allowed_stop_loss_pct']:
            raise ValueError(
                f'max_allowed_stop_loss_pct ({v}) must be >= min_allowed_stop_loss_pct ({info.data["min_allowed_stop_loss_pct"]})'
            )
        return v


class HarmonicTradingConfig(BaseSettings):
    """
    Main configuration for Harmonic Trading System with validation.

    Environment variables can override settings using HARMONIC_ prefix.
    Example: HARMONIC_DATA_INTERVAL=1wk
    """
    model_config = SettingsConfigDict(
        env_prefix='HARMONIC_',
        case_sensitive=False,
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )

    # ==================== TIMEFRAME SETTINGS ====================
    data_interval: Literal['1d', '3d', '1wk', '1mo'] = Field(
        '1wk',
        description="Trading timeframe"
    )

    # ==================== PATTERN DETECTION ====================
    pyharmonics_fib_tolerance: float = Field(
        0.01,
        ge=0.001,
        le=0.05,
        description="Fibonacci tolerance used only by the pyharmonics library for candidate discovery; Carney pattern ranges remain authoritative"
    )

    # ==================== PATTERN DURATION FILTERS ====================
    max_cd_to_xa_time_ratio: float = Field(5.0, ge=1.0, le=20.0)
    max_cd_to_ab_time_ratio: float = Field(10.0, ge=1.0, le=30.0)
    max_cd_to_bc_time_ratio: float = Field(8.0, ge=1.0, le=30.0)
    max_cd_to_xabc_time_ratio: float = Field(4.0, ge=1.0, le=20.0)
    max_total_pattern_duration_days: int = Field(2555, ge=365, le=7300)
    max_individual_leg_duration_days: int = Field(1460, ge=180, le=3650)
    enable_temporal_validation: bool = Field(True)

    # ==================== DATA SETTINGS ====================
    min_bars_required: int = Field(30, ge=10, le=200)

    # ==================== SCANNING SETTINGS ====================
    stocks_to_scan: Literal['All', 'SP500', 'None'] = Field('All')
    stock_tickers: List[str] = Field(
        default_factory=lambda: [
            'LAES', 'ONDS', 'RIVN', 'TIC', 'IQ', 'PANW', 'DOCU', 'LAC', 'URA',
            'FRSH', 'EVEX', 'SSYS', 'BULL', 'TGT', 'CROX', 'CLSK', 'TEAM',
            'REMX', 'SNDK', 'RGTI'
        ]
    )
    scan_etfs: bool = Field(True)
    scan_commodities: bool = Field(True)
    cryptos_to_scan: Optional[Literal['Top500', 'Top100', 'Top50', 'Top20']] = Field('Top500')

    filter_by_stock_volume: bool = Field(False)
    min_volume_usd: float = Field(1_000_000, ge=0)
    min_volume_stocks: float = Field(1_000_000, ge=0)
    max_stocks_to_scan: Optional[int] = Field(10000, ge=1)

    download_delay: float = Field(0.25, ge=0.0, le=5.0)
    max_download_retries: int = Field(3, ge=1, le=10)

    # ==================== CONFIRMATION SETTINGS ====================
    require_price_in_prz: bool = Field(
        True,
        description="HOLD if current price has already left the PRZ"
    )
    type2_retest_tolerance_pct: float = Field(2.0, ge=0.1, le=10.0)
    type2_entry_max_bars_after_confirmation: int = Field(1, ge=0, le=10)
    require_rsi_confirmation: bool = Field(False)
    rsi_oversold: int = Field(30, ge=0, le=100)
    rsi_overbought: int = Field(70, ge=0, le=100)
    require_volume_confirmation: bool = Field(False)
    volume_multiplier: float = Field(1.5, ge=1.0, le=10.0)

    # ==================== REPORTING SETTINGS ====================
    include_hold_in_report: bool = Field(False)
    verbose_reports: bool = Field(False)
    max_maturing_patterns_display_in_report: Optional[int] = Field(50, ge=1)
    auto_save_charts: bool = Field(True)
    chart_save_dir: str = Field('./charts')

    # ==================== RISK MANAGEMENT ====================
    max_pattern_age_days: int = Field(1850, ge=30, le=3650)

    # ==================== POSITION SIZING ====================
    position_size_t1: float = Field(0.20, ge=0.0, le=1.0)
    position_size_t2: float = Field(0.30, ge=0.0, le=1.0)
    position_size_t3: float = Field(0.50, ge=0.0, le=1.0)

    # ==================== TAKE PROFIT STRATEGY ====================
    tp_strategy: Literal['SCOTT', 'MITCH', 'POSITION'] = Field('MITCH')

    @field_validator('position_size_t1', 'position_size_t2', 'position_size_t3')
    @classmethod
    def validate_position_sizes(cls, v: float, info) -> float:
        """Validate position sizes sum to 1.0."""
        # This validator runs after all fields are set
        if all(k in info.data for k in ['position_size_t1', 'position_size_t2', 'position_size_t3']):
            total = info.data['position_size_t1'] + info.data['position_size_t2'] + info.data['position_size_t3']
            if abs(total - 1.0) > 0.001:
                raise ValueError(f'Position sizes must sum to 1.0, got {total}')
        return v

    @computed_field
    @property
    def timeframe_config(self) -> TimeframeConfig:
        """Get timeframe-specific configuration."""
        try:
            from .config_timeframes import get_timeframe_config
        except ImportError:
            # Handle case when running as script (not in package)
            import sys
            from pathlib import Path
            config_dir = Path(__file__).parent
            if str(config_dir) not in sys.path:
                sys.path.insert(0, str(config_dir))
            from config_timeframes import get_timeframe_config

        cfg = get_timeframe_config(self.data_interval)
        return TimeframeConfig(**{k.lower(): v for k, v in cfg.items()})

    @computed_field
    @property
    def swing_window(self) -> int:
        """Get swing window from timeframe config."""
        return self.timeframe_config.swing_window

    @computed_field
    @property
    def max_days_since_pattern(self) -> int:
        """Get max days since pattern from timeframe config."""
        return self.timeframe_config.max_days_since_pattern

    @computed_field
    @property
    def data_period(self) -> str:
        """Get data period from timeframe config."""
        return self.timeframe_config.data_period

    @computed_field
    @property
    def min_allowed_stop_loss_pct(self) -> float:
        """Get min allowed stop loss from timeframe config."""
        return self.timeframe_config.min_allowed_stop_loss_pct

    @computed_field
    @property
    def max_allowed_stop_loss_pct(self) -> float:
        """Get max allowed stop loss from timeframe config."""
        return self.timeframe_config.max_allowed_stop_loss_pct

    @computed_field
    @property
    def min_long_risk_reward_ratio(self) -> float:
        """Get min long risk/reward from timeframe config."""
        return self.timeframe_config.min_long_risk_reward_ratio

    @computed_field
    @property
    def min_short_risk_reward_ratio(self) -> float:
        """Get min short risk/reward from timeframe config."""
        return self.timeframe_config.min_short_risk_reward_ratio

    @computed_field
    @property
    def min_risk_reward_ratio(self) -> float:
        """Backward compatibility - returns min long R/R."""
        return self.min_long_risk_reward_ratio

    def get_stock_list(self) -> List[str]:
        """Get list of stocks, ETFs, and commodities to scan."""
        from data.stock_universe import get_stock_universe

        return get_stock_universe(
            stocks_to_scan=self.stocks_to_scan,
            etfs_to_scan=self.scan_etfs,
            commodities_to_scan=self.scan_commodities,
            max_stocks=self.max_stocks_to_scan,
            min_volume_usd=self.min_volume_usd,
            min_volume_stocks=self.min_volume_stocks,
            filter_by_stock_volume=self.filter_by_stock_volume,
            download_delay=self.download_delay,
            timeframe=self.data_interval,
            min_bars=self.min_bars_required
        )

    def get_crypto_list(self) -> List[str]:
        """Get list of cryptocurrencies to scan."""
        from data.crypto_universe import get_crypto_universe

        if self.cryptos_to_scan is None or self.cryptos_to_scan.upper() == 'NONE':
            return []

        return get_crypto_universe(
            cryptos_to_scan=self.cryptos_to_scan,
            min_volume_usd=self.min_volume_usd,
            download_delay=self.download_delay,
            timeframe=self.data_interval,
            min_bars=self.min_bars_required
        )


# Global configuration instance
_config: Optional[HarmonicTradingConfig] = None


def get_config() -> HarmonicTradingConfig:
    """
    Get the global configuration instance.

    Creates a new instance on first call, then returns the cached instance.
    """
    global _config
    if _config is None:
        _config = HarmonicTradingConfig()
    return _config


def reset_config() -> None:
    """Reset the global configuration (useful for testing)."""
    global _config
    _config = None


if __name__ == "__main__":
    # Test configuration
    config = get_config()

    print("="*70)
    print("HARMONIC TRADING CONFIGURATION")
    print("="*70)
    print(f"\nTimeframe: {config.data_interval}")
    print(f"Data Period: {config.data_period}")
    print(f"Swing Window: {config.swing_window}")
    print(f"Min Long R/R: {config.min_long_risk_reward_ratio}")
    print(f"Min Short R/R: {config.min_short_risk_reward_ratio}")
    print(f"Stop Loss Range: {config.min_allowed_stop_loss_pct}% - {config.max_allowed_stop_loss_pct}%")
    print(f"TP Strategy: {config.tp_strategy}")
    print(f"Position Sizing: T1={config.position_size_t1}, T2={config.position_size_t2}, T3={config.position_size_t3}")
    print("="*70)
