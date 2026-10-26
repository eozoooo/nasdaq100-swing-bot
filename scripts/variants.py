"""Étude de variantes avec validation hors échantillon.

Protocole (fixé AVANT de voir les résultats) :
  * les variantes ci-dessous sont définies à l'avance, une idée logique chacune ;
  * année 1 (in-sample) : on compare les variantes ;
  * année 2 (out-of-sample) : on ne regarde qu'une fois, pour vérifier que
    l'amélioration tient. Une variante n'est retenue que si elle bat la
    référence sur les DEUX périodes (profit factor et R moyen).

Usage : python scripts/variants.py   (lancé par le workflow "Real data test" avec --variants)
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import logging
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from backtest import compute_metrics, run_portfolio, simulate_ticker  # noqa: E402
from config import RISK, STRATEGY  # noqa: E402
from data import download_batch  # noqa: E402
from fundamentals import historical_earnings_dates  # noqa: E402
from strategy import compute_signals  # noqa: E402
from universe import get_universe  # noqa: E402

warnings.filterwarnings("ignore", module="yfinance")
log = logging.getLogger("variants")

# Référence = stratégie d'origine, sans aucun des trois filtres (indépendante des défauts de config.py)
BASE = {"exit_before_earnings": False, "adx_min": 0.0, "regime_qqq_sma50": False}
VARIANTS = {
    "V0 référence": {},
    "V1 sortie avant résultats": {"exit_before_earnings": True},
    "V2 tendance forte (ADX>=20)": {"adx_min": 20.0},
    "V3 régime strict (QQQ>SMA50)": {"regime_qqq_sma50": True},
    "V4 = V1+V2+V3": {"exit_before_earnings": True, "adx_min": 20.0, "regime_qqq_sma50": True},
}


def period_stats(trades, start, end) -> dict:
    sub = [t for t in trades if start <= t.entry_time < end]
    book, eq = run_portfolio(sub, RISK, max_positions=5)
    m = compute_metrics(book, eq, RISK.capital)
    if not m.get("trades"):
        return {"trades": 0}
    return {k: m[k] for k in ("trades", "winrate_%", "profit_factor", "avg_R", "total_return_%", "max_drawdown_%")}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    tickers = get_universe(refresh=True)
    end = dt.date.today() + dt.timedelta(days=1)
    h_start = end - dt.timedelta(days=729)
    daily = download_batch(tickers + ["QQQ"], start=(h_start - dt.timedelta(days=450)).isoformat(),
                           end=end.isoformat(), interval="1d")
    hourly = download_batch(tickers, start=h_start.isoformat(), end=end.isoformat(), interval="1h", chunk_size=25)
    earnings = {t: historical_earnings_dates(t) for t in tickers}
    qqq = daily["QQQ"]

    all_idx = pd.DatetimeIndex(sorted(set().union(*(h.index for h in hourly.values()))))
    mid = all_idx[0] + (all_idx[-1] - all_idx[0]) / 2
    periods = {"Année 1 (IS)": (all_idx[0], mid), "Année 2 (OOS)": (mid, all_idx[-1] + pd.Timedelta(hours=1))}

    rows = []
    for name, overrides in VARIANTS.items():
        p = dataclasses.replace(STRATEGY, **{**BASE, **overrides})
        trades = []
        for t in tickers:
            if t not in daily or t not in hourly or len(hourly[t]) < 200:
                continue
            sig = compute_signals(hourly[t], daily[t], qqq, p)
            trades += simulate_ticker(t, sig, hourly[t], p=p, earnings=earnings.get(t))
        for label, (a, b) in periods.items():
            rows.append({"variante": name, "période": label, **period_stats(trades, a, b)})
        log.info("%s : %d trades", name, len(trades))

    table = pd.DataFrame(rows).set_index(["variante", "période"])
    pd.set_option("display.width", 200)
    print("\n=== Variantes (portefeuille 5 positions, 1 % de risque, capital remis à zéro par période) ===")
    print(f"Coupure IS/OOS : {mid:%Y-%m-%d}")
    print(table.to_string())

    base = table.loc["V0 référence"]
    print("\n=== Verdict (règle fixée à l'avance) ===")
    for name in VARIANTS:
        if name == "V0 référence":
            continue
        v = table.loc[name]
        ok = all(
            v.loc[per, "profit_factor"] > base.loc[per, "profit_factor"] and v.loc[per, "avg_R"] > base.loc[per, "avg_R"]
            for per in periods
            if v.loc[per, "trades"] and base.loc[per, "trades"]
        )
        print(f"{name:<32} : {'RETENUE (bat la référence sur les 2 années)' if ok else 'rejetée'}")
    table.to_csv("variants_results.csv")


if __name__ == "__main__":
    main()
