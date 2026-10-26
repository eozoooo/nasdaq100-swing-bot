"""Univers Nasdaq 100.

La composition change (rééquilibrage annuel en décembre + remplacements en
cours d'année). La liste statique sert de repli ; `get_universe()` tente
d'abord de la rafraîchir depuis Wikipedia.
GOOG est volontairement exclu (doublon de GOOGL).
Liste statique alignée sur Wikipedia le 26/10/2026. En production, main.py
rafraîchit la composition une fois par jour (au 1er passage de la journée).
"""
from __future__ import annotations

import io
import logging

import pandas as pd
import requests

log = logging.getLogger(__name__)

NASDAQ100_FALLBACK = [
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "ALAB", "ALNY", "AMAT",
    "AMD", "AMGN", "AMZN", "APP", "ARM", "ASML", "AVGO", "AXON", "BKNG", "BKR",
    "CCEP", "CDNS", "CEG", "CMCSA", "COST", "CPRT", "CRWD", "CRWV", "CSCO", "CSX",
    "CTAS", "DASH", "DDOG", "DXCM", "EXC", "FANG", "FAST", "FER", "FTNT", "GEHC",
    "GILD", "GOOGL", "HON", "HONA", "IDXX", "INTC", "INTU", "ISRG", "KDP", "KLAC",
    "LIN", "LITE", "LRCX", "MAR", "MCHP", "MDLZ", "MELI", "META", "MNST", "MPWR",
    "MRNA", "MRVL", "MSFT", "MSTR", "MU", "NBIS", "NFLX", "NVDA", "NXPI", "ODFL",
    "ORLY", "PANW", "PAYX", "PCAR", "PDD", "PEP", "PLTR", "PYPL", "QCOM", "REGN",
    "RKLB", "ROP", "ROST", "SBUX", "SHOP", "SNDK", "SNPS", "SPCX", "STX", "TER",
    "TMUS", "TRI", "TSLA", "TTWO", "TXN", "VRTX", "WDAY", "WDC", "WMT", "XEL",
]

# La composition a quitté la page "Nasdaq-100" pour une page dédiée
WIKI_URLS = [
    "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies",
    "https://en.wikipedia.org/wiki/List_of_Nasdaq-100_companies",
    "https://en.wikipedia.org/wiki/Nasdaq-100",
]


def _parse_components(html: str) -> list[str] | None:
    for table in pd.read_html(io.StringIO(html)):
        if isinstance(table.columns, pd.MultiIndex):
            table.columns = [" ".join(map(str, c)) for c in table.columns]
        for col in table.columns:
            name = str(col).strip().lower()
            if ("ticker" in name or "symbol" in name) and 90 <= len(table) <= 110:
                tickers = [str(t).strip().replace(".", "-") for t in table[col]]
                return sorted({t for t in tickers if t and t != "GOOG"})
    return None


def fetch_from_wikipedia(timeout: int = 15) -> list[str]:
    # Wikipedia refuse les User-Agent génériques : il faut un UA descriptif
    headers = {"User-Agent": "nasdaq100-swing-bot/1.0 (https://github.com/eozoooo/nasdaq100-swing-bot)"}
    errors = []
    for url in WIKI_URLS:
        try:
            resp = requests.get(url, timeout=timeout, headers=headers)
            resp.raise_for_status()
            tickers = _parse_components(resp.text)
            if tickers:
                return tickers
            errors.append(f"{url} : aucune table de composition")
        except Exception as exc:
            errors.append(f"{url} : {exc}")
    raise ValueError(" ; ".join(errors))


def get_universe(refresh: bool = False) -> list[str]:
    if refresh:
        try:
            tickers = fetch_from_wikipedia()
            log.info("Univers rafraîchi depuis Wikipedia : %d tickers", len(tickers))
            return tickers
        except Exception as exc:  # réseau, lxml absent, page modifiée...
            log.warning("Rafraîchissement Wikipedia impossible (%s), liste statique utilisée", exc)
    return list(NASDAQ100_FALLBACK)
