"""
Commodity Universe - Major commodity futures contracts
Used for harmonic pattern scanning on liquid, tradeable commodity instruments
"""

from typing import List


def get_all_commodities() -> List[str]:
    """
    Get comprehensive list of major commodity futures across all categories.

    Returns:
        List of commodity futures ticker symbols (Yahoo Finance format)
    """
    return get_commodity_universe(include_all=True)


def get_commodity_universe(
    include_precious_metals: bool = True,
    include_energy: bool = True,
    include_agriculture: bool = True,
    include_industrial_metals: bool = True,
    include_livestock: bool = True,
    include_softs: bool = True,
    include_all: bool = False
) -> List[str]:
    """
    Get commodity universe with granular control over categories.

    Args:
        include_precious_metals: Include gold, silver, platinum, palladium
        include_energy: Include crude oil, natural gas, heating oil, gasoline
        include_agriculture: Include corn, wheat, soybeans, rice, oats
        include_industrial_metals: Include copper, aluminum, zinc, nickel
        include_livestock: Include live cattle, lean hogs, feeder cattle
        include_softs: Include coffee, sugar, cotton, cocoa, orange juice
        include_all: Override all filters and include everything

    Returns:
        List of commodity futures ticker symbols based on selected categories
    """
    commodities = []

    # PRECIOUS METALS (4)
    if include_precious_metals or include_all:
        commodities.extend([
            'GC=F',  # Gold
            'SI=F',  # Silver
            'PL=F',  # Platinum
            'PA=F',  # Palladium
        ])

    # ENERGY (4)
    if include_energy or include_all:
        commodities.extend([
            'CL=F',  # Crude Oil WTI
            'BZ=F',  # Brent Crude Oil
            'NG=F',  # Natural Gas
            'RB=F',  # RBOB Gasoline
        ])

    # AGRICULTURE - GRAINS (5)
    if include_agriculture or include_all:
        commodities.extend([
            'ZC=F',  # Corn
            'ZW=F',  # Wheat
            'ZS=F',  # Soybeans
            'ZO=F',  # Oats
            'ZR=F',  # Rough Rice
        ])

    # INDUSTRIAL METALS (4)
    if include_industrial_metals or include_all:
        commodities.extend([
            'HG=F',  # Copper
            'ALI=F', # Aluminum
        ])

    # LIVESTOCK (3)
    if include_livestock or include_all:
        commodities.extend([
            'LE=F',  # Live Cattle
            'HE=F',  # Lean Hogs
            'GF=F',  # Feeder Cattle
        ])

    # SOFTS (5)
    if include_softs or include_all:
        commodities.extend([
            'KC=F',  # Coffee
            'SB=F',  # Sugar #11
            'CT=F',  # Cotton
            'CC=F',  # Cocoa
            'OJ=F',  # Orange Juice
        ])

    # Remove duplicates and sort
    commodities = sorted(list(set(commodities)))

    return commodities


def get_high_liquidity_commodities() -> List[str]:
    """
    Get only the highest liquidity commodity futures.
    Best for harmonic pattern trading.

    Returns:
        List of most liquid commodity futures ticker symbols
    """
    return [
        # Tier 1 - Mega Volume
        'GC=F',  # Gold
        'SI=F',  # Silver
        'CL=F',  # Crude Oil WTI
        'NG=F',  # Natural Gas

        # Tier 2 - High Volume
        'HG=F',  # Copper
        'ZC=F',  # Corn
        'ZW=F',  # Wheat
        'ZS=F',  # Soybeans
        'BZ=F',  # Brent Crude
        'PL=F',  # Platinum

        # Tier 3 - Good Volume
        'LE=F',  # Live Cattle
        'HE=F',  # Lean Hogs
        'KC=F',  # Coffee
        'SB=F',  # Sugar
        'CT=F',  # Cotton
    ]


def get_precious_metals_only() -> List[str]:
    """
    Get only precious metals commodity futures.

    Returns:
        List of precious metals ticker symbols
    """
    return [
        'GC=F',  # Gold
        'SI=F',  # Silver
        'PL=F',  # Platinum
        'PA=F',  # Palladium
    ]


def get_energy_only() -> List[str]:
    """
    Get only energy commodity futures.

    Returns:
        List of energy commodity ticker symbols
    """
    return [
        'CL=F',  # Crude Oil WTI
        'BZ=F',  # Brent Crude Oil
        'NG=F',  # Natural Gas
        'RB=F',  # RBOB Gasoline
    ]


if __name__ == "__main__":
    # Test the module
    print("All Commodities:", len(get_all_commodities()))
    print(f"Sample: {get_all_commodities()[:10]}")

    print("\nHigh Liquidity Commodities:", len(get_high_liquidity_commodities()))
    print(f"Sample: {get_high_liquidity_commodities()[:10]}")

    print("\nPrecious Metals only:", len(get_precious_metals_only()))
    print(f"Sample: {get_precious_metals_only()}")

    print("\nEnergy only:", len(get_energy_only()))
    print(f"Sample: {get_energy_only()}")

    print("\nCustom (metals + energy only):")
    custom = get_commodity_universe(
        include_precious_metals=True,
        include_energy=True,
        include_agriculture=False,
        include_industrial_metals=False,
        include_livestock=False,
        include_softs=False
    )
    print(f"Count: {len(custom)}")
    print(f"Tickers: {custom}")
