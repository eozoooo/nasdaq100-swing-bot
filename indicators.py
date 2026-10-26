"""Indicateurs techniques vectorisés (pandas pur, pas de dépendance TA-Lib)."""
from __future__ import annotations

import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI de Wilder (lissage alpha = 1/period)."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    # loss == 0 -> RSI = 100 ; gain == loss == 0 -> 50
    out = out.where(loss != 0, 100.0)
    return out.where(~((gain == 0) & (loss == 0)), 50.0)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["Close"].shift(1)
    return pd.concat(
        [df["High"] - df["Low"], (df["High"] - prev_close).abs(), (df["Low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR de Wilder."""
    return true_range(df).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def bollinger(close: pd.Series, period: int = 20, n_std: float = 2.0) -> pd.DataFrame:
    mid = sma(close, period)
    std = close.rolling(period, min_periods=period).std(ddof=0)
    return pd.DataFrame({"bb_mid": mid, "bb_up": mid + n_std * std, "bb_low": mid - n_std * std})
