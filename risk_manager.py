"""Plan de trade et dimensionnement de position (risque fixe en % du capital).

Formules :
    risque_$        = capital * risque_par_trade
    risque/action   = entrée - stop
    quantité        = floor(risque_$ / risque/action)
    plafond         = floor(capital * max_position_pct / entrée)
    quantité finale = min(quantité, plafond)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from config import RISK, STRATEGY, RiskParams, StrategyParams


@dataclass
class TradePlan:
    entry: float
    stop: float
    tp1: float
    tp2: float
    risk_per_share: float
    shares: float
    position_value: float
    risk_amount: float          # perte réelle si le stop est touché
    risk_pct_capital: float
    capped: bool                # la taille a été réduite par le plafond de position
    rr_tp1: float
    rr_tp2: float

    @property
    def stop_pct(self) -> float:
        return (self.stop / self.entry - 1) * 100

    @property
    def tp1_pct(self) -> float:
        return (self.tp1 / self.entry - 1) * 100

    @property
    def tp2_pct(self) -> float:
        return (self.tp2 / self.entry - 1) * 100


def position_size(
    entry: float,
    stop: float,
    capital: float,
    risk: RiskParams = RISK,
) -> tuple[float, bool]:
    risk_per_share = entry - stop
    if risk_per_share <= 0 or entry <= 0 or capital <= 0:
        return 0.0, False
    raw = capital * risk.risk_per_trade / risk_per_share
    cap = capital * risk.max_position_pct / entry
    qty = min(raw, cap)
    qty = round(qty, 4) if risk.allow_fractional else math.floor(qty)
    return float(qty), cap < raw


def build_trade_plan(
    entry: float,
    stop: float,
    capital: float | None = None,
    risk: RiskParams = RISK,
    p: StrategyParams = STRATEGY,
) -> TradePlan:
    capital = risk.capital if capital is None else capital
    rps = entry - stop
    shares, capped = position_size(entry, stop, capital, risk)
    tp1 = entry + p.tp1_r * rps
    tp2 = entry + p.tp2_r * rps
    risk_amount = shares * rps
    return TradePlan(
        entry=entry,
        stop=stop,
        tp1=tp1,
        tp2=tp2,
        risk_per_share=rps,
        shares=shares,
        position_value=shares * entry,
        risk_amount=risk_amount,
        risk_pct_capital=risk_amount / capital * 100 if capital else 0.0,
        capped=capped,
        rr_tp1=p.tp1_r,
        rr_tp2=p.tp2_r,
    )
