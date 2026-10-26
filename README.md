# Nasdaq 100 Swing Bot

Bot de swing trading gratuit : il scanne les 100 actions du Nasdaq 100 toutes les 15 minutes pendant la séance américaine, sur GitHub Actions, et envoie les signaux d'achat sur Telegram avec un plan de trade complet (entrée, stop ATR, objectifs 2R/3R, taille de position).

La stratégie, ses formules et ses limites sont détaillées dans [docs/STRATEGIE.md](docs/STRATEGIE.md).

> Outil d'aide à la décision, pas un conseil en investissement. Le bot n'exécute aucun ordre.

## Arborescence

```
nasdaq100-swing-bot/
├── .github/workflows/trading_bot.yml   # cron 15 min + cache Daily + commit de state.json
├── .github/workflows/real_data_test.yml # test manuel complet sur vraies données
├── main.py              # orchestration (entonnoir Daily -> 1H -> fondamentaux -> Telegram)
├── strategy.py          # règles d'entrée vectorisées (partagées avec le backtest)
├── risk_manager.py      # stop, objectifs, taille de position
├── fundamentals.py      # earnings + qualité du bilan (seulement sur les signaux)
├── notifier.py          # message Telegram HTML
├── data.py              # yf.download en lot, cache Daily, bougies non clôturées
├── indicators.py        # EMA, SMA, RSI, MACD, ATR, Bollinger (pandas pur)
├── market_calendar.py   # heures de New York, heure d'été, jours fériés
├── state.py             # anti-spam (state.json)
├── universe.py          # liste Nasdaq 100 (+ rafraîchissement Wikipedia)
├── config.py            # tous les paramètres
├── backtest.py          # backtest 2 ans : winrate, profit factor, drawdown
├── state.json
├── requirements.txt
├── docs/STRATEGIE.md
├── scripts/smoke_test.py # vérifications sur vraies données
└── tests/               # tests sur données synthétiques (pytest)
```

## Comment le bot ménage l'API Yahoo

| Étape | Données | Fréquence | Titres concernés |
|---|---|---|---|
| 1 | Daily en lot (`yf.download`, 2 lots de 50) | 1 fois par jour (cache GitHub) | ~100 |
| 2 | 1H en lot | Toutes les 15 min | Seulement ceux qui passent le filtre Daily (souvent 5 à 25) |
| 3 | `calendar` + `info` (fondamentaux) | Seulement en cas de signal | 0 à 3 en général |

## Anti-spam

Un titre déjà signalé n'est pas renvoyé pendant `ALERT_COOLDOWN_DAYS` jours (3 par défaut). Le registre `state.json` est commité par le workflow **uniquement quand une alerte part**, donc l'historique git ne se remplit pas inutilement. Le paramètre `concurrency` du workflow empêche deux exécutions de se marcher dessus.

## Installation

👉 **Suivez le [guide d'installation pas à pas](docs/INSTALLATION.md)** (20 à 30 min, sans rien installer sur votre ordinateur). Il couvre la création du bot Telegram, le dépôt GitHub, les secrets, le test sur vraies données, la lecture du backtest, la mise en service et le dépannage.

## Utilisation locale

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m pytest -q                      # tests (sans réseau)
python main.py --force --dry-run         # scan immédiat, messages affichés et non envoyés
python main.py --refresh-universe        # relit la composition du Nasdaq 100 sur Wikipedia
python main.py --test-telegram           # vérifie token + chat id avec un message de test
python scripts/smoke_test.py             # vérifications sur les vraies données Yahoo
```

## Backtest

```bash
python backtest.py                       # Nasdaq 100, ~2 ans de 1H, filtre earnings inclus
python backtest.py --no-earnings         # plus rapide (évite 100 requêtes)
python backtest.py --capital 10000 --risk 0.005 --max-positions 4
python backtest.py --tickers NVDA MSFT AAPL
```

Le script affiche les signaux bruts (en multiples de R) puis le portefeuille simulé : nombre de trades, winrate, profit factor, R moyen, rendement, CAGR, max drawdown, raisons de sortie, et la comparaison avec un achat-conservation du QQQ. Il écrit aussi `backtest_trades.csv`, `backtest_trades_equity.csv` et un graphique `backtest_trades_equity.png`.

Hypothèses prudentes : entrée à la clôture de la bougie du signal avec 5 bps de glissement de chaque côté, stop prioritaire si stop et objectif sont touchés dans la même bougie, sortie à l'ouverture en cas de gap sous le stop. Biais connus : composition actuelle de l'indice (biais du survivant) et fondamentaux non testés. Le drawdown est mesuré en mark-to-market sur chaque clôture 1H (positions ouvertes valorisées). Le script affiche aussi les résultats par moitié de période : une stratégie robuste doit tenir sur les deux.

## Exemple de message

```
🟢 SIGNAL ACHAT · NVDA
NVIDIA Corporation
Swing Trade · Tendance 1D / Entrée 1H · bougie 23/10 11:30 ET

📊 Pourquoi
• Tendance D : cours 182.10 > SMA50 176.40 > SMA200 151.20 (SMA200 haussière)
• Repli D vers EMA20 (179.80) sur les 5 dernières séances, RSI(D) 56
• Force relative 3 mois : +14.2 % (bat le QQQ), QQQ > SMA200
• Déclencheur 1H : croisement MACD haussier (hist +0.112), clôture > EMA20 1H (180.95)
• RSI(1H) 58, volume x1.6 vs même créneau, sous la bande de Bollinger haute (184.30)
• Prochains résultats : 19/11/2026 (dans 27 j)
• Fondamentaux : FCF +72.0 Md$, marge op. 62%, D/E 0.1x

🎯 Plan de trade
Entrée      181.20 $
Stop        172.95 $  (-4.6 %)
TP1         197.70 $  (+9.1 %)  R/R 1:2
TP2         205.95 $  (+13.7 %)  R/R 1:3
Vendre 50 % à TP1 puis remonter le stop au prix d'entrée. Sortie forcée après 15 séances.

💰 Sizing
Quantité 6 actions
Montant  1,087 $ (22% du capital)
Risque   50 $ (0.99 % de 5,000 $)
```
(valeurs d'illustration)
