"""Filtres fondamentaux et calendrier des résultats.

Appelé UNIQUEMENT pour les rares titres qui viennent de déclencher un signal
technique : c'est la partie la plus coûteuse en requêtes Yahoo.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

import pandas as pd
import yfinance as yf

from config import FILTERS, FilterParams

log = logging.getLogger(__name__)


@dataclass
class FundamentalCheck:
    ticker: str
    name: str = ""
    next_earnings: dt.date | None = None
    days_to_earnings: int | None = None
    passed: bool = True
    reasons: list[str] = field(default_factory=list)   # motifs de rejet
    notes: list[str] = field(default_factory=list)     # infos affichées


def _next_earnings_date(tk: yf.Ticker, today: dt.date) -> dt.date | None:
    dates: list[dt.date] = []
    try:
        cal = tk.calendar or {}
        raw = cal.get("Earnings Date") if isinstance(cal, dict) else None
        for d in raw or []:
            dates.append(pd.Timestamp(d).date())
    except Exception as exc:
        log.debug("calendar %s: %s", tk.ticker, exc)
    if not dates:
        try:
            ed = tk.get_earnings_dates(limit=8)
            if ed is not None and len(ed):
                dates = [ts.date() for ts in ed.index]
        except Exception as exc:
            log.debug("earnings_dates %s: %s", tk.ticker, exc)
    future = sorted(d for d in dates if d >= today)
    return future[0] if future else None


def check_fundamentals(ticker: str, today: dt.date | None = None, f: FilterParams = FILTERS) -> FundamentalCheck:
    today = today or dt.date.today()
    tk = yf.Ticker(ticker)
    res = FundamentalCheck(ticker=ticker)

    # 1) Earnings : on n'entre pas juste avant une publication
    nxt = _next_earnings_date(tk, today)
    res.next_earnings = nxt
    if nxt is None:
        res.notes.append("Prochains résultats : date inconnue (vérifier manuellement)")
    else:
        res.days_to_earnings = (nxt - today).days
        if res.days_to_earnings <= f.earnings_blackout_days:
            res.passed = False
            res.reasons.append(f"résultats dans {res.days_to_earnings} j ({nxt:%d/%m})")
        else:
            res.notes.append(f"Prochains résultats : {nxt:%d/%m/%Y} (dans {res.days_to_earnings} j)")

    # 2) Qualité : élimine les bilans fragiles. Donnée absente = pas de rejet.
    try:
        info = tk.info or {}
    except Exception as exc:
        log.warning("info %s indisponible : %s", ticker, exc)
        info = {}
    res.name = info.get("shortName") or info.get("longName") or ticker

    fcf = info.get("freeCashflow")
    if f.require_positive_fcf and fcf is not None and fcf <= 0:
        res.passed = False
        res.reasons.append("free cash-flow négatif")
    op_margin = info.get("operatingMargins")
    if f.require_positive_operating_margin and op_margin is not None and op_margin <= 0:
        res.passed = False
        res.reasons.append(f"marge opérationnelle négative ({op_margin:.0%})")
    de = info.get("debtToEquity")
    if de is not None and de > f.max_debt_to_equity:
        res.passed = False
        res.reasons.append(f"dette/fonds propres {de / 100:.1f}x")

    bits = []
    if fcf is not None:
        bits.append(f"FCF {fcf / 1e9:+.1f} Md$")
    if op_margin is not None:
        bits.append(f"marge op. {op_margin:.0%}")
    if de is not None:
        bits.append(f"D/E {de / 100:.1f}x")
    if bits:
        res.notes.append("Fondamentaux : " + ", ".join(bits))
    return res


def historical_earnings_dates(ticker: str, limit: int = 16) -> list[dt.date]:
    """Dates de résultats passées (pour le backtest)."""
    try:
        ed = yf.Ticker(ticker).get_earnings_dates(limit=limit)
        if ed is None or not len(ed):
            return []
        return sorted({ts.date() for ts in ed.index})
    except Exception as exc:
        log.debug("earnings_dates %s: %s", ticker, exc)
        return []
