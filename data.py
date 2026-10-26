"""Téléchargement des prix en lot via yf.download + cache Daily.

Économie de requêtes :
  * Daily : 1 téléchargement groupé par jour (cache .cache/daily.pkl, conservé
    entre exécutions par actions/cache) ;
  * 1H : téléchargé seulement pour les titres dont le setup Daily est valide ;
  * fondamentaux : seulement pour les titres qui déclenchent (voir fundamentals.py).
"""
from __future__ import annotations

import datetime as dt
import logging
import pickle
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)
NY_TZ = "America/New_York"
OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def download_batch(
    tickers: list[str],
    period: str | None = None,
    interval: str = "1d",
    start: str | None = None,
    end: str | None = None,
    chunk_size: int = 50,
    retries: int = 3,
) -> dict[str, pd.DataFrame]:
    """Retourne {ticker: DataFrame OHLCV} ; les tickers sans données sont omis."""
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        raw = None
        for attempt in range(1, retries + 1):
            try:
                raw = yf.download(
                    chunk,
                    period=period,
                    start=start,
                    end=end,
                    interval=interval,
                    group_by="ticker",
                    auto_adjust=True,
                    threads=True,
                    progress=False,
                )
                break
            except Exception as exc:
                log.warning("yf.download %s (essai %d) : %s", interval, attempt, exc)
                time.sleep(5 * attempt)
        if raw is None or raw.empty:
            continue
        out.update(split_by_ticker(raw, chunk))
        if i + chunk_size < len(tickers):
            time.sleep(1)  # politesse envers Yahoo entre deux lots
    return out


def split_by_ticker(raw: pd.DataFrame, tickers: list[str]) -> dict[str, pd.DataFrame]:
    out = {}
    if not isinstance(raw.columns, pd.MultiIndex):
        frames = {tickers[0]: raw}
    else:
        level = 0 if set(tickers) & set(raw.columns.get_level_values(0)) else 1
        frames = {t: raw.xs(t, axis=1, level=level) for t in tickers if t in raw.columns.get_level_values(level)}
    for t, df in frames.items():
        df = df[[c for c in OHLCV if c in df.columns]].dropna(subset=["Close"])
        if len(df):
            out[t] = df.sort_index()
    return out


def drop_incomplete_hourly(df: pd.DataFrame, now: dt.datetime | None = None) -> pd.DataFrame:
    """Supprime la bougie 1H en cours de formation.

    Yahoo horodate les bougies 1H par leur DÉBUT (9:30, 10:30, ... 15:30).
    Une bougie est close quand début + 60 min (ou 16:00 pour la dernière) est passé.
    """
    if df.empty:
        return df
    now = pd.Timestamp(now or dt.datetime.now(dt.timezone.utc))
    now = now.tz_localize("UTC") if now.tzinfo is None else now
    idx = df.index if df.index.tz is not None else df.index.tz_localize("UTC")
    local = idx.tz_convert(NY_TZ)
    end = local + pd.Timedelta(minutes=60)
    close_16 = local.normalize() + pd.Timedelta(hours=16)
    bar_end = end.where(end <= close_16, close_16)
    return df[bar_end <= now.tz_convert(NY_TZ)]


def drop_today_daily(df: pd.DataFrame, now: dt.datetime | None = None) -> pd.DataFrame:
    """En séance, Yahoo renvoie une bougie Daily partielle pour aujourd'hui : on l'enlève."""
    now = pd.Timestamp(now or dt.datetime.now(dt.timezone.utc))
    now = now.tz_localize("UTC") if now.tzinfo is None else now
    today_ny = now.tz_convert(NY_TZ).date()
    dates = pd.to_datetime(df.index).date
    return df[dates < today_ny]


def load_daily_cached(tickers: list[str], cache_file: str, period: str, now: dt.datetime) -> dict[str, pd.DataFrame]:
    """Daily téléchargé une seule fois par jour de bourse."""
    path = Path(cache_file)
    today = pd.Timestamp(now).tz_convert(NY_TZ).date().isoformat()
    if path.exists():
        try:
            with path.open("rb") as fh:
                cached = pickle.load(fh)
            if cached.get("date") == today and set(tickers) <= set(cached["data"]) | set(cached.get("missing", [])):
                log.info("Daily : cache du %s utilisé", today)
                return cached["data"]
        except Exception as exc:
            log.warning("Cache Daily illisible (%s), re-téléchargement", exc)
    data = download_batch(tickers, period=period, interval="1d")
    data = {t: drop_today_daily(df, now) for t, df in data.items()}
    missing = sorted(set(tickers) - set(data))
    if len(missing) > 0.1 * len(tickers):
        # Téléchargement dégradé (blocage Yahoo...) : ne pas figer un cache
        # incomplet pour toute la journée, on retentera au prochain passage.
        log.warning("Daily incomplet (%d manquants) : cache non écrit", len(missing))
        return data
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        pickle.dump({"date": today, "data": data, "missing": missing}, fh)
    log.info("Daily : %d/%d tickers téléchargés", len(data), len(tickers))
    return data
