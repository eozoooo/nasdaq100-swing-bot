"""Données synthétiques réalistes (tendance + replis) pour tester sans réseau."""
from __future__ import annotations

import numpy as np
import pandas as pd

NY = "America/New_York"
SLOTS = ["09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30"]


def make_market(days: int = 700, seed: int = 0, drift: float = 0.0008, vol: float = 0.012, start_price: float = 100.0):
    """Retourne (daily, hourly) cohérents : le Daily est agrégé depuis le 1H."""
    rng = np.random.default_rng(seed)
    sessions = pd.bdate_range("2024-01-02", periods=days)
    rows, price = [], start_price
    for d in sessions:
        # cycles de repli : la dérive s'inverse ~1 semaine sur 5
        cyc = np.sin(2 * np.pi * (len(rows) / 7) / 25)
        mu = drift * (1.6 if cyc > -0.5 else -2.5)
        for k, slot in enumerate(SLOTS):
            ret = rng.normal(mu / 7, vol / np.sqrt(7))
            o = price
            c = o * (1 + ret)
            hi = max(o, c) * (1 + abs(rng.normal(0, vol / 10)))
            lo = min(o, c) * (1 - abs(rng.normal(0, vol / 10)))
            base_v = 3e6 if k == 0 else 1e6
            v = base_v * rng.lognormal(0, 0.4) * (1.8 if ret > 0 and rng.random() < 0.3 else 1.0)
            ts = pd.Timestamp(f"{d.date()} {slot}", tz=NY)
            rows.append((ts, o, hi, lo, c, v))
            price = c
    hourly = pd.DataFrame(rows, columns=["ts", "Open", "High", "Low", "Close", "Volume"]).set_index("ts")
    g = hourly.groupby(hourly.index.date)
    daily = pd.DataFrame(
        {
            "Open": g["Open"].first(),
            "High": g["High"].max(),
            "Low": g["Low"].min(),
            "Close": g["Close"].last(),
            "Volume": g["Volume"].sum(),
        }
    )
    daily.index = pd.DatetimeIndex(daily.index)
    return daily, hourly
