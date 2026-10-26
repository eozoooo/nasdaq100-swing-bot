# Stratégie « Pullback in Trend » Nasdaq 100 : proposition et critique quant

> Ce document et le code associé sont un outil d'aide à la décision, pas un conseil en investissement. Aucune performance passée ou backtestée ne garantit un résultat futur.

## 1. Idée générale

On n'achète **que des titres déjà en tendance haussière** (Daily), **après un repli** vers leur moyenne courte, **au moment où le momentum intraday redémarre** (1H). C'est une stratégie de continuation de tendance avec entrée sur repli. Elle est plus robuste que l'achat de cassures (moins de faux départs) ou que le retour à la moyenne pur (qui souffre dans les marchés tendanciels).

Pourquoi elle colle au Nasdaq 100 :
- l'indice est dominé par des valeurs de croissance à **fort momentum persistant** : l'effet momentum à 3-12 mois est l'une des anomalies les mieux documentées (Jegadeesh & Titman, 1993), et il est particulièrement marqué sur la tech ;
- la liquidité est énorme : spreads de quelques centimes, glissement faible, données Yahoo fiables ;
- les replis vers l'EMA20 dans une tendance saine sont souvent achetés par les institutionnels, ce qui crée le rebond que l'on cherche à capturer.

## 2. Règles exactes

Toutes les conditions Daily utilisent la **clôture de la veille** (pas de regard vers le futur). Le déclencheur utilise la **dernière bougie 1H clôturée**.

### Filtre de régime de marché
| # | Règle | Rôle |
|---|---|---|
| R1 | `QQQ_close > SMA200(QQQ)` | Ne pas acheter de swing long dans un marché baissier |
| R2 | `QQQ_close > SMA50(QQQ)` | Pas d'achat pendant les corrections de l'indice (ajouté après validation hors échantillon) |

### Filtre de tendance Daily (1D)
| # | Règle | Rôle |
|---|---|---|
| D1 | `Close > SMA50 > SMA200` | Tendance alignée sur 2 horizons |
| D2 | `SMA200(t) > SMA200(t-20)` | Tendance de fond qui monte (pas seulement un rebond) |
| D3 | `min(Low, 5 dernières séances) ≤ EMA20 + 0,5 × ATR14` | Il y a eu un **repli** récent : on n'achète pas en extension |
| D4 | `40 ≤ RSI14(D) ≤ 70` | Ni cassé, ni suracheté |
| D5 | `Perf 63 j (titre) > Perf 63 j (QQQ)` | Force relative : on prend les leaders de l'indice |
| D6 | `ADX14(D) ≥ 20` | Tendance réelle, pas un range (ajouté après validation hors échantillon) |

### Déclencheur Intraday (1H)
| # | Règle | Rôle |
|---|---|---|
| H1 | Histogramme MACD(12,26,9) passé de ≤ 0 à > 0 sur l'une des 2 dernières bougies | Redémarrage du momentum |
| H2 | `Close > EMA20(1H)` | Le prix a repris sa moyenne courte |
| H3 | `50 ≤ RSI14(1H) ≤ 70` | Momentum positif mais pas épuisé |
| H4 | `Volume ≥ 1,2 × moyenne du même créneau horaire sur 10 séances` | Volume anormal, en comparant 10:30 à 10:30 (la première heure est toujours plus volumineuse, une moyenne simple serait biaisée) |
| H5 | `Close ≤ Bollinger haute (20, 2σ) en 1H` | Ne pas courir après une bougie déjà étirée |

### Filtre fondamental (uniquement sur les titres qui ont déclenché)
| # | Règle |
|---|---|
| F1 | Pas de résultats trimestriels dans les **7 jours calendaires** (paramétrable) |
| F2 | Free cash-flow > 0 |
| F3 | Marge opérationnelle > 0 |
| F4 | Dette / fonds propres < 3x (donnée absente = pas de rejet, une entreprise à fonds propres négatifs comme ORLY n'est pas fragile pour autant) |

Signal = R1 et D1…D5 et H1…H5 et F1…F4.

## 3. Gestion du risque

### Stop-loss (hybride structure + ATR)
```
ATR      = ATR14 Daily (lissage de Wilder)
stop_str = plus bas des 10 dernières bougies 1H − 0,2 × ATR
distance = clip(entrée − stop_str, 1,0 × ATR, 2,5 × ATR)
stop     = entrée − distance
```
Le stop se place sous le dernier creux, là où l'idée de trade est invalidée. La borne basse à 1 ATR évite un stop dans le bruit intraday. La borne haute à 2,5 ATR évite un risque par action démesuré.

### Objectifs
```
R   = entrée − stop
TP1 = entrée + 2R  -> vendre 50 %, stop remonté au prix d'entrée
TP2 = entrée + 3R  -> vendre le solde
Stop temporel : sortie après 15 séances si rien n'est touché
Résultats   : sortie à la clôture de la veille de la publication (rappel dans le message Telegram)
```
Un gagnant complet rapporte 0,5 × 2R + 0,5 × 3R = **+2,5R**. Un perdant coûte **−1R**. Le taux de réussite d'équilibre est donc d'environ **1 / (1 + 2,5) ≈ 29 %**. Tout ce qui est au-dessus (après frais) est de l'espérance positive.

### Taille de position (risque fixe)
```
risque_$   = capital × risque_par_trade          (5 000 × 1 % = 50 $)
quantité   = floor(risque_$ / (entrée − stop))
plafond    = floor(capital × 25 % / entrée)      (pas plus de 25 % du capital sur une ligne)
quantité   = min(quantité, plafond)
```
Exemple : NVDA à 180 $, ATR 5,5 $, stop à 1,5 ATR = 171,75 $. Le risque par action est de 8,25 $, donc 50 / 8,25 = 6 actions (1 080 $, 21,6 % du capital). TP1 = 196,50 $, TP2 = 204,75 $.

Avec 5 000 $, le plafond de 25 % s'active souvent sur les stops serrés : le risque réel est alors inférieur à 1 %, ce que le message Telegram signale. Sur les titres à plus de 1 250 $ (BKNG, MELI…), on ne peut parfois pas acheter une seule action : activez `ALLOW_FRACTIONAL=true` si votre courtier propose les fractions.

## 4. Angles morts (à lire avant de risquer un dollar)

1. **Marché en range.** Le filtre Daily réduit les faux signaux, mais en range les croisements MACD 1H s'enchaînent et sont souvent suivis d'un retour sous l'EMA20. Le taux de réussite chute. Le filtre QQQ > SMA200 ne détecte pas un range *au-dessus* de la SMA200 (exemple : l'été 2024).
2. **Retournement brutal.** La SMA200 réagit lentement. Lors d'un krach rapide (avril 2025, août 2024), les premiers stops sautent avant que le filtre de régime ne coupe les entrées.
3. **Gaps de nuit.** Le stop n'est pas garanti : une news ou un dégât sur un concurrent peut ouvrir 5-10 % plus bas. Le backtest le modélise (sortie à l'ouverture), mais une perte de −2R reste possible.
4. **Corrélation.** Le Nasdaq 100 est très concentré sur les semi-conducteurs et le logiciel. Cinq signaux simultanés sur NVDA, AMD, AVGO, MU et LRCX représentent un seul pari, avec 5 % du capital à risque. Limitez-vous à 1-2 positions par secteur.
5. **Earnings pendant la détention.** Le filtre bloque l'entrée à J-7, mais un trade de 15 séances peut traverser une publication. Recommandation : alléger ou clôturer la veille des résultats.
6. **Biais du survivant.** Le backtest utilise la composition **actuelle** de l'indice : les titres sortis (souvent les perdants) n'y figurent pas. Les résultats sont donc optimistes.
7. **Fondamentaux non backtestables.** Yahoo ne fournit pas de données fondamentales historiques "point-in-time" gratuites. Seuls la technique et les earnings sont testés.
8. **Sur-optimisation.** Il y a environ 20 paramètres. Ne les ajustez pas pour maximiser le backtest sur 2 ans : vous ajusteriez le bruit. Si vous les modifiez, gardez des valeurs rondes et vérifiez que le résultat tient sur les deux moitiés de la période.
9. **Données et exécution.** yfinance est une API non officielle (blocages possibles, changements sans préavis). Le cron GitHub peut avoir 5 à 15 minutes de retard en période chargée. Ce bot est un outil de **signal**, pas d'exécution automatique.

## 5. Recommandations d'analyste

- Lancez d'abord `backtest.py`. Si le Profit Factor est inférieur à 1,3 ou si le drawdown dépasse 15 % sur 2 ans, ne passez pas en réel.
- Commencez à **0,5 % de risque** par trade pendant 1 à 2 mois (paper trading ou petites tailles), et comparez les signaux reçus au backtest.
- Plafond de risque global : pas plus de 5 positions et pas plus de 5 % du capital à risque en même temps.
- Notez chaque signal suivi ou ignoré (et pourquoi) : c'est la seule façon de savoir si l'écart vient de la stratégie ou de l'exécution.
- Les règles R2, D6 et la sortie avant résultats viennent de `scripts/variants.py` (26/10/2026) : 4 variantes fixées à l'avance, comparées sur l'année 1 puis vérifiées sur l'année 2. Seule la combinaison des trois battait la référence sur les deux années (année 1 : PF 1,61 contre 1,59 ; année 2 : PF 1,55 contre 1,43, drawdown −4,5 % contre −13,1 %). Le gain de l'année 1 est minime : l'apport principal est un drawdown plus faible, au prix de moins de trades. Pour revenir à la version d'origine : `adx_min=0`, `regime_qqq_sma50=False`, `exit_before_earnings=False` dans `config.py`.
