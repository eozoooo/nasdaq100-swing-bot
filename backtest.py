"""Backtest de la stratégie sur ~2 ans de données 1H + Daily du Nasdaq 100.

Usage :
    python backtest.py                         # univers complet, filtre earnings activé
    python backtest.py --no-earnings           # sans filtre earnings (plus rapide)
    python backtest.py --tickers NVDA MSFT --capital 10000 --risk 0.005

Limite Yahoo : l'historique 1H est limité à ~730 jours, d'où "2 ans".

Hypothèses (volontairement prudentes) :
  * entrée à la clôture de la bougie 1H du signal + slippage ;
  * si stop et objectif sont touchés dans la même bougie, on suppose le stop ;
  * gap sous le stop -> sortie au prix d'ouverture (pire que le stop) ;
  * TP1 (2R) : 50 % vendus, stop remonté au prix d'entrée ; TP2 (3R) : solde ;
  * stop temporel après N séances ;
  * une seule position par titre, max N positions simultanées, capital composé ;
  * fondamentaux NON testés (pas de données point-in-time gratuites) ;
  * biais du survivant : on teste la composition ACTUELLE du Nasdaq 100.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import math
from dataclasses import dataclass, field, fields

import numpy as np
import pandas as pd

from config import RISK, STRATEGY, RiskParams, StrategyParams
from data import NY_TZ, download_batch
from strategy import compute_signals
from universe import get_universe

log = logging.getLogger("backtest")
BARS_PER_DAY = 7  # 9:30, 10:30, ..., 15:30


@dataclass
class Trade:
    ticker: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry: float
    stop: float
    exit_price: float      # prix moyen de sortie (pondéré TP1 / solde)
    r_multiple: float      # gain en multiples du risque initial
    exit_reason: str
    bars_held: int
    # P&L latent par action à chaque clôture 1H (pour un drawdown mark-to-market)
    path: pd.Series = field(default=None, repr=False)

    def as_row(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name != "path"}


# --------------------------------------------------------------------------- #
# Simulation d'un titre (indépendante du capital)
# --------------------------------------------------------------------------- #
def simulate_ticker(
    ticker: str,
    sig: pd.DataFrame,
    hourly: pd.DataFrame,
    p: StrategyParams = STRATEGY,
    slippage: float = 0.0005,
    earnings: list[dt.date] | None = None,
    blackout_days: int = 7,
) -> list[Trade]:
    opens = hourly["Open"].to_numpy(float)
    highs = hourly["High"].to_numpy(float)
    lows = hourly["Low"].to_numpy(float)
    closes = hourly["Close"].to_numpy(float)
    idx = hourly.index
    signal = sig["signal"].reindex(idx).fillna(False).to_numpy(bool)
    stops = sig["stop"].reindex(idx).to_numpy(float)
    sessions = idx.tz_convert(NY_TZ).date
    earn = np.array(sorted(earnings or []), dtype="datetime64[D]")
    max_bars = p.max_holding_days * BARS_PER_DAY

    trades: list[Trade] = []
    i, n = 0, len(idx)
    while i < n - 1:
        if not signal[i] or not np.isfinite(stops[i]):
            i += 1
            continue
        if len(earn):
            d = np.datetime64(sessions[i], "D")
            nxt = earn[earn >= d]
            if len(nxt) and (nxt[0] - d).astype(int) <= blackout_days:
                i += 1
                continue

        entry = closes[i] * (1 + slippage)
        stop = stops[i]
        risk = entry - stop
        if risk <= 0:
            i += 1
            continue
        tp1, tp2 = entry + p.tp1_r * risk, entry + p.tp2_r * risk
        remaining, realized = 1.0, 0.0
        cur_stop, tp1_hit = stop, False
        reason, j = "time", i
        marks = []
        for j in range(i + 1, min(i + 1 + max_bars, n)):
            o, hi, lo = opens[j], highs[j], lows[j]
            # 1) le stop d'abord (hypothèse prudente)
            if lo <= cur_stop:
                px = min(o, cur_stop) * (1 - slippage)
                realized += remaining * (px - entry)
                remaining = 0.0
                reason = "breakeven" if tp1_hit else "stop"
                break
            if not tp1_hit and hi >= tp1:
                px = max(o, tp1) * (1 - slippage)
                realized += p.tp1_fraction * (px - entry)
                remaining -= p.tp1_fraction
                tp1_hit, cur_stop = True, max(cur_stop, entry)
            if tp1_hit and hi >= tp2:
                px = max(o, tp2) * (1 - slippage)
                realized += remaining * (px - entry)
                remaining = 0.0
                reason = "tp2"
                break
            marks.append(realized + remaining * (closes[j] - entry))
        if remaining > 0:  # stop temporel ou fin des données
            px = closes[j] * (1 - slippage)
            realized += remaining * (px - entry)
            reason = "tp1+time" if tp1_hit else ("time" if j < n - 1 else "open_at_end")
            marks = marks[:-1]
        marks.append(realized)
        path = pd.Series(marks, index=idx[j - len(marks) + 1 : j + 1])
        trades.append(
            Trade(
                ticker=ticker,
                entry_time=idx[i],
                exit_time=idx[j],
                entry=entry,
                stop=stop,
                exit_price=entry + realized,
                r_multiple=realized / risk,
                exit_reason=reason,
                bars_held=j - i,
                path=path,
            )
        )
        i = j + 1  # pas de nouvelle entrée tant que la position est ouverte
    return trades


# --------------------------------------------------------------------------- #
# Portefeuille : sizing à risque fixe, capital composé, positions plafonnées
# --------------------------------------------------------------------------- #
def run_portfolio(trades: list[Trade], risk: RiskParams, max_positions: int) -> tuple[pd.DataFrame, pd.Series]:
    """Retourne (journal des trades pris, courbe de capital mark-to-market 1H)."""
    equity = risk.capital
    open_pos: list[tuple[pd.Timestamp, float, float]] = []  # (exit_time, pnl, capital engagé)
    rows, paths = [], []
    for tr in sorted(trades, key=lambda t: t.entry_time):
        # clôture des positions sorties avant cette entrée
        for pos in [x for x in open_pos if x[0] <= tr.entry_time]:
            equity += pos[1]
            open_pos.remove(pos)
        if len(open_pos) >= max_positions:
            continue
        committed = sum(x[2] for x in open_pos)
        rps = tr.entry - tr.stop
        qty = min(equity * risk.risk_per_trade / rps, equity * risk.max_position_pct / tr.entry)
        qty = min(qty, max(equity - committed, 0) / tr.entry)  # pas de levier
        qty = qty if risk.allow_fractional else math.floor(qty)
        if qty <= 0:
            continue
        pnl = qty * (tr.exit_price - tr.entry)
        open_pos.append((tr.exit_time, pnl, qty * tr.entry))
        rows.append({**tr.as_row(), "qty": qty, "pnl": pnl, "equity_at_entry": equity})
        if tr.path is not None:
            paths.append(tr.path * qty)
    if not rows:
        return pd.DataFrame(), pd.Series(dtype=float)
    # Courbe mark-to-market : P&L latent de chaque position à chaque clôture 1H,
    # puis P&L final figé après la sortie.
    grid = pd.DatetimeIndex(sorted(set().union(*(p.index for p in paths))))
    total = np.zeros(len(grid))
    for path in paths:
        s = path.reindex(grid)
        started = grid >= path.index[0]
        total += s.ffill().where(started, 0.0).fillna(0.0).to_numpy()
    eq = pd.Series(risk.capital + total, index=grid)
    start = pd.Series({rows[0]["entry_time"]: risk.capital})
    return pd.DataFrame(rows), pd.concat([start, eq[eq.index > start.index[0]]])


def compute_metrics(book: pd.DataFrame, eq: pd.Series, capital: float) -> dict:
    if book.empty:
        return {"trades": 0}
    pnl = book["pnl"]
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    dd = eq / eq.cummax() - 1
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    final = eq.iloc[-1]
    return {
        "trades": len(book),
        "winrate_%": round(len(wins) / len(book) * 100, 1),
        "profit_factor": round(wins.sum() / abs(losses.sum()), 2) if losses.sum() != 0 else float("inf"),
        "avg_R": round(book["r_multiple"].mean(), 3),
        "expectancy_$": round(pnl.mean(), 2),
        "total_return_%": round((final / capital - 1) * 100, 1),
        "CAGR_%": round(((final / capital) ** (1 / years) - 1) * 100, 1),
        "max_drawdown_%": round(dd.min() * 100, 1),
        "avg_bars_held": round(book["bars_held"].mean(), 1),
        "exit_reasons": book["exit_reason"].value_counts().to_dict(),
    }


def buy_and_hold(qqq: pd.DataFrame, start: pd.Timestamp) -> float:
    s = qqq["Close"][pd.to_datetime(qqq.index).date >= start.date()]
    return round((s.iloc[-1] / s.iloc[0] - 1) * 100, 1) if len(s) > 1 else float("nan")


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="Backtest Nasdaq 100 swing")
    ap.add_argument("--tickers", nargs="*", help="sous-ensemble de tickers (défaut : Nasdaq 100)")
    ap.add_argument("--capital", type=float, default=RISK.capital)
    ap.add_argument("--risk", type=float, default=RISK.risk_per_trade, help="risque par trade (0.01 = 1 %%)")
    ap.add_argument("--max-positions", type=int, default=5)
    ap.add_argument("--slippage", type=float, default=0.0005, help="par côté (0.0005 = 5 bps)")
    ap.add_argument("--no-earnings", action="store_true", help="désactive le filtre earnings")
    ap.add_argument("--fractional", action="store_true")
    ap.add_argument("--out", default="backtest_trades.csv")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    tickers = args.tickers or get_universe()
    regime = STRATEGY.regime_ticker
    end = dt.date.today() + dt.timedelta(days=1)
    h_start = end - dt.timedelta(days=729)
    d_start = h_start - dt.timedelta(days=450)  # préchauffage SMA200 + pente

    log.info("Téléchargement Daily (%d titres)...", len(tickers) + 1)
    daily = download_batch(tickers + [regime], start=d_start.isoformat(), end=end.isoformat(), interval="1d")
    log.info("Téléchargement 1H (%d titres, ~2 ans)...", len(tickers))
    hourly = download_batch(tickers, start=h_start.isoformat(), end=end.isoformat(), interval="1h", chunk_size=25)
    qqq = daily[regime]

    earnings: dict[str, list[dt.date]] = {}
    if not args.no_earnings:
        from fundamentals import historical_earnings_dates

        log.info("Dates de résultats historiques (1 requête par titre)...")
        earnings = {t: historical_earnings_dates(t) for t in tickers}

    all_trades: list[Trade] = []
    for t in tickers:
        if t not in daily or t not in hourly or len(hourly[t]) < 200:
            log.warning("%s : données insuffisantes, ignoré", t)
            continue
        sig = compute_signals(hourly[t], daily[t], qqq)
        all_trades += simulate_ticker(
            t, sig, hourly[t], slippage=args.slippage, earnings=earnings.get(t),
        )

    risk = RiskParams(capital=args.capital, risk_per_trade=args.risk, allow_fractional=args.fractional)
    book, eq = run_portfolio(all_trades, risk, args.max_positions)
    metrics = compute_metrics(book, eq, args.capital)

    raw_r = pd.Series([t.r_multiple for t in all_trades])
    print("\n=== Signaux bruts (tous titres, sans contrainte de portefeuille) ===")
    if len(raw_r):
        pf = raw_r[raw_r > 0].sum() / abs(raw_r[raw_r <= 0].sum()) if (raw_r <= 0).any() else float("inf")
        print(f"trades={len(raw_r)}  winrate={(raw_r > 0).mean():.1%}  R moyen={raw_r.mean():.3f}  PF(R)={pf:.2f}")
    print("\n=== Portefeuille simulé ===")
    for k, v in metrics.items():
        print(f"{k:>16} : {v}")
    if len(book) >= 20:
        # Robustesse : une stratégie saine doit tenir sur les DEUX moitiés
        mid = book["entry_time"].min() + (book["entry_time"].max() - book["entry_time"].min()) / 2
        print("\n=== Stabilité (R par trade, par moitié de période) ===")
        for label, part in (("1re moitié", book[book["entry_time"] < mid]), ("2e moitié", book[book["entry_time"] >= mid])):
            r = part["r_multiple"]
            pf_h = r[r > 0].sum() / abs(r[r <= 0].sum()) if (r <= 0).any() else float("inf")
            print(f"{label:>16} : trades={len(r)}  winrate={(r > 0).mean():.1%}  R moyen={r.mean():+.3f}  PF(R)={pf_h:.2f}")
    if len(book):
        print(f"{'QQQ buy&hold_%':>16} : {buy_and_hold(qqq, book['entry_time'].min())}")
        book.to_csv(args.out, index=False)
        eq.to_csv(args.out.replace(".csv", "_equity.csv"), header=["equity"])
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(10, 4))
            eq.plot(ax=ax, title="Courbe de capital (backtest)")
            ax.set_ylabel("$")
            fig.tight_layout()
            fig.savefig(args.out.replace(".csv", "_equity.png"), dpi=120)
        except ImportError:
            pass
        print(f"\nDétail des trades : {args.out}")


if __name__ == "__main__":
    main()
