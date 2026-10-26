"""Univers Nasdaq 100.

La composition change (rééquilibrage annuel en décembre + remplacements en
cours d'année). La liste statique sert de repli ; `get_universe()` tente
d'abord de la rafraîchir depuis Wikipedia.
GOOG est volontairement exclu (doublon de GOOGL).
"""
from __future__ import annotations

import io
import logging

import pandas as pd
import requests

log = logging.getLogger(__name__)

NASDAQ100_FALLBACK = [
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "ALNY", "AMAT", "AMD",
    "AMGN", "AMZN", "APP", "ARM", "ASML", "AVGO", "AXON", "AZN", "BKNG", "BKR",
    "CCEP", "CDNS", "CEG", "CHTR", "CMCSA", "COST", "CPRT", "CRWD", "CSCO", "CSGP",
    "CSX", "CTAS", "CTSH", "DASH", "DDOG", "DXCM", "EA", "EXC", "FANG", "FAST",
    "FER", "FTNT", "GEHC", "GILD", "GOOGL", "HON", "IDXX", "INSM", "INTC", "INTU",
    "ISRG", "KDP", "KHC", "KLAC", "LIN", "LRCX", "MAR", "MCHP", "MDLZ", "MELI",
    "META", "MNST", "MPWR", "MRVL", "MSFT", "MSTR", "MU", "NFLX", "NVDA", "NXPI",
    "ODFL", "ORLY", "PANW", "PAYX", "PCAR", "PDD", "PEP", "PLTR", "PYPL", "QCOM",
    "REGN", "ROP", "ROST", "SBUX", "SHOP", "SNPS", "STX", "TEAM", "TMUS", "TRI",
    "TSLA", "TTWO", "TXN", "VRSK", "VRTX", "WBD", "WDAY", "WDC", "XEL", "ZS",
]

WIKI_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"


def fetch_from_wikipedia(timeout: int = 15) -> list[str]:
    # Wikipedia refuse les User-Agent génériques : il faut un UA descriptif
    headers = {"User-Agent": "nasdaq100-swing-bot/1.0 (https://github.com/eozoooo/nasdaq100-swing-bot)"}
    resp = requests.get(WIKI_URL, timeout=timeout, headers=headers)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    for table in tables:
        if isinstance(table.columns, pd.MultiIndex):
            table.columns = [" ".join(map(str, c)) for c in table.columns]
        for col in table.columns:
            if str(col).strip().lower() in ("ticker", "symbol") and 90 <= len(table) <= 110:
                tickers = [str(t).strip().replace(".", "-") for t in table[col]]
                return sorted({t for t in tickers if t and t != "GOOG"})
    shapes = [(len(t), list(t.columns)[:4]) for t in tables]
    raise ValueError(f"table Nasdaq-100 introuvable parmi {len(tables)} tables : {shapes}")


def get_universe(refresh: bool = False) -> list[str]:
    if refresh:
        try:
            tickers = fetch_from_wikipedia()
            log.info("Univers rafraîchi depuis Wikipedia : %d tickers", len(tickers))
            return tickers
        except Exception as exc:  # réseau, lxml absent, page modifiée...
            log.warning("Rafraîchissement Wikipedia impossible (%s), liste statique utilisée", exc)
    return list(NASDAQ100_FALLBACK)
