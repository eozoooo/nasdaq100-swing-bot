import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import backtest  # noqa: E402
import main as bot  # noqa: E402
from config import RiskParams  # noqa: E402
from data import drop_incomplete_hourly, drop_today_daily, split_by_ticker  # noqa: E402
from fundamentals import FundamentalCheck  # noqa: E402
from indicators import atr, rsi  # noqa: E402
from market_calendar import is_market_open  # noqa: E402
from notifier import format_signal  # noqa: E402
from risk_manager import build_trade_plan, position_size  # noqa: E402
from state import AlertState  # noqa: E402
from strategy import align_daily_to_hourly, compute_signals, daily_features, hourly_features  # noqa: E402
from synthetic import make_market  # noqa: E402

UTC = dt.timezone.utc


@pytest.fixture(scope="module")
def market():
    stock_d, stock_h = make_market(seed=1, drift=0.0012)
    qqq_d, _ = make_market(seed=2, drift=0.0008, vol=0.008)
    return stock_d, stock_h, qqq_d


# ----------------------------------------------------------------- indicateurs
def test_rsi_bounds_and_atr_positive(market):
    d, _, _ = market
    r = rsi(d["Close"]).dropna()
    assert r.between(0, 100).all()
    assert (atr(d).dropna() > 0).all()


def test_rsi_monotonic_series():
    up = pd.Series(np.arange(1, 50, dtype=float))
    assert rsi(up).dropna().iloc[-1] == 100


# ----------------------------------------------------------------- risque
def test_position_size_fixed_risk():
    risk = RiskParams(capital=5000, risk_per_trade=0.01, max_position_pct=1.0, allow_fractional=False)
    qty, capped = position_size(entry=100, stop=95, capital=5000, risk=risk)
    assert qty == 10 and not capped          # 50 $ / 5 $ = 10 actions


def test_position_size_capped():
    risk = RiskParams(capital=5000, risk_per_trade=0.01, max_position_pct=0.25, allow_fractional=False)
    qty, capped = position_size(entry=100, stop=99, capital=5000, risk=risk)
    assert qty == 12 and capped               # brut 50 actions, plafond 1250 $ -> 12


def test_trade_plan_rr():
    risk = RiskParams(capital=5000, risk_per_trade=0.01, max_position_pct=1.0)
    plan = build_trade_plan(entry=200, stop=190, risk=risk)
    assert plan.tp1 == 220 and plan.tp2 == 230
    assert plan.shares == 5 and plan.risk_amount == 50
    assert plan.stop_pct == pytest.approx(-5)


# ----------------------------------------------------------------- données
def test_drop_incomplete_hourly():
    idx = pd.DatetimeIndex(
        [pd.Timestamp(f"2026-10-23 {s}", tz="America/New_York") for s in ["09:30", "10:30", "11:30"]]
    )
    df = pd.DataFrame({"Close": [1, 2, 3]}, index=idx)
    now = pd.Timestamp("2026-10-23 11:45", tz="America/New_York").tz_convert("UTC")
    assert list(drop_incomplete_hourly(df, now)["Close"]) == [1, 2]
    last = pd.DataFrame({"Close": [1]}, index=[pd.Timestamp("2026-10-23 15:30", tz="America/New_York")])
    after_close = pd.Timestamp("2026-10-23 16:05", tz="America/New_York")
    assert len(drop_incomplete_hourly(last, after_close)) == 1


def test_drop_today_daily():
    df = pd.DataFrame({"Close": [1, 2]}, index=pd.DatetimeIndex(["2026-10-22", "2026-10-23"]))
    now = dt.datetime(2026, 10, 23, 15, 0, tzinfo=UTC)
    assert list(drop_today_daily(df, now)["Close"]) == [1]


def test_split_by_ticker_multiindex():
    cols = pd.MultiIndex.from_product([["AAA", "BBB"], ["Open", "High", "Low", "Close", "Volume"]])
    raw = pd.DataFrame(np.ones((3, 10)), columns=cols)
    raw.loc[:, ("BBB", "Close")] = np.nan
    out = split_by_ticker(raw, ["AAA", "BBB"])
    assert list(out) == ["AAA"]


# ----------------------------------------------------------------- calendrier
@pytest.mark.parametrize(
    "utc, expected",
    [
        (dt.datetime(2026, 10, 23, 14, 30, tzinfo=UTC), True),    # été : 10:30 NY
        (dt.datetime(2026, 10, 23, 14, 0, tzinfo=UTC), False),    # été : 10:00 NY, aucune bougie 1H close
        (dt.datetime(2026, 11, 3, 14, 30, tzinfo=UTC), False),    # hiver : 9:30 NY
        (dt.datetime(2026, 11, 3, 21, 15, tzinfo=UTC), True),     # hiver : 16:15 NY
        (dt.datetime(2026, 10, 24, 15, 0, tzinfo=UTC), False),    # samedi
        (dt.datetime(2026, 11, 26, 16, 0, tzinfo=UTC), False),    # Thanksgiving
    ],
)
def test_market_hours(utc, expected):
    assert is_market_open(utc) is expected


# ----------------------------------------------------------------- stratégie
def test_no_lookahead_alignment(market):
    d, h, q = market
    hf = hourly_features(h)
    df = daily_features(d, q)
    x = align_daily_to_hourly(hf, df)
    sessions = pd.DatetimeIndex(x["session"])
    # la clôture Daily vue par une bougie de la séance D vient de D-1
    prev_close = d["Close"].shift(1).reindex(sessions).to_numpy()
    mask = ~np.isnan(prev_close)
    assert np.allclose(x["d_close"].to_numpy()[mask], prev_close[mask])


def test_alignment_without_today_daily_bar(market):
    """En direct le Daily d'aujourd'hui est retiré : la séance D doit voir D-1, pas D-2."""
    d, h, q = market
    last_session = h.index[-1].tz_convert("America/New_York").date()
    d_live = d[d.index.date < last_session]
    x = compute_signals(h, d_live, q)
    assert x["d_close"].iloc[-1] == pytest.approx(d_live["Close"].iloc[-1])


def test_signals_and_stops(market):
    d, h, q = market
    x = compute_signals(h, d, q)
    sig = x[x["signal"]]
    assert len(sig) > 0, "aucun signal sur une série en tendance avec replis"
    dist_atr = (sig["close"] - sig["stop"]) / sig["atr_d"]
    assert dist_atr.between(1.0 - 1e-9, 2.5 + 1e-9).all()
    assert (sig["tp2"] > sig["tp1"]).all() and (sig["tp1"] > sig["close"]).all()


def test_regime_filter_blocks_all_signals(market):
    """Titre haussier mais QQQ sous sa SMA200 en permanence : aucun signal."""
    d, h, _ = market
    falling = pd.Series(np.linspace(500, 100, len(d)), index=d.index)
    q_bear = pd.DataFrame({"Open": falling, "High": falling * 1.01, "Low": falling * 0.99, "Close": falling,
                           "Volume": 1e6})
    assert compute_signals(h, d, q_bear)["signal"].sum() == 0


# ----------------------------------------------------------------- backtest
def test_backtest_pipeline(market):
    d, h, q = market
    sig = compute_signals(h, d, q)
    trades = backtest.simulate_ticker("SYN", sig, h)
    assert trades
    for t in trades:
        assert t.exit_time > t.entry_time
        assert t.r_multiple >= -3  # un gap peut dépasser -1R mais pas dans ces proportions
    book, eq = backtest.run_portfolio(trades, RiskParams(capital=5000, risk_per_trade=0.01), max_positions=5)
    m = backtest.compute_metrics(book, eq, 5000)
    # la courbe mark-to-market finit exactement sur le P&L réalisé
    assert eq.iloc[-1] == pytest.approx(5000 + book["pnl"].sum())
    assert eq.index.is_monotonic_increasing
    assert m["trades"] == len(book) > 0
    assert m["max_drawdown_%"] <= 0
    assert 0 <= m["winrate_%"] <= 100


def test_backtest_stop_first_when_both_hit():
    idx = pd.date_range("2026-01-05 09:30", periods=3, freq="h", tz="America/New_York")
    h = pd.DataFrame(
        {"Open": [100, 100, 100], "High": [100, 130, 100], "Low": [100, 80, 100], "Close": [100, 100, 100],
         "Volume": [1, 1, 1]},
        index=idx,
    )
    sig = pd.DataFrame({"signal": [True, False, False], "stop": [95.0, np.nan, np.nan]}, index=idx)
    (tr,) = backtest.simulate_ticker("X", sig, h, slippage=0)
    assert tr.exit_reason == "stop" and tr.r_multiple == pytest.approx(-1)


def test_earnings_blackout_blocks_entry(market):
    d, h, q = market
    sig = compute_signals(h, d, q)
    all_days = sorted(set(h.index.tz_convert("America/New_York").date))
    assert backtest.simulate_ticker("SYN", sig, h, earnings=all_days) == []


# ----------------------------------------------------------------- état / message
def test_state_cooldown(tmp_path):
    s = AlertState(str(tmp_path / "state.json"), cooldown_days=3)
    now = dt.datetime(2026, 10, 23, 15, tzinfo=UTC)
    assert s.can_alert("NVDA", now)
    s.record("NVDA", now)
    s.save()
    s2 = AlertState(str(tmp_path / "state.json"), cooldown_days=3)
    assert not s2.can_alert("NVDA", now + dt.timedelta(hours=5))
    assert s2.can_alert("NVDA", now + dt.timedelta(days=3))


def test_format_signal_escapes_html():
    plan = build_trade_plan(entry=100, stop=96)
    fund = FundamentalCheck(ticker="T", name="AT&T <Inc>", notes=["Prochains résultats : 12/11/2026"])
    msg = format_signal("T", plan, ["cours 10 > SMA50"], fund, "23/10 11:30 ET", 5000)
    assert "AT&amp;T &lt;Inc&gt;" in msg and "cours 10 &gt; SMA50" in msg
    assert "<b>" in msg


# ----------------------------------------------------------------- main (bout en bout, sans réseau)
def test_main_end_to_end(monkeypatch, tmp_path, market):
    d, h, q = market
    x = compute_signals(h, d, q)
    sig_ts = x.index[x["signal"]][-1]
    session = sig_ts.tz_convert("America/New_York").date()
    h_cut = h[h.index <= sig_ts]
    d_cut = d[d.index.date < session]
    now = (sig_ts + pd.Timedelta(minutes=75)).tz_convert("UTC").to_pydatetime()

    class FrozenDT(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(bot.dt, "datetime", FrozenDT)
    monkeypatch.setattr(bot, "get_universe", lambda refresh=False: ["SYN"])
    monkeypatch.setattr(bot, "cached_universe", lambda *a, **k: None)
    monkeypatch.setattr(bot, "load_daily_cached", lambda *a, **k: {"SYN": d_cut, "QQQ": q[q.index.date < session]})
    monkeypatch.setattr(bot, "download_batch", lambda *a, **k: {"SYN": h_cut})
    monkeypatch.setattr(bot, "check_fundamentals", lambda t, today=None: FundamentalCheck(ticker=t, name="Synth"))
    sent = []
    monkeypatch.setattr(bot, "send_telegram", lambda msg: sent.append(msg) or True)
    monkeypatch.chdir(tmp_path)

    assert bot.run(force=True) == 0
    assert len(sent) == 1 and "SIGNAL ACHAT · SYN" in sent[0]
    assert (tmp_path / "state.json").exists()
    # 2e exécution 15 min plus tard : anti-spam
    assert bot.run(force=True) == 0
    assert len(sent) == 1


def test_daily_cache_not_written_when_download_degraded(monkeypatch, tmp_path):
    import data

    monkeypatch.setattr(data, "download_batch", lambda *a, **k: {})
    now = dt.datetime(2026, 10, 23, 15, tzinfo=UTC)
    cache = tmp_path / "daily.pkl"
    assert data.load_daily_cached(["AAA", "BBB"], str(cache), "2y", now) == {}
    assert not cache.exists()


def test_cached_universe_roundtrip(tmp_path):
    import pickle

    import data

    now = dt.datetime(2026, 10, 23, 15, tzinfo=UTC)
    cache = tmp_path / "daily.pkl"
    assert data.cached_universe(str(cache), now) is None
    cache.write_bytes(pickle.dumps({"date": "2026-10-23", "data": {"AAA": 1, "QQQ": 1}, "missing": ["BBB"]}))
    assert data.cached_universe(str(cache), now) == ["AAA", "BBB", "QQQ"]
    assert data.cached_universe(str(cache), now + dt.timedelta(days=1)) is None


def test_exit_before_earnings():
    import dataclasses

    from config import STRATEGY

    idx = pd.DatetimeIndex(
        [pd.Timestamp(f"2026-01-{d:02d} {s}", tz="America/New_York") for d in (5, 6, 7) for s in ("09:30", "15:30")]
    )
    flat = [100.0] * len(idx)
    h = pd.DataFrame({"Open": flat, "High": flat, "Low": flat, "Close": flat, "Volume": 1}, index=idx)
    sig = pd.DataFrame({"signal": [True] + [False] * 5, "stop": [95.0] + [np.nan] * 5}, index=idx)
    p = dataclasses.replace(STRATEGY, exit_before_earnings=True)
    (tr,) = backtest.simulate_ticker("X", sig, h, p=p, slippage=0, earnings=[dt.date(2026, 1, 7)], blackout_days=0)
    assert tr.exit_reason == "earnings"
    assert tr.exit_time == idx[3]  # dernière bougie du 06/01, veille des résultats


def test_adx_range(market):
    from indicators import adx

    d, _, _ = market
    a = adx(d).dropna()
    assert len(a) and a.between(0, 100).all()


def test_earnings_exit_line():
    import datetime as dt
    from fundamentals import FundamentalCheck
    from notifier import earnings_exit_line

    # résultats un lundi -> clôturer le vendredi
    f = FundamentalCheck(ticker="X", next_earnings=dt.date(2026, 11, 9), days_to_earnings=10)
    assert earnings_exit_line(f) == "⚠️ Clôturer avant les résultats du 09/11 : au plus tard à la clôture du 06/11."
    assert earnings_exit_line(FundamentalCheck(ticker="X", next_earnings=dt.date(2027, 1, 30), days_to_earnings=60)) is None
    assert earnings_exit_line(FundamentalCheck(ticker="X")) is None
