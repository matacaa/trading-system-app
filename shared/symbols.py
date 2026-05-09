"""
symbols.py
──────────
Universo de activos del sistema.
16 símbolos con soporte de OHLCV (yfinance) y noticias (Alpaca).
"""

from __future__ import annotations

ALL_SYMBOLS: dict[str, str] = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "JPM": "JPMorgan",
    "YPF": "YPF",
    "GGAL": "Galicia",
    "BBAR": "BBVA Argentina",
    "GLD": "SPDR Gold ETF",
    "SLV": "iShares Silver ETF",
    "USO": "US Oil ETF",
    "UNG": "US Natural Gas ETF",
    "DBA": "Agro Commodity ETF",
    "PDBC": "Invesco Commodity ETF",
    "GSG": "iShares GSCI ETF",
    "CPER": "Cobre ETF",
    "WEAT": "Trigo ETF",
    "SOYB": "Soja ETF",
}

CATEGORIES: dict[str, dict[str, str]] = {
    "acciones": {
        "AAPL": "Apple", "MSFT": "Microsoft", "JPM": "JPMorgan",
        "YPF": "YPF", "GGAL": "Galicia", "BBAR": "BBVA Argentina",
    },
    "materias_primas": {
        "GLD": "SPDR Gold ETF", "SLV": "iShares Silver ETF",
        "USO": "US Oil ETF", "UNG": "US Natural Gas ETF",
        "DBA": "Agro Commodity ETF", "PDBC": "Invesco Commodity ETF",
        "GSG": "iShares GSCI ETF", "CPER": "Cobre ETF",
        "WEAT": "Trigo ETF", "SOYB": "Soja ETF",
    },
}

SYMBOL_CATEGORY: dict[str, str] = {
    sym: cat for cat, syms in CATEGORIES.items() for sym in syms
}


def get_symbols(categories: list[str] | None = None) -> list[str]:
    """Devuelve lista de tickers filtrada por categoría."""
    if not categories:
        return list(ALL_SYMBOLS.keys())
    return [sym for cat in categories for sym in CATEGORIES.get(cat, {})]
