# 🥇 Alerte Fondamentale Pour Gold

Bot Telegram qui exécute chaque matin (par défaut **6h, fuseau Europe/Paris**)
une analyse fondamentale complète du Gold (XAU/USD) et publie le rapport dans
un chat Telegram dédié. Une commande `/now` permet de déclencher une analyse à
la demande à tout moment.

Spécification source : [`PROMPT.md`](PROMPT.md)

---

## ✨ Fonctionnalités

- 📅 **Analyse quotidienne automatique** à l'heure configurée
- ⚡ **Commande `/now`** pour une analyse immédiate
- 📊 **Scoring multi-facteurs** : taux réels, DXY, VIX, courbe, CPI, COT, GLD, news
- 🌍 **Sentiment géopolitique** via agrégation RSS (ZeroHedge, Kitco News, Google News)
- 🏛️ **Données macro officielles** : FRED, CFTC COT, CME FedWatch, ETF holdings
- 🎯 **Trade setup** suggéré (entrée / SL / TP1 / TP2 / R-R)
- 🐳 **Déploiement Docker** prêt à l'emploi

---

## 🚀 Démarrage rapide

### 1. Créer le bot Telegram

1. Sur Telegram, parler à [@BotFather](https://t.me/BotFather) → `/newbot`
2. Récupérer le **token** (`123456789:ABCdef…`)
3. Démarrer une conversation avec votre nouveau bot (envoyer `/start`)
4. Pour un chat dédié, créer un canal privé et ajouter le bot comme admin

### 2. Cloner & configurer

```bash
git clone <repo>
cd alerte-fondamentale-pour-gold
cp .env.example .env
# Éditer .env et renseigner au minimum TELEGRAM_BOT_TOKEN
```

### 3. Récupérer votre chat ID

```bash
pip install -r requirements.txt
# Démarrer une première fois sans TELEGRAM_CHAT_ID (le bot répondra à /id)
# OU envoyer /id au bot depuis le chat cible
python -m src.bot
```

Envoyer `/id` au bot dans le chat cible → il renvoie le `chat_id` à coller
dans `.env`.

### 4. Lancer en production

**Option A — Docker (recommandé)**
```bash
docker compose up -d --build
docker compose logs -f gold-bot
```

**Option B — Python direct**
```bash
python -m src.bot
```

**Option C — Test sans Telegram (rapport en stdout)**
```bash
python -m src.cli            # affiche le rapport
python -m src.cli --send     # affiche ET envoie sur Telegram
```

---

## 🔧 Variables d'environnement

| Variable | Obligatoire | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | Token @BotFather |
| `TELEGRAM_CHAT_ID` | ✅ | ID du chat / canal cible |
| `TELEGRAM_ALLOWED_USERS` | ⬜ | IDs additionnels autorisés à `/now` (CSV) |
| `DAILY_RUN_TIME` | ⬜ | Heure quotidienne, `HH:MM` (défaut `06:00`) |
| `TIMEZONE` | ⬜ | Fuseau IANA (défaut `Europe/Paris`) |
| `FRED_API_KEY` | ⬜ | Clé FRED gratuite — sinon fallback CSV |
| `X_BEARER_TOKEN` | ⬜ | Bearer X API v2 — sources Tier S Twitter |
| `LOG_LEVEL` | ⬜ | `DEBUG` / `INFO` / `WARNING` (défaut `INFO`) |

> 🔑 **FRED API key** (recommandé, gratuit) :
> https://fred.stlouisfed.org/docs/api/api_key.html

> 🐦 **X/Twitter** : l'API v2 nécessite un abonnement payant. Sans token, le
> bot s'appuie sur Google News RSS pour la dimension sentiment (suffisant pour
> détecter l'essentiel des breaking news).

---

## 🎛️ Commandes Telegram

| Commande | Effet |
|---|---|
| `/start` ou `/help` | Message d'accueil |
| `/now` ou `/analyse` | **Analyse immédiate** (autorisé) |
| `/status` | Heure du dernier run + prochain run planifié |
| `/id` | Affiche votre `chat_id` et `user_id` |

---

## 🏗️ Architecture

```
src/
├── bot.py             # Telegram bot + scheduler APScheduler
├── analysis.py        # Orchestrateur (collecte parallèle + scoring + rendu)
├── scoring.py         # Règles bullish/bearish du PROMPT
├── report.py          # Formatage Markdown du rapport final
├── config.py          # Chargement .env
├── cli.py             # Entrée CLI pour test/cron
└── sources/
    ├── fred.py        # Taux réels, breakeven, DXY, CPI, PCE, NFP, VIX
    ├── markets.py     # Gold spot, DXY live, VIX, ratios (yfinance)
    ├── cot.py         # CFTC COT report (Socrata public API)
    ├── fedwatch.py    # CME FedWatch probabilités
    ├── etf.py         # GLD holdings (SPDR daily CSV)
    ├── calendar.py    # FOMC + événements macro à venir
    └── news.py        # Agrégateur RSS (ZeroHedge, Kitco, Google News)
```

---

## 🩺 Diagnostic

- **Le bot ne répond pas** → vérifier `TELEGRAM_BOT_TOKEN`, `docker compose logs`
- **`/now` répond "Non autorisé"** → ajouter votre `user_id` à `TELEGRAM_ALLOWED_USERS`
- **Sources `n/a` dans le rapport** → vérifier la connectivité sortante, en particulier vers `api.stlouisfed.org`, `query1.finance.yahoo.com`, `publicreporting.cftc.gov`, `news.google.com`
- **Heure d'envoi incorrecte** → vérifier `TIMEZONE` (IANA, ex. `America/Montreal`) et `DAILY_RUN_TIME`

---

## ⚠️ Disclaimer

Ce bot produit des rapports informatifs uniquement. Aucun signal n'est un
conseil en investissement. **Gérez toujours votre risque** et confrontez
toujours l'analyse fondamentale à votre propre analyse technique avant
d'entrer en position.
