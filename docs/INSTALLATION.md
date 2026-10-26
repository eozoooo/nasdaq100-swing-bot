# Guide d'installation pas à pas

Durée : 20 à 30 minutes. Coût : 0 €. Aucune installation sur votre ordinateur n'est nécessaire.

Les libellés de l'interface GitHub sont écrits **en anglais, exactement comme ils apparaissent à l'écran**, entre guillemets et en gras (exemple : **"New repository"**).

À la fin de ce guide :
- le bot tourne seul toutes les 15 minutes pendant la séance américaine ;
- vous recevez les signaux sur Telegram ;
- vous avez vérifié, avant de risquer un dollar, que tout fonctionne sur les vraies données et que le backtest est acceptable.

Sommaire :
1. [Créer le bot Telegram](#étape-1--créer-le-bot-telegram-5-min)
2. [Récupérer votre Chat ID](#étape-2--récupérer-votre-chat-id-3-min)
3. [Créer le dépôt GitHub](#étape-3--créer-le-dépôt-github-2-min)
4. [Mettre le code dans le dépôt](#étape-4--mettre-le-code-dans-le-dépôt-5-min)
5. [Enregistrer les clés secrètes](#étape-5--enregistrer-les-clés-secrètes-3-min)
6. [Régler votre capital et votre risque](#étape-6--régler-votre-capital-et-votre-risque-facultatif-2-min)
7. [Autoriser le bot à mémoriser ses alertes](#étape-7--autoriser-le-bot-à-mémoriser-ses-alertes-1-min)
8. [Lancer le test complet sur vraies données](#étape-8--lancer-le-test-complet-sur-vraies-données-15-min-dont-10-dattente)
9. [Lire le backtest et décider](#étape-9--lire-le-backtest-et-décider)
10. [Mettre en service](#étape-10--mettre-en-service)
11. [Au quotidien](#au-quotidien)
12. [Dépannage](#dépannage)

---

## Étape 1 : créer le bot Telegram (5 min)

1. Ouvrez Telegram (téléphone ou ordinateur).
2. Dans la barre de recherche, tapez **BotFather**. Choisissez celui qui a le **badge bleu de certification** (identifiant exact : `@BotFather`). Les copies sans badge sont des arnaques.
3. Appuyez sur **Start** (ou envoyez `/start`).
4. Envoyez `/newbot`.
5. BotFather demande un **nom affiché**, par exemple `Nasdaq Swing Signals`.
6. Il demande ensuite un **identifiant**, qui doit finir par `bot` et être unique, par exemple `yuto_nasdaq_swing_bot`. S'il est déjà pris, essayez-en un autre.
7. BotFather répond avec un message contenant une ligne de ce type :
   ```
   Use this token to access the HTTP API:
   7123456789:AAH4x-exemple-de-token-ne-pas-partager
   ```
   C'est votre **TELEGRAM_BOT_TOKEN**. Copiez-le dans un endroit sûr (gestionnaire de mots de passe, par exemple).

> ⚠️ Ce token donne le contrôle total du bot. Ne le collez jamais dans un fichier du dépôt, une capture d'écran ou un message. S'il fuit, envoyez `/revoke` à BotFather pour en générer un nouveau.

8. **Indispensable :** cliquez sur le lien `t.me/votre_bot` donné par BotFather, puis appuyez sur **Start** dans la conversation avec **votre** bot. Un bot Telegram n'a pas le droit d'écrire à quelqu'un qui ne lui a jamais parlé.

## Étape 2 : récupérer votre Chat ID (3 min)

Le Chat ID est le numéro de la conversation où le bot vous écrira.

**Méthode A : avec le navigateur (recommandée)**
1. Envoyez un message quelconque à votre bot, par exemple `hello`.
2. Dans un navigateur, ouvrez cette adresse en remplaçant `<TOKEN>` par votre token (gardez bien le mot `bot` collé devant) :
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
   Exemple : `https://api.telegram.org/bot7123456789:AAH4x.../getUpdates`
3. La page affiche du texte. Cherchez le passage `"chat":{"id":` suivi d'un nombre :
   ```json
   "chat":{"id":512345678,"first_name":"Yuto","type":"private"}
   ```
   Ce nombre (`512345678` ici) est votre **TELEGRAM_CHAT_ID**.
4. Si la page affiche seulement `{"ok":true,"result":[]}`, renvoyez un message à votre bot, puis rechargez la page.

**Méthode B : avec un bot utilitaire**
Envoyez `/start` à `@userinfobot` : il répond avec votre `Id`. Cela ne marche que pour une conversation privée.

**Pour recevoir les signaux dans un groupe ou un canal :**
1. Ajoutez votre bot au groupe (pour un canal, ajoutez-le comme administrateur).
2. Envoyez un message dans le groupe.
3. Refaites la méthode A. L'identifiant du groupe est négatif et commence souvent par `-100`. Copiez-le **avec le signe moins**.

## Étape 3 : créer le dépôt GitHub (2 min)

1. Connectez-vous sur [github.com](https://github.com).
2. En haut à droite, cliquez sur le **"+"**, puis sur **"New repository"**.
3. Remplissez le formulaire :
   - **"Owner"** : votre compte (`eozoooo`) ;
   - **"Repository name"** : `nasdaq100-swing-bot` ;
   - **"Description"** : facultatif ;
   - choisissez **"Private"** ou **"Public"** (voir l'encadré ci-dessous) ;
   - **ne cochez rien** dans **"Initialize this repository with"** : pas de **"Add a README file"**, **"Add .gitignore"** à **"None"**, **"Choose a license"** à **"None"**. Le dépôt doit être **vide**.
4. Cliquez sur **"Create repository"**.

> **Private ou Public ?**
> - **Private** (recommandé) : personne ne voit votre code ni les titres alertés. Vous disposez de 2 000 minutes GitHub Actions gratuites par mois. Le bot en consomme environ 700 à 1 300, ce qui suffit si vous n'avez pas d'autres workflows actifs. Consultez votre consommation dans **Settings** (de votre profil) > **"Billing and licensing"**.
> - **Public** : minutes illimitées, mais le code et `state.json` (les titres alertés) sont visibles par tous. Vos secrets restent protégés dans les deux cas.

## Étape 4 : mettre le code dans le dépôt (5 min)

Choisissez **une seule** des trois options.

### Option A : je le fais pour vous (le plus simple)
Une fois le dépôt vide créé, dites-le-moi dans la conversation. Je pousse le code directement, et vous passez à l'étape 5.

### Option B : par le site GitHub, sans rien installer
1. Décompressez `nasdaq100-swing-bot.zip` sur votre ordinateur.
2. **Affichez les fichiers cachés.** Le dossier `.github` et le fichier `.gitignore` commencent par un point, et votre système les masque. **Sans le dossier `.github`, le bot ne tournera jamais.**
   - Mac (Finder) : appuyez sur `Cmd + Maj + .`
   - Windows 11 (Explorateur) : menu **Afficher** > **Afficher** > cochez **Éléments masqués**.
3. Sur la page de votre dépôt vide, cliquez sur le lien **"uploading an existing file"**.
4. Ouvrez le dossier `nasdaq100-swing-bot`, sélectionnez **tout son contenu** (`Cmd + A` ou `Ctrl + A`) et glissez-le dans la zone **"Drag files here to add them to your repository"**. Utilisez Chrome ou Edge, qui gèrent bien le glisser-déposer de dossiers.
5. Vérifiez dans la liste qui s'affiche que `.github/workflows/trading_bot.yml` est présent.
6. En bas, dans **"Commit changes"**, laissez le message par défaut et cliquez sur le bouton vert **"Commit changes"**.
7. Sur la page d'accueil du dépôt, vérifiez que vous voyez bien le dossier `.github`, ainsi que `main.py`, `state.json`, etc. Ils doivent être **à la racine**, pas dans un sous-dossier `nasdaq100-swing-bot/`.

### Option C : en ligne de commande (si vous utilisez déjà git)
```bash
cd nasdaq100-swing-bot
git init -b main
git add .
git commit -m "Nasdaq 100 swing bot"
git remote add origin https://github.com/eozoooo/nasdaq100-swing-bot.git
git push -u origin main
```

## Étape 5 : enregistrer les clés secrètes (3 min)

1. Dans votre dépôt, cliquez sur l'onglet **"Settings"** (l'icône d'engrenage, tout à droite de la barre d'onglets).
2. Dans le menu de gauche, section **"Security"**, cliquez sur **"Secrets and variables"**, puis sur **"Actions"**.
3. Restez sur l'onglet **"Secrets"** et cliquez sur le bouton vert **"New repository secret"**.
4. Créez le premier secret :
   - **"Name"** : `TELEGRAM_BOT_TOKEN` (exactement ainsi, en majuscules) ;
   - **"Secret"** : collez votre token, sans espace ni guillemets ;
   - cliquez sur **"Add secret"**.
5. Cliquez de nouveau sur **"New repository secret"** pour le second :
   - **"Name"** : `TELEGRAM_CHAT_ID` ;
   - **"Secret"** : votre Chat ID (avec le `-` si c'est un groupe) ;
   - cliquez sur **"Add secret"**.
6. Les deux noms apparaissent dans la liste **"Repository secrets"**. Leur valeur n'est plus jamais affichée, c'est normal. Pour la modifier, cliquez sur l'icône crayon.

## Étape 6 : régler votre capital et votre risque (facultatif, 2 min)

Sans réglage, le bot calcule les tailles de position pour **5 000 $** de capital et **1 %** de risque par trade.

Pour changer ces valeurs, toujours dans **"Secrets and variables"** > **"Actions"** :
1. Cliquez sur l'onglet **"Variables"**, puis sur **"New repository variable"**.
2. Créez celles que vous voulez modifier :

| "Name" | Exemple de "Value" | Signification |
|---|---|---|
| `CAPITAL` | `5000` | Capital en dollars, sans espace ni symbole $ |
| `RISK_PER_TRADE` | `0.005` | Risque par trade : `0.01` = 1 %, `0.005` = 0,5 % (recommandé au début) |
| `MAX_POSITION_PCT` | `0.25` | Montant maximal d'une ligne : `0.25` = 25 % du capital |
| `ALLOW_FRACTIONAL` | `true` | Fractions d'actions, si votre courtier les accepte |
| `ALERT_COOLDOWN_DAYS` | `3` | Délai avant qu'un même titre puisse être signalé de nouveau |
| `EARNINGS_BLACKOUT_DAYS` | `7` | Pas d'entrée si des résultats sont publiés dans ce nombre de jours |

3. Cliquez sur **"Add variable"** pour chacune.

> Le point décimal est obligatoire : écrivez `0.005`, pas `0,005`.

## Étape 7 : autoriser le bot à mémoriser ses alertes (1 min)

Le bot enregistre les titres déjà signalés dans `state.json`, puis commite ce fichier pour ne pas vous renvoyer la même alerte. Il a besoin du droit d'écriture.

1. **"Settings"** > menu de gauche **"Actions"** > **"General"**.
2. Section **"Actions permissions"** : vérifiez que **"Allow all actions and reusable workflows"** est sélectionné.
3. Descendez jusqu'à **"Workflow permissions"** et sélectionnez **"Read and write permissions"**.
4. Cliquez sur **"Save"** (le bouton juste en dessous de cette section).

## Étape 8 : lancer le test complet sur vraies données (15 min, dont 10 d'attente)

Ce test ne passe aucun ordre et n'envoie aucun signal réel. Il :
- lance les tests unitaires ;
- vérifie que les données Yahoo arrivent dans le format attendu, pour les 100 titres ;
- fait un scan à blanc ;
- vous envoie un message Telegram de **TEST** ;
- lance le backtest complet sur 2 ans.

1. Cliquez sur l'onglet **"Actions"** de votre dépôt.
2. Si GitHub affiche **"Workflows aren't being run on this repository"** ou un bouton **"I understand my workflows, go ahead and enable them"**, cliquez dessus.
3. Dans la colonne de gauche, cliquez sur **"Real data test"**.
4. À droite, cliquez sur le bouton gris **"Run workflow"**. Un menu s'ouvre :
   - **"Use workflow from"** : laissez **"Branch: main"** ;
   - cochez **"Envoyer un message Telegram de test"** ;
   - laissez **"Options du backtest"** vide ;
   - cliquez sur le bouton vert **"Run workflow"**.
5. Après quelques secondes, une ligne apparaît avec un cercle jaune (en cours). Cliquez dessus, puis sur le job **"test"** pour suivre les étapes en direct. Cliquez sur une étape pour déplier son journal.
6. Vérifiez, étape par étape :

| Étape | Ce que vous devez voir |
|---|---|
| **Unit tests** | `25 passed` (ou plus) |
| **Smoke test on real Yahoo data** | `9/9 vérifications réussies`. La ligne « Univers » indique si la liste du Nasdaq 100 doit être mise à jour. |
| **Dry-run scan** | `Étape 1 Daily : X/100 titres...`, puis éventuellement des messages formatés. Zéro signal est normal. |
| **Telegram test message** | `Message de test envoyé`, et le message **🧪 TEST DE CONFIGURATION** arrive sur votre téléphone |
| **Backtest (2 years)** | Le tableau des résultats (voir l'étape 9). Comptez 5 à 15 minutes. |

7. Quand tout est vert (✓), remontez sur la page **"Summary"** de l'exécution. Tout en bas, section **"Artifacts"**, cliquez sur **"backtest-results"** pour télécharger un zip. Il contient le résumé, la liste de tous les trades (CSV, ouvrable dans Excel) et le graphique de la courbe de capital.

> Si une étape est rouge (✗), ouvrez-la, copiez les 20 dernières lignes du journal et envoyez-les-moi. Je corrigerai.

## Étape 9 : lire le backtest et décider

Le résumé ressemble à ceci (chiffres d'illustration) :
```
=== Portefeuille simulé ===
          trades : 180
       winrate_% : 38.5
   profit_factor : 1.45
           avg_R : 0.21
  max_drawdown_% : -9.8
=== Stabilité (R par trade, par moitié de période) ===
      1re moitié : trades=85  ...  PF(R)=1.38
       2e moitié : trades=95  ...  PF(R)=1.52
  QQQ buy&hold_% : 41.0
```

Comment le lire :

| Indicateur | Feu vert | Prudence | Ne pas lancer en réel |
|---|---|---|---|
| **profit_factor** (gains ÷ pertes) | ≥ 1,4 | 1,15 à 1,4 | < 1,15 |
| **winrate_%** | ≥ 35 % | 29 à 35 % | < 29 % (seuil de rentabilité avec ces objectifs) |
| **max_drawdown_%** | > −12 % | −12 à −20 % | < −20 % |
| **Stabilité** : PF des deux moitiés | Les deux > 1,2 | Une seule > 1,2 | Une moitié < 1 |
| **trades** | ≥ 100 | 50 à 100 (peu fiable) | < 50 (pas significatif) |

À garder en tête :
- **Ces résultats sont optimistes.** Le backtest utilise la composition actuelle de l'indice (biais du survivant) et ne teste pas les filtres fondamentaux. Attendez-vous à moins bien en réel.
- **Battre le QQQ n'est pas l'objectif premier.** La stratégie est souvent hors marché, avec un risque et un drawdown plus faibles. Comparez plutôt le rendement au drawdown.
- **Ne retouchez pas les paramètres pour « améliorer » le backtest.** Sur 2 ans, vous optimiseriez le hasard. Si les résultats sont mauvais, parlons-en avant de changer quoi que ce soit.

Pour tester une autre configuration, relancez **"Real data test"** et remplissez **"Options du backtest"**, par exemple :
- `--risk 0.005` : risque de 0,5 % ;
- `--max-positions 3` : 3 positions au maximum ;
- `--no-earnings` : sans filtre de résultats ;
- `--capital 10000` : un autre capital ;
- `--tickers NVDA MSFT AAPL` : un sous-ensemble de titres.

## Étape 10 : mettre en service

Il n'y a rien de plus à faire : le workflow **"Nasdaq100 Swing Bot"** est déjà planifié. Il tourne du lundi au vendredi, toutes les 15 minutes, de 10h30 à 16h15 heure de New York (15h30 à 22h15 heure de Paris, une heure plus tôt pendant les deux ou trois semaines par an où l'Europe et les États-Unis ne changent pas d'heure le même jour).

Pour vérifier qu'il fonctionne :
1. **"Actions"** > colonne de gauche **"Nasdaq100 Swing Bot"** > **"Run workflow"** > cochez **"Ignorer les heures de marché (test)"** > **"Run workflow"**.
2. Dans le journal de l'étape **"Run bot"**, vous devez voir `Étape 1 Daily`, `Étape 2 1H` puis `Terminé : N alerte(s) envoyée(s)`. Attention : si un signal existe à ce moment, il vous est **réellement** envoyé.
3. Le jour de bourse suivant, l'onglet **"Actions"** doit montrer une exécution toutes les 15 minutes environ. Celles qui tombent hors séance se terminent en quelques secondes avec `Marché fermé`, c'est normal.

> Conseil : pendant les 4 à 8 premières semaines, suivez les signaux **sur papier** ou avec un risque de 0,5 %. Notez chaque signal (pris ou non, résultat) et comparez avec le backtest.

## Au quotidien

- **Fréquence des signaux** : de 0 à quelques-uns par semaine sur l'ensemble de l'indice. Des journées, voire des semaines, sans signal sont normales, surtout quand le QQQ est sous sa moyenne à 200 jours : le bot coupe alors volontairement les entrées.
- **Quand un signal arrive** :
  1. vérifiez le prix actuel, qui peut avoir bougé depuis la clôture de la bougie ;
  2. passez l'ordre chez votre courtier avec la quantité indiquée ;
  3. placez **immédiatement** le stop-loss ;
  4. placez un ordre limite à TP1 pour la moitié de la position ;
  5. une fois TP1 atteint, remontez le stop au prix d'entrée.
- **Le bot ne suit pas vos positions.** Il ne vous dit pas quand vendre : ce sont vos ordres stop et TP chez le courtier qui gèrent la sortie. Après 15 séances, si rien n'est touché, clôturez la position.
- **Commits automatiques** : vous verrez dans l'historique du dépôt des commits `chore: update alert state [skip ci]`. C'est le bot qui mémorise ses alertes, ne les supprimez pas.

### Entretien

| Quand | Quoi |
|---|---|
| Chaque décembre | Le Nasdaq 100 change sa composition. Relancez **"Real data test"** : la ligne « Univers » du smoke test liste les tickers à ajouter ou retirer dans `universe.py`. Ou demandez-le-moi. |
| Chaque décembre | Ajoutez les jours fériés de l'année suivante dans `market_calendar.py`. La liste actuelle s'arrête fin 2027. |
| Si Yahoo casse | `yfinance` est une API non officielle. Si le bot échoue plusieurs jours de suite avec des erreurs de téléchargement, il faut souvent juste attendre une nouvelle version de yfinance, que le workflow installe automatiquement. |
| Dépôt public inactif | GitHub désactive les workflows planifiés après 60 jours sans activité. Un e-mail vous prévient ; il suffit de cliquer sur **"Enable workflow"** dans l'onglet **"Actions"**. |

## Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| Aucun onglet **"Actions"**, ou aucun workflow listé | Le dossier `.github` n'a pas été envoyé | Refaites l'étape 4 en affichant les fichiers cachés |
| `Telegram HTTP 401 : Unauthorized` | Token faux ou révoqué | Recopiez le token dans le secret `TELEGRAM_BOT_TOKEN` (étape 5) |
| `Telegram HTTP 400 : chat not found` | Chat ID faux, ou vous n'avez jamais appuyé sur **Start** dans votre bot | Refaites les étapes 1.8 et 2 |
| `Telegram HTTP 403 : bot was blocked by the user` | Vous avez bloqué le bot | Débloquez-le dans Telegram et appuyez sur **Start** |
| `TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID absents` | Secrets absents ou mal nommés | Les noms doivent être exactement ceux de l'étape 5 |
| Échec de l'étape **"Persist state.json"** avec `Permission ... denied to github-actions[bot]` ou `403` | Droits d'écriture non accordés | Refaites l'étape 7 |
| `YFRateLimitError` ou `Too Many Requests` | Yahoo limite temporairement les requêtes | Rien à faire, le passage suivant réessaie. Si cela dure plusieurs heures, prévenez-moi. |
| `Données QQQ indisponibles : abandon` | Yahoo n'a rien renvoyé | Normalement temporaire. Le cache n'est pas figé, le passage suivant retente. |
| Toutes les exécutions affichent `Marché fermé` | Week-end, jour férié, ou avant 10h30 heure de New York | Normal. Pour tester hors séance, utilisez l'option **force**. |
| Le bot ne tourne plus du tout | Workflow désactivé (inactivité ou minutes épuisées) | **"Actions"** > **"Nasdaq100 Swing Bot"** > **"Enable workflow"**. Vérifiez votre quota de minutes. |
| Les exécutions arrivent avec 5 à 20 min de retard | Charge des serveurs GitHub | Normal sur le plan gratuit, sans impact pour du swing trading |
| `Quantité 0 actions` dans un signal | Action trop chère pour votre capital et votre risque | Mettez la variable `ALLOW_FRACTIONAL` à `true` si votre courtier le permet, ou ignorez le signal |

---

> Ce bot est un outil d'aide à la décision. Il ne constitue pas un conseil en investissement, et les performances passées ou backtestées ne préjugent pas des résultats futurs.
