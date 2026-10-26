"""État persistant minimal (anti-spam) stocké dans state.json.

Le workflow GitHub Actions commite ce fichier seulement s'il a changé.
Format :
{
  "alerts": {"NVDA": {"sent_at": "2026-10-23T15:46:02+00:00", "bar": "2026-10-23 10:30", "entry": 181.2}},
  "last_run": "2026-10-23T15:46:02+00:00"
}
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path


class AlertState:
    def __init__(self, path: str, cooldown_days: int):
        self.path = Path(path)
        self.cooldown = dt.timedelta(days=cooldown_days)
        self.data: dict = {"alerts": {}}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text())
                self.data.setdefault("alerts", {})
            except (json.JSONDecodeError, OSError):
                self.data = {"alerts": {}}

    def can_alert(self, ticker: str, now: dt.datetime) -> bool:
        rec = self.data["alerts"].get(ticker)
        if not rec:
            return True
        sent = dt.datetime.fromisoformat(rec["sent_at"])
        return now - sent >= self.cooldown

    def record(self, ticker: str, now: dt.datetime, **extra) -> None:
        self.data["alerts"][ticker] = {"sent_at": now.isoformat(timespec="seconds"), **extra}

    def prune(self, now: dt.datetime, keep_days: int = 30) -> None:
        limit = now - dt.timedelta(days=keep_days)
        self.data["alerts"] = {
            t: r for t, r in self.data["alerts"].items() if dt.datetime.fromisoformat(r["sent_at"]) >= limit
        }

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, self.path)
