"""
ETF Universe - Leading ETFs across different categories
Used for harmonic pattern scanning on liquid, tradeable instruments
"""

from typing import List


def get_all_etfs() -> List[str]:
    """
    Get comprehensive list of leading ETFs across all categories.

    Returns:
        List of 135 ETF ticker symbols
    """
    return get_etf_universe(include_all=True)


def get_etf_universe(
    include_broad_market: bool = True,
    include_sector: bool = True,
    include_international: bool = True,
    include_bonds: bool = True,
    include_commodities: bool = True,
    include_leveraged: bool = False,  # Default False (risky)
    include_dividend: bool = True,
    include_thematic: bool = True,
    include_all: bool = False
) -> List[str]:
    """
    Get ETF universe with granular control over categories.

    Args:
        include_broad_market: Include broad market ETFs (SPY, QQQ, etc.)
        include_sector: Include sector ETFs (XLK, XLF, XLE, etc.)
        include_international: Include international/regional ETFs
        include_bonds: Include bond/fixed income ETFs
        include_commodities: Include commodity/precious metal ETFs
        include_leveraged: Include leveraged/inverse ETFs (3x bull/bear)
        include_dividend: Include dividend/income ETFs
        include_thematic: Include thematic/specialty ETFs
        include_all: Override all filters and include everything

    Returns:
        List of ETF ticker symbols based on selected categories
    """
    etfs = []

    # BROAD MARKET ETFs (10)
    if include_broad_market or include_all:
        etfs.extend([
            'SPY', 'QQQ', 'DIA', 'IWM', 'VTI', 'VOO', 'IVV', 'VT', 'ITOT', 'SCHB'
        ])

    # SECTOR ETFs (35)
    if include_sector or include_all:
        # Technology (12)
        etfs.extend([
            'XLK', 'VGT', 'SMH', 'SOXX', 'IGV', 'HACK', 'ARKK', 'ARKW',
            'FINX', 'WCLD', 'CLOU', 'ROBO'
        ])

        # Financial (6)
        etfs.extend([
            'XLF', 'VFH', 'KRE', 'KBE', 'IAI', 'FAS'
        ])

        # Healthcare (8)
        etfs.extend([
            'XLV', 'VHT', 'IHI', 'IBB', 'XBI', 'IHF', 'ARKG', 'XPH'
        ])

        # Consumer (8)
        etfs.extend([
            'XLY', 'VCR', 'XLP', 'VDC', 'XRT', 'RTH', 'PEJ', 'FXD'
        ])

        # Energy (7)
        etfs.extend([
            'XLE', 'VDE', 'XOP', 'OIH', 'ICLN', 'TAN', 'PBW'
        ])

        # Industrials & Materials (8)
        etfs.extend([
            'XLI', 'VIS', 'XLB', 'VAW', 'IYT', 'PAVE', 'ITB', 'XME'
        ])

        # Real Estate (5)
        etfs.extend([
            'XLRE', 'VNQ', 'IYR', 'SCHH', 'REM'
        ])

        # Utilities & Communication (5)
        etfs.extend([
            'XLU', 'VPU', 'XLC', 'VOX', 'FCOM'
        ])

    # INTERNATIONAL/REGIONAL ETFs (15)
    if include_international or include_all:
        etfs.extend([
            'EFA', 'VEA', 'EEM', 'VWO', 'IEMG', 'FXI', 'MCHI', 'EWJ',
            'EWZ', 'EWY', 'EWG', 'EWU', 'INDA', 'RSX', 'EWC'
        ])

    # BONDS & FIXED INCOME ETFs (10)
    if include_bonds or include_all:
        etfs.extend([
            'AGG', 'BND', 'TLT', 'IEF', 'SHY', 'LQD', 'HYG', 'JNK', 'MUB', 'TIP'
        ])

    # COMMODITIES & PRECIOUS METALS ETFs (8)
    if include_commodities or include_all:
        etfs.extend([
            'GLD', 'SLV', 'GDX', 'GDXJ', 'USO', 'UNG', 'DBA', 'DBC'
        ])

    # LEVERAGED & INVERSE ETFs (10) - High Risk
    if include_leveraged or include_all:
        etfs.extend([
            'TQQQ', 'SQQQ', 'UPRO', 'SPXU', 'TNA', 'TZA',
            'UDOW', 'SDOW', 'SOXL', 'SOXS'
        ])

    # DIVIDEND & INCOME ETFs (8)
    if include_dividend or include_all:
        etfs.extend([
            'VYM', 'SCHD', 'VIG', 'DGRO', 'DVY', 'SDY', 'HDV', 'NOBL'
        ])

    # GROWTH & VALUE ETFs (6)
    if include_sector or include_all:  # Included with sector
        etfs.extend([
            'VUG', 'IVW', 'VTV', 'IVE', 'MTUM', 'QUAL'
        ])

    # THEMATIC & SPECIALTY ETFs (9)
    if include_thematic or include_all:
        etfs.extend([
            'ARKF', 'ARQQ', 'BETZ', 'JETS', 'PBD', 'LIT',
            'DRIV', 'ESPO', 'UFO'
        ])

    # Remove duplicates and sort
    etfs = sorted(list(set(etfs)))

    return etfs


def get_high_liquidity_etfs() -> List[str]:
    """
    Get only the highest liquidity ETFs (Tier 1 + Tier 2).
    Best for harmonic pattern trading on weekly timeframes.

    Returns:
        List of ~30 most liquid ETF ticker symbols
    """
    return [
        # Tier 1 (Mega Volume)
        'SPY', 'QQQ', 'IWM', 'DIA', 'XLF', 'XLE', 'XLK', 'GLD', 'TLT', 'EEM',

        # Tier 2 (High Volume)
        'SMH', 'IBB', 'XBI', 'XRT', 'GDX', 'HYG', 'EFA', 'FXI', 'TQQQ', 'SQQQ',

        # Additional High Volume
        'XLV', 'XLY', 'XLP', 'XLI', 'XLRE', 'XLU', 'XLC', 'VTI', 'EWJ', 'AGG'
    ]


def get_sector_etfs_only() -> List[str]:
    """
    Get only sector ETFs (no broad market, no thematic).

    Returns:
        List of sector ETF ticker symbols
    """
    return [
        # Select Sector SPDRs
        'XLK', 'XLF', 'XLV', 'XLY', 'XLP', 'XLE', 'XLI', 'XLB', 'XLRE', 'XLU', 'XLC',

        # Vanguard Sector
        'VGT', 'VFH', 'VHT', 'VCR', 'VDC', 'VDE', 'VIS', 'VAW', 'VNQ', 'VPU',

        # Sub-sector specialists
        'SMH', 'SOXX', 'IBB', 'XBI', 'KRE', 'XRT', 'XOP', 'OIH', 'GDX', 'ITB'
    ]


if __name__ == "__main__":
    # Test the module
    print("All ETFs:", len(get_all_etfs()))
    print(f"Sample: {get_all_etfs()[:10]}")

    print("\nHigh Liquidity ETFs:", len(get_high_liquidity_etfs()))
    print(f"Sample: {get_high_liquidity_etfs()[:10]}")

    print("\nSector ETFs only:", len(get_sector_etfs_only()))
    print(f"Sample: {get_sector_etfs_only()[:10]}")

    print("\nCustom (no leveraged, no bonds):")
    custom = get_etf_universe(include_leveraged=False, include_bonds=False)
    print(f"Count: {len(custom)}")
