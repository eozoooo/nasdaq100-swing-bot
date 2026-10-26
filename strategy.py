"""Stratégie hybride : tendance Daily + déclencheur 1H "reprise après repli".

Toutes les règles sont vectorisées : la même fonction `compute_signals` sert au
bot en direct (on lit la dernière bougie 1H clôturée) et au backtest (on lit
toutes les bougies). Ainsi le backtest teste exactement le code qui tourne.

Anti look-ahead : chaque bougie 1H de la séance D ne voit que les indicateurs
Daily calculés à la clôture de D-1.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import STRATEGY, StrategyParams
from indicators import atr, bollinger, ema, macd, rsi, sma

NY_TZ = "America/New_York"


# --------------------------------------------------------------------------- #
# Daily
# --------------------------------------------------------------------------- #
def market_regime(qqq_daily: pd.DataFrame, p: StrategyParams = STRATEGY) -> pd.DataFrame:
    close = qqq_daily["Close"]
    sma200 = sma(close, p.sma_trend)
    return pd.DataFrame(
        {
            "regime_ok": close > sma200,
            "qqq_ret_rs": close.pct_change(p.rs_lookback),
        },
        index=qqq_daily.index,
    )


def daily_features(daily: pd.DataFrame, qqq_daily: pd.DataFrame, p: StrategyParams = STRATEGY) -> pd.DataFrame:
    close = daily["Close"]
    f = pd.DataFrame(index=daily.index)
    f["d_close"] = close
    f["sma200"] = sma(close, p.sma_trend)
    f["sma50"] = sma(close, p.sma_mid)
    f["ema20"] = ema(close, p.ema_pullback)
    f["atr_d"] = atr(daily, p.atr_period)
    f["rsi_d"] = rsi(close, 14)
    f["ret_rs"] = close.pct_change(p.rs_lookback)

    regime = market_regime(qqq_daily, p).reindex(f.index, method="ffill")
    f["regime_ok"] = regime["regime_ok"].fillna(False).astype(bool)
    f["rs_ok"] = f["ret_rs"] > regime["qqq_ret_rs"]

    f["trend_ok"] = (
        (close > f["sma200"])
        & (f["sma50"] > f["sma200"])
        & (f["sma200"] > f["sma200"].shift(p.sma200_slope_days))
        & (close > f["sma50"])
    )
    recent_low = daily["Low"].rolling(p.pullback_lookback, min_periods=1).min()
    f["pullback_ok"] = recent_low <= f["ema20"] + p.pullback_atr_tolerance * f["atr_d"]
    f["rsi_d_ok"] = f["rsi_d"].between(p.daily_rsi_min, p.daily_rsi_max)

    f["daily_ok"] = f["regime_ok"] & f["trend_ok"] & f["pullback_ok"] & f["rsi_d_ok"] & f["rs_ok"]
    return f


def daily_setup_today(daily: pd.DataFrame, qqq_daily: pd.DataFrame, p: StrategyParams = STRATEGY) -> bool:
    """Le titre est-il éligible aujourd'hui (selon la dernière clôture Daily) ?

    Sert de pré-filtre en direct : on ne télécharge le 1H que pour ces titres.
    """
    f = daily_features(daily, qqq_daily, p).dropna(subset=["sma200"])
    return bool(len(f)) and bool(f["daily_ok"].iloc[-1])


# --------------------------------------------------------------------------- #
# Intraday 1H
# --------------------------------------------------------------------------- #
def hourly_features(hourly: pd.DataFrame, p: StrategyParams = STRATEGY) -> pd.DataFrame:
    close = hourly["Close"]
    h = pd.DataFrame(index=hourly.index)
    h["close"] = close
    h["high"] = hourly["High"]
    h["low"] = hourly["Low"]
    h["ema20_h"] = ema(close, p.ema_fast_h)
    m = macd(close, p.macd_fast, p.macd_slow, p.macd_signal)
    h["macd_hist"] = m["hist"]
    h["rsi_h"] = rsi(close, 14)
    h = h.join(bollinger(close, p.bb_period, p.bb_std))

    # Volume anormal : comparé à la moyenne du MÊME créneau horaire sur les
    # N séances précédentes (la 1re heure est toujours plus volumineuse).
    local = hourly.index.tz_convert(NY_TZ)
    slot = local.hour * 60 + local.minute
    vol = hourly["Volume"].astype(float)
    avg = vol.groupby(slot).transform(
        lambda s: s.shift(1).rolling(p.volume_lookback_sessions, min_periods=3).mean()
    )
    h["vol_ratio"] = vol / avg.replace(0, np.nan)

    h["swing_low"] = hourly["Low"].rolling(p.swing_low_bars, min_periods=1).min()

    hist = h["macd_hist"]
    crossed_now = (hist > 0) & (hist.shift(1) <= 0)
    crossed_prev = (hist.shift(1) > 0) & (hist.shift(2) <= 0)
    h["macd_cross"] = (hist > 0) & (crossed_now | crossed_prev)
    h["trigger_ok"] = (
        h["macd_cross"]
        & (close > h["ema20_h"])
        & h["rsi_h"].between(p.rsi_h_min, p.rsi_h_max)
        & (h["vol_ratio"] >= p.volume_ratio_min)
        & (close <= h["bb_up"])
    )
    h["session"] = pd.DatetimeIndex(local.date)
    return h


def align_daily_to_hourly(h: pd.DataFrame, d: pd.DataFrame) -> pd.DataFrame:
    """Associe à chaque bougie 1H les indicateurs Daily de la séance PRÉCÉDENTE."""
    d = d.copy()
    d.index = pd.DatetimeIndex(pd.to_datetime(d.index).date, name="session")
    left = h.reset_index(names="ts")
    right = d.reset_index()
    left["session"] = left["session"].astype("datetime64[ns]")
    right["session"] = right["session"].astype("datetime64[ns]")
    # allow_exact_matches=False : la séance D reçoit la dernière ligne Daily
    # STRICTEMENT antérieure (clôture de D-1), qu'il y ait ou non une bougie
    # Daily partielle pour D.
    merged = pd.merge_asof(
        left.sort_values("session"), right, on="session", direction="backward", allow_exact_matches=False
    )
    return merged.sort_values("ts").set_index("ts")


def compute_signals(
    hourly: pd.DataFrame,
    daily: pd.DataFrame,
    qqq_daily: pd.DataFrame,
    p: StrategyParams = STRATEGY,
) -> pd.DataFrame:
    h = hourly_features(hourly, p)
    d = daily_features(daily, qqq_daily, p)
    x = align_daily_to_hourly(h, d)
    x["daily_ok"] = x["daily_ok"].fillna(False).astype(bool)
    x["signal"] = x["daily_ok"] & x["trigger_ok"].fillna(False)

    # Stop : sous le dernier creux 1H, distance bornée entre min et max ATR(D)
    struct_stop = x["swing_low"] - p.swing_low_buffer_atr * x["atr_d"]
    dist = (x["close"] - struct_stop).clip(lower=p.min_stop_atr * x["atr_d"], upper=p.max_stop_atr * x["atr_d"])
    x["stop"] = x["close"] - dist
    x["risk_per_share"] = dist
    x["tp1"] = x["close"] + p.tp1_r * dist
    x["tp2"] = x["close"] + p.tp2_r * dist
    return x


def describe_signal(row: pd.Series) -> list[str]:
    """Raisons lisibles du déclenchement (texte brut, échappé par le notifier)."""
    return [
        f"Tendance D : cours {row['d_close']:.2f} > SMA50 {row['sma50']:.2f} > SMA200 {row['sma200']:.2f} (SMA200 haussière)",
        f"Repli D vers EMA20 ({row['ema20']:.2f}) sur les 5 dernières séances, RSI(D) {row['rsi_d']:.0f}",
        f"Force relative 3 mois : {row['ret_rs'] * 100:+.1f} % (bat le QQQ), QQQ > SMA200",
        f"Déclencheur 1H : croisement MACD haussier (hist {row['macd_hist']:+.3f}), clôture > EMA20 1H ({row['ema20_h']:.2f})",
        f"RSI(1H) {row['rsi_h']:.0f}, volume x{row['vol_ratio']:.1f} vs même créneau, sous la bande de Bollinger haute ({row['bb_up']:.2f})",
    ]
