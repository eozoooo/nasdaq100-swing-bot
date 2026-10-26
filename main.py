"""Point d'entrée du bot (exécuté toutes les 15 min par GitHub Actions).

Pipeline en entonnoir pour ménager l'API Yahoo :
  1. Daily en lot (1x/jour, caché)      -> ~100 titres  -> filtre tendance + repli
  2. 1H en lot sur les survivants       -> ~5-25 titres -> déclencheur intraday
  3. Fondamentaux + earnings            -> 0-3 titres   -> filtre final
  4. Anti-spam (state.json) puis Telegram
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys

import warnings

import pandas as pd

from config import BOT, RISK, STRATEGY
from data import cached_universe, download_batch, drop_incomplete_hourly, load_daily_cached
from fundamentals import check_fundamentals
from market_calendar import NY, is_market_open
from notifier import format_signal, send_telegram
from risk_manager import build_trade_plan
from state import AlertState
from strategy import compute_signals, daily_setup_today, describe_signal
from universe import get_universe

# yfinance émet des centaines d'avertissements de dépréciation pandas, sans impact
warnings.filterwarnings("ignore", module="yfinance")
log = logging.getLogger("bot")
STALE_AFTER = pd.Timedelta(hours=3)  # bougie 1H plus vieille : données en retard ou jour férié


def run(force: bool = False, dry_run: bool = False, refresh_universe: bool = False) -> int:
    now = dt.datetime.now(dt.timezone.utc)
    if not force and not is_market_open(now):
        log.info("Marché fermé (%s heure de New York) : rien à faire", now.astimezone(NY).strftime("%a %H:%M"))
        return 0

    # Composition relue sur Wikipedia une fois par jour, puis reprise du cache Daily
    regime = STRATEGY.regime_ticker
    cached = None if refresh_universe else cached_universe(BOT.daily_cache_file, now)
    tickers = [t for t in cached if t != regime] if cached else get_universe(refresh=True)
    daily = load_daily_cached(tickers + [regime], BOT.daily_cache_file, BOT.daily_period, now)
    if regime not in daily:
        log.error("Données %s indisponibles : abandon", regime)
        return 1
    qqq = daily[regime]

    # Étape 1 : pré-filtre Daily (zéro requête supplémentaire)
    candidates = [t for t in tickers if t in daily and daily_setup_today(daily[t], qqq)]
    log.info("Étape 1 Daily : %d/%d titres en tendance + repli", len(candidates), len(tickers))
    if not candidates:
        return 0

    # Étape 2 : 1H en lot, seulement pour les candidats
    hourly = download_batch(candidates, period=BOT.hourly_period, interval="1h")
    triggered = []
    for t in candidates:
        h = drop_incomplete_hourly(hourly.get(t, pd.DataFrame()), now)
        if len(h) < 60:
            continue
        if pd.Timestamp(now) - h.index[-1].tz_convert("UTC") > STALE_AFTER:
            continue  # pas de bougie fraîche (jour férié non listé, données en retard...)
        sig = compute_signals(h, daily[t], qqq)
        last = sig.iloc[-1]
        if bool(last["signal"]):
            triggered.append((t, last, sig.index[-1]))
    log.info("Étape 2 1H : %d déclenchement(s) %s", len(triggered), [t for t, *_ in triggered])

    # Étape 3 + 4 : anti-spam, fondamentaux, envoi
    state = AlertState(BOT.state_file, BOT.alert_cooldown_days)
    today_ny = now.astimezone(NY).date()
    sent = 0
    for t, row, ts in triggered[: BOT.max_signals_per_run]:
        if not state.can_alert(t, now):
            log.info("%s : déjà alerté récemment, ignoré", t)
            continue
        fund = check_fundamentals(t, today=today_ny)
        if not fund.passed:
            log.info("%s rejeté (fondamental) : %s", t, ", ".join(fund.reasons))
            continue
        plan = build_trade_plan(entry=float(row["close"]), stop=float(row["stop"]))
        bar_time = ts.tz_convert(NY).strftime("%d/%m %H:%M ET")
        msg = format_signal(t, plan, describe_signal(row), fund, bar_time, RISK.capital)
        if dry_run:
            print(msg, "\n" + "-" * 40)
            continue
        if send_telegram(msg):
            state.record(t, now, bar=bar_time, entry=round(plan.entry, 2), stop=round(plan.stop, 2))
            sent += 1

    if sent:
        state.prune(now)
        state.save()
    log.info("Terminé : %d alerte(s) envoyée(s)", sent)
    return 0


def send_test_message() -> bool:
    """Vérifie token + chat id avec un faux signal clairement marqué TEST."""
    from fundamentals import FundamentalCheck

    plan = build_trade_plan(entry=100.0, stop=96.0)
    fund = FundamentalCheck(ticker="TEST", name="Message de test", notes=["Ceci n'est pas un signal réel"])
    msg = "🧪 <b>TEST DE CONFIGURATION</b>\n\n" + format_signal(
        "TEST", plan, ["Si vous lisez ceci, le bot peut vous écrire."], fund, "--", RISK.capital
    )
    ok = send_telegram(msg)
    log.info("Message de test %s", "envoyé" if ok else "NON envoyé (voir l'erreur ci-dessus)")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Bot de swing trading Nasdaq 100")
    parser.add_argument("--force", action="store_true", help="ignore les heures de marché")
    parser.add_argument("--dry-run", action="store_true", help="affiche les messages sans les envoyer")
    parser.add_argument("--refresh-universe", action="store_true", help="relit la composition sur Wikipedia")
    parser.add_argument("--test-telegram", action="store_true", help="envoie un message d'exemple puis s'arrête")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.test_telegram:
        sys.exit(0 if send_test_message() else 1)
    sys.exit(run(force=args.force, dry_run=args.dry_run, refresh_universe=args.refresh_universe))


if __name__ == "__main__":
    main()
