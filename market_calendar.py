"""Heures d'ouverture de Wall Street, gérées en heure de New York.

Le cron GitHub est en UTC et ne connaît pas l'heure d'été : il couvre
13:30-21:00 UTC et c'est ce module qui décide si le marché est ouvert.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
OPEN = dt.time(9, 30)
CLOSE = dt.time(16, 0)
GRACE = dt.timedelta(minutes=20)  # dernière exécution après 16h pour lire la bougie 15:30-16:00

# Jours fériés NYSE/Nasdaq (à compléter chaque année)
HOLIDAYS = {
    dt.date(2026, 1, 1), dt.date(2026, 1, 19), dt.date(2026, 2, 16), dt.date(2026, 4, 3),
    dt.date(2026, 5, 25), dt.date(2026, 6, 19), dt.date(2026, 7, 3), dt.date(2026, 9, 7),
    dt.date(2026, 11, 26), dt.date(2026, 12, 25),
    dt.date(2027, 1, 1), dt.date(2027, 1, 18), dt.date(2027, 2, 15), dt.date(2027, 3, 26),
    dt.date(2027, 5, 31), dt.date(2027, 6, 18), dt.date(2027, 7, 5), dt.date(2027, 9, 6),
    dt.date(2027, 11, 25), dt.date(2027, 12, 24),
}


def is_market_open(now_utc: dt.datetime) -> bool:
    now = now_utc.astimezone(NY)
    if now.weekday() >= 5 or now.date() in HOLIDAYS:
        return False
    start = dt.datetime.combine(now.date(), OPEN, NY)
    end = dt.datetime.combine(now.date(), CLOSE, NY) + GRACE
    # Avant 10:30 aucune bougie 1H n'est close : inutile de tourner
    return start + dt.timedelta(hours=1) <= now <= end
