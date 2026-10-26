"""Test sur données réelles Yahoo : vérifie que le format reçu correspond à ce
que le code attend. À lancer avant la mise en production (workflow
"Real data test") ou en local : python scripts/smoke_test.py
"""
from __future__ import annotations

import datetime as dt
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import warnings

import pandas as pd  # noqa: E402

from config import STRATEGY  # noqa: E402
from data import download_batch, drop_incomplete_hourly, drop_today_daily  # noqa: E402
from fundamentals import check_fundamentals, historical_earnings_dates  # noqa: E402
from strategy import compute_signals, daily_features  # noqa: E402
from universe import fetch_from_wikipedia, get_universe  # noqa: E402

# yfinance émet des centaines d'avertissements de dépréciation pandas, sans impact
warnings.filterwarnings("ignore", module="yfinance")
NY = "America/New_York"
SAMPLE = ["AAPL", "NVDA", "MSFT", "AMZN", "COST"]
results: list[tuple[str, str, str]] = []  # (nom, OK/AVERT./ÉCHEC, détail)


def check(name: str, critical: bool = True):
    """critical=False : un échec est signalé mais ne fait pas échouer le test."""
    def deco(fn):
        try:
            detail = fn() or ""
            results.append((name, "OK", detail))
        except Exception as exc:
            results.append((name, "ÉCHEC" if critical else "AVERT.", f"{type(exc).__name__}: {exc}"))
            traceback.print_exc()
        return fn
    return deco


now = dt.datetime.now(dt.timezone.utc)
tickers = get_universe()
daily: dict[str, pd.DataFrame] = {}
hourly: dict[str, pd.DataFrame] = {}


@check("Univers : liste statique vs Wikipedia", critical=False)
def _():
    wiki = set(fetch_from_wikipedia())
    static = set(tickers)
    added, removed = sorted(wiki - static), sorted(static - wiki)
    assert len(wiki) >= 95, f"seulement {len(wiki)} tickers lus"
    return f"{len(wiki)} sur Wikipedia ; à ajouter {added or 'aucun'} ; à retirer {removed or 'aucun'}"


@check("Daily : téléchargement en lot des 100 titres + QQQ")
def _():
    daily.update(download_batch(tickers + [STRATEGY.regime_ticker], period="2y", interval="1d"))
    missing = sorted(set(tickers + ["QQQ"]) - set(daily))
    assert len(missing) <= 3, f"manquants : {missing}"
    return f"{len(daily)} titres reçus, manquants : {missing or 'aucun'}"


@check("Daily : format (index, colonnes, fraîcheur, profondeur)")
def _():
    q = daily["QQQ"]
    for t, df in daily.items():
        assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"], (t, list(df.columns))
        assert df.index.is_monotonic_increasing and not df.index.has_duplicates, t
        assert (df["High"] >= df["Low"]).all(), t
    last = pd.Timestamp(q.index[-1]).date()
    age = (now.date() - last).days
    assert age <= 5, f"dernière bougie QQQ trop vieille : {last}"
    short = {t: f"{len(df)} j depuis {pd.Timestamp(df.index[0]).date()}" for t, df in daily.items() if len(df) < 260}
    stale = {t: str(pd.Timestamp(df.index[-1]).date()) for t, df in daily.items()
             if (pd.Timestamp(q.index[-1]) - pd.Timestamp(df.index[-1])).days > 3}
    return (f"index tz={q.index.tz}, dernière séance {last}, {len(q)} bougies ; "
            f"historique court : {short or 'aucun'} ; plus cotés (à retirer) : {stale or 'aucun'}")


@check("1H : téléchargement + horodatage 9:30..15:30 New York")
def _():
    hourly.update(download_batch(SAMPLE, period="60d", interval="1h"))
    assert set(hourly) == set(SAMPLE), set(SAMPLE) - set(hourly)
    df = hourly["AAPL"]
    local = df.index.tz_convert(NY)
    assert (local.minute == 30).all(), sorted(set(local.strftime("%H:%M")))
    slots = sorted(set(local.strftime("%H:%M")))
    assert slots[0] == "09:30" and slots[-1] == "15:30", slots
    per_day = pd.Series(local.date).value_counts()
    return f"{len(df)} bougies, créneaux {slots}, bougies/jour médiane {int(per_day.median())}"


@check("1H : suppression de la bougie en cours")
def _():
    df = hourly["AAPL"]
    kept = drop_incomplete_hourly(df, now)
    return f"{len(df) - len(kept)} bougie(s) non clôturée(s) retirée(s), dernière close {kept.index[-1].tz_convert(NY)}"


@check("Stratégie : calcul sur données réelles (5 titres)")
def _():
    q = drop_today_daily(daily["QQQ"], now)
    out = []
    for t in SAMPLE:
        x = compute_signals(drop_incomplete_hourly(hourly[t], now), drop_today_daily(daily[t], now), q)
        last = x.iloc[-1]
        assert pd.notna(last["atr_d"]) and pd.notna(last["macd_hist"]) and pd.notna(last["vol_ratio"]), t
        out.append(f"{t}: {int(x['signal'].sum())} signaux/60j, daily_ok={bool(last['daily_ok'])}")
    return " | ".join(out)


@check("Pré-filtre Daily sur tout l'univers (aujourd'hui)")
def _():
    q = drop_today_daily(daily["QQQ"], now)
    ok = []
    for t in tickers:
        if t in daily:
            f = daily_features(drop_today_daily(daily[t], now), q).dropna(subset=["sma200"])
            if len(f) and f["daily_ok"].iloc[-1]:
                ok.append(t)
    regime = daily_features(q, q)["regime_ok"].iloc[-1]
    return f"régime QQQ>SMA200={bool(regime)} ; {len(ok)} titres en setup : {ok}"


@check("Fondamentaux + prochains résultats (3 titres)")
def _():
    out = []
    for t in SAMPLE[:3]:
        r = check_fundamentals(t)
        assert r.name, t
        out.append(f"{t}: {r.name}, résultats {r.next_earnings}, passe={r.passed} {r.reasons or ''}")
    return " | ".join(out)


@check("Dates de résultats historiques (backtest)")
def _():
    dates = historical_earnings_dates("AAPL")
    assert len(dates) >= 6, dates
    return f"AAPL : {len(dates)} dates, de {dates[0]} à {dates[-1]}"


print("\n" + "=" * 70)
for name, status, detail in results:
    print(f"{status:<6} | {name}\n       {detail}")
failed = [n for n, status, _ in results if status == "ÉCHEC"]
warned = [n for n, status, _ in results if status == "AVERT."]
print("=" * 70)
print(f"{len(results) - len(failed) - len(warned)}/{len(results)} vérifications réussies"
      + (f", {len(warned)} avertissement(s) non bloquant(s)" if warned else ""))
sys.exit(1 if failed else 0)
