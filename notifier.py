"""Envoi des signaux sur Telegram (parse_mode HTML, plus robuste que Markdown)."""
from __future__ import annotations

import datetime as dt
import html
import logging
import os
import time

import requests

from config import STRATEGY
from fundamentals import FundamentalCheck
from risk_manager import TradePlan

log = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/sendMessage"


def _e(text: object) -> str:
    return html.escape(str(text), quote=False)


def earnings_exit_line(fundamentals: FundamentalCheck, max_days: int = STRATEGY.max_holding_days) -> str | None:
    """Rappel de sortie si les résultats tombent avant le stop temporel (règle validée en backtest)."""
    nxt, days = fundamentals.next_earnings, fundamentals.days_to_earnings
    if not STRATEGY.exit_before_earnings or nxt is None or days is None or days > max_days * 7 / 5 + 2:
        return None
    eve = nxt - dt.timedelta(days=1)
    while eve.weekday() >= 5:  # veille ouvrée
        eve -= dt.timedelta(days=1)
    return f"⚠️ Clôturer avant les résultats du {nxt:%d/%m} : au plus tard à la clôture du {eve:%d/%m}."


def format_signal(
    ticker: str,
    plan: TradePlan,
    reasons: list[str],
    fundamentals: FundamentalCheck,
    bar_time: str,
    capital: float,
) -> str:
    name = fundamentals.name or ticker
    lines = [
        f"🟢 <b>SIGNAL ACHAT · {_e(ticker)}</b>",
        f"<i>{_e(name)}</i>",
        f"Swing Trade · Tendance 1D / Entrée 1H · bougie {_e(bar_time)}",
        "",
        "<b>📊 Pourquoi</b>",
        *[f"• {_e(r)}" for r in reasons],
        *[f"• {_e(n)}" for n in fundamentals.notes],
        "",
        "<b>🎯 Plan de trade</b>",
        f"<code>Entrée   {plan.entry:>9.2f} $</code>",
        f"<code>Stop     {plan.stop:>9.2f} $  ({plan.stop_pct:+.1f} %)</code>",
        f"<code>TP1      {plan.tp1:>9.2f} $  ({plan.tp1_pct:+.1f} %)  R/R 1:{plan.rr_tp1:g}</code>",
        f"<code>TP2      {plan.tp2:>9.2f} $  ({plan.tp2_pct:+.1f} %)  R/R 1:{plan.rr_tp2:g}</code>",
        f"<i>Vendre 50 % à TP1 puis remonter le stop au prix d'entrée. Sortie forcée après {STRATEGY.max_holding_days} séances.</i>",
        *([f"<b>{_e(x)}</b>"] if (x := earnings_exit_line(fundamentals)) else []),
        "",
        "<b>💰 Sizing</b>",
        f"<code>Quantité {plan.shares:g} actions</code>",
        f"<code>Montant  {plan.position_value:,.0f} $ ({plan.position_value / capital:.0%} du capital)</code>",
        f"<code>Risque   {plan.risk_amount:,.0f} $ ({plan.risk_pct_capital:.2f} % de {capital:,.0f} $)</code>",
    ]
    if plan.capped:
        lines.append("<i>Taille limitée par le plafond de position (risque réel &lt; risque cible).</i>")
    if plan.shares == 0:
        lines.append("⚠️ <i>Capital insuffisant pour 1 action entière avec ce risque. Activer ALLOW_FRACTIONAL ?</i>")
    lines += ["", "<i>Signal algorithmique, pas un conseil en investissement.</i>"]
    return "\n".join(lines)


def send_telegram(text: str, token: str | None = None, chat_id: str | None = None, retries: int = 3) -> bool:
    token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID absents : message affiché seulement\n%s", text)
        return False
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(API.format(token=token), json=payload, timeout=15)
            if r.status_code == 200:
                return True
            if r.status_code == 429:  # flood control Telegram
                wait = r.json().get("parameters", {}).get("retry_after", 5)
                time.sleep(wait)
                continue
            log.error("Telegram HTTP %s : %s", r.status_code, r.text[:300])
            return False
        except requests.RequestException as exc:
            log.warning("Telegram tentative %d échouée : %s", attempt, exc)
            time.sleep(2 * attempt)
    return False
