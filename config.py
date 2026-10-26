"""Paramètres centralisés du bot.

Toutes les valeurs peuvent être surchargées par des variables d'environnement
(pratique dans GitHub Actions : onglet Settings > Secrets and variables > Variables).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value not in (None, "") else default


@dataclass(frozen=True)
class StrategyParams:
    # --- Filtre de tendance Daily (1D) ---
    sma_trend: int = 200          # tendance de fond
    sma_mid: int = 50             # tendance intermédiaire
    ema_pullback: int = 20        # zone de repli
    sma200_slope_days: int = 20   # la SMA200 doit monter sur cette fenêtre
    pullback_lookback: int = 5    # le repli vers l'EMA20 doit dater de <= 5 séances
    pullback_atr_tolerance: float = 0.5   # low <= EMA20 + 0.5 * ATR
    daily_rsi_min: float = 40.0
    daily_rsi_max: float = 70.0
    rs_lookback: int = 63         # force relative vs QQQ sur ~3 mois
    regime_ticker: str = "QQQ"    # filtre de régime de marché

    # --- Déclencheur Intraday (1H) ---
    ema_fast_h: int = 20
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    rsi_h_min: float = 50.0
    rsi_h_max: float = 70.0
    volume_ratio_min: float = 1.2  # volume / moyenne du même créneau horaire
    volume_lookback_sessions: int = 10
    bb_period: int = 20            # pas d'achat au-dessus de la bande haute 1H
    bb_std: float = 2.0

    # --- ATR / stops ---
    atr_period: int = 14
    swing_low_bars: int = 10           # creux des 10 dernières bougies 1H
    swing_low_buffer_atr: float = 0.2  # marge sous le creux
    min_stop_atr: float = 1.0          # distance de stop bornée entre 1 et 2.5 ATR(D)
    max_stop_atr: float = 2.5

    # --- Objectifs ---
    tp1_r: float = 2.0     # 50 % de la position, puis stop au point mort
    tp2_r: float = 3.0     # solde
    tp1_fraction: float = 0.5
    max_holding_days: int = 15   # stop temporel (séances)

    # --- Filtres retenus par scripts/variants.py (V4, validée hors échantillon le 26/10/2026) ---
    adx_min: float = 20.0              # > 0 : exige ADX(14) Daily >= adx_min (0 = désactivé)
    regime_qqq_sma50: bool = True      # régime plus strict : QQQ > SMA50 en plus de SMA200
    exit_before_earnings: bool = True  # sortie à la clôture de la veille des résultats


@dataclass(frozen=True)
class RiskParams:
    capital: float = field(default_factory=lambda: _env_float("CAPITAL", 5000.0))
    risk_per_trade: float = field(default_factory=lambda: _env_float("RISK_PER_TRADE", 0.01))
    # Plafond de la taille d'une ligne (sinon un stop serré donne une position énorme)
    max_position_pct: float = field(default_factory=lambda: _env_float("MAX_POSITION_PCT", 0.25))
    allow_fractional: bool = field(default_factory=lambda: os.getenv("ALLOW_FRACTIONAL", "false").lower() == "true")


@dataclass(frozen=True)
class FilterParams:
    earnings_blackout_days: int = field(default_factory=lambda: _env_int("EARNINGS_BLACKOUT_DAYS", 7))
    max_debt_to_equity: float = 300.0   # yfinance exprime D/E en % (300 = 3x)
    require_positive_fcf: bool = True
    require_positive_operating_margin: bool = True


@dataclass(frozen=True)
class BotParams:
    alert_cooldown_days: int = field(default_factory=lambda: _env_int("ALERT_COOLDOWN_DAYS", 3))
    state_file: str = "state.json"
    daily_cache_file: str = ".cache/daily.pkl"
    daily_period: str = "2y"     # assez d'historique pour la SMA200 et sa pente
    hourly_period: str = "60d"   # assez pour MACD / EMA20 / ATR en 1H
    max_signals_per_run: int = 5


STRATEGY = StrategyParams()
RISK = RiskParams()
FILTERS = FilterParams()
BOT = BotParams()
