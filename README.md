# 🥇 Alerte Fondamentale Pour Gold

Bot Telegram qui exécute chaque matin (par défaut **6h, fuseau Europe/Paris**)
une analyse fondamentale complète du Gold (XAU/USD) et publie le rapport dans
tous les chats Telegram inscrits. Une commande `/now` permet une analyse à la
demande. Multi-utilisateurs avec code d'invitation, alertes intra-day,
webhook TradingView et historique persistant.

Spécification source : [`PROMPT.md`](PROMPT.md)

---

## ✨ Fonctionnalités

| Catégorie | Détail |
|---|---|
| 📅 Daily auto | Rapport quotidien à `DAILY_RUN_TIME` (défaut 06:00 Paris) |
| ⚡ À la demande | `/now` — analyse immédiate, n'importe quand |
| 👥 Multi-user | Vos amis s'inscrivent via `/subscribe [code]` |
| 🚨 Alertes macro | Flash dès qu'un CPI/NFP/PCE/PPI tombe sur FRED |
| 📈 Chart Gold | Graphique 30 jours avec MA7/MA20 joint au rapport |
| 📊 Historique | `/history` — derniers rapports persistés en SQLite |
| 🦅 Truth Social | Scrape des posts Trump (impact Fed/$ immédiat) |
| 🔌 Webhook TradingView | Reçoit vos alertes TV → broadcast aux subscribers |
| 🐳 Docker | Déploiement 1 commande, données persistées |

---

## 🚀 Démarrage rapide

### 1. Créer le bot Telegram

1. Sur Telegram, parler à [@BotFather](https://t.me/BotFather) → `/newbot`
2. Récupérer le **token** (`123456789:ABCdef…`)
3. Démarrer une conversation avec votre nouveau bot (envoyer `/start`)

### 2. Cloner & configurer

```bash
git clone <repo>
cd alerte-fondamentale-pour-gold
cp .env.example .env
```

Remplir au minimum :
- `TELEGRAM_BOT_TOKEN` (BotFather)
- `TELEGRAM_CHAT_ID` (votre ID — voir étape 3)
- `OWNER_USER_ID` (votre user_id Telegram)
- `INVITE_CODE` (optionnel — code pour autoriser vos amis)

### 3. Récupérer votre chat ID

Premier démarrage sans `TELEGRAM_CHAT_ID` n'est pas possible — astuce :
mettez n'importe quelle valeur, lancez, puis envoyez `/id` au bot dans le chat
cible. Le bot répond avec votre `chat_id` et `user_id` à coller dans `.env`,
puis redémarrer.

### 4. Lancer

**Docker (recommandé)**
```bash
docker compose up -d --build
docker compose logs -f gold-bot
```

**Python direct**
```bash
pip install -r requirements.txt
python -m src.bot
```

---

## 👥 Partager le bot avec un ami

1. Choisissez un `INVITE_CODE` dans `.env` (ex: `GOLD2026`)
2. Redémarrer le bot
3. Votre ami trouve le bot sur Telegram, envoie `/start`
4. Puis tape : `/subscribe GOLD2026`
5. Il est inscrit et recevra le rapport quotidien + alertes

Vous (admin) gérez via :
- `/users` — liste des inscrits
- `/kick <user_id>` — retirer un inscrit

Chaque inscrit contrôle ses propres alertes : `/alerts on` ou `/alerts off`.

---

## 🎛️ Commandes Telegram

| Commande | Effet |
|---|---|
| `/start` ou `/help` | Message d'accueil |
| `/subscribe [code]` | S'inscrire (code requis si `INVITE_CODE` configuré) |
| `/unsubscribe` | Se désinscrire |
| `/now` ou `/analyse` | **Analyse immédiate** (subscribers uniquement) |
| `/history [N]` | Derniers rapports (défaut 5, max 20) |
| `/alerts on\|off` | Activer/désactiver les flashs macro intra-day |
| `/status` | Diagnostic complet du bot |
| `/id` | Affiche votre `chat_id` et `user_id` |
| `/users` | (admin) Liste des subscribers |
| `/kick <id>` | (admin) Retirer un subscriber |

---

## 🔌 Webhook TradingView (optionnel)

Activer dans `.env` :
```
WEBHOOK_ENABLED=true
WEBHOOK_PORT=8080
WEBHOOK_SECRET=monsecret_long_et_random
```

Dans TradingView → Alerts → Webhook URL : `http://VOTRE_IP:8080/tv`

Payload JSON à coller dans le champ "Message" de l'alerte :
```json
{
  "secret": "monsecret_long_et_random",
  "symbol": "{{ticker}}",
  "action": "BUY",
  "price": {{close}},
  "message": "Breakout 4H confirmed"
}
```

Le bot enrichit l'alerte avec le **biais fondamental actuel** puis la
broadcast à tous les subscribers ayant `/alerts on`.

> ⚠️ Exposer le port nécessite IP publique + ouverture firewall. Pour
> production, mettre Nginx/Caddy en reverse-proxy HTTPS devant.

---

## 🔧 Variables d'environnement complètes

| Variable | Défaut | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | **Requis.** Token @BotFather |
| `TELEGRAM_CHAT_ID` | — | **Requis.** Chat principal (notifications système) |
| `OWNER_USER_ID` | — | Votre user_id (auto-admin) |
| `INVITE_CODE` | vide | Code pour autoriser vos amis (vide = ouvert) |
| `DAILY_RUN_TIME` | `06:00` | Heure du rapport quotidien (HH:MM) |
| `TIMEZONE` | `Europe/Paris` | Fuseau IANA |
| `ALERTS_ENABLED` | `true` | Surveillance intra-day des publications BLS |
| `ALERTS_CHECK_TIME` | `14:35` | Heure de check (8:35 EST = 14:35 Paris) |
| `WEBHOOK_ENABLED` | `false` | Active serveur webhook TradingView |
| `WEBHOOK_PORT` | `8080` | Port HTTP du webhook |
| `WEBHOOK_SECRET` | vide | Secret partagé avec TradingView |
| `FRED_API_KEY` | vide | Clé FRED gratuite (recommandée) |
| `TRUTH_SOCIAL_ACCOUNT_ID` | `1077…128497` | Compte à monitorer (Trump par défaut) |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` |

> 🔑 **FRED API key** (gratuit) : https://fred.stlouisfed.org/docs/api/api_key.html

---

## 🏗️ Architecture

```
src/
├── bot.py             # Telegram + scheduler + multi-user + webhook
├── analysis.py        # Orchestrateur parallèle
├── scoring.py         # Règles bull/bear (PROMPT.md)
├── report.py          # Rendu Markdown du rapport
├── chart.py           # Graphique Gold 30 jours
├── alerts.py          # Watchdog publications macro
├── webhook.py         # Serveur aiohttp TradingView
├── db.py              # SQLite (subscribers, history, alerts log)
├── config.py          # .env loader
├── cli.py             # Entrée CLI (`python -m src.cli`)
└── sources/
    ├── fred.py        # Taux réels, breakeven, DXY, CPI, PCE, NFP, VIX
    ├── markets.py     # yfinance — Gold, DXY live, VIX, ratios
    ├── cot.py         # CFTC COT report (Socrata)
    ├── fedwatch.py    # CME FedWatch probabilités
    ├── etf.py         # GLD holdings (SPDR CSV)
    ├── calendar.py    # FOMC + événements macro 7j
    ├── news.py        # RSS aggregator (ZeroHedge, Kitco, Google News)
    └── truthsocial.py # Public Mastodon API → posts Trump

data/                  # SQLite + cache (persisted via Docker volume)
```

---

## 🩺 Diagnostic

- **Pas de message au démarrage** → vérifier `TELEGRAM_BOT_TOKEN`, `docker compose logs gold-bot`
- **`/now` répond "Inscrivez-vous"** → faire `/subscribe` (ou `/subscribe <code>`)
- **Sources `n/a` dans le rapport** → réseau bloqué vers `api.stlouisfed.org`, `query1.finance.yahoo.com`, `publicreporting.cftc.gov`, etc.
- **Webhook refuse 401** → `secret` manquant ou différent du `WEBHOOK_SECRET`
- **Alertes ne tombent jamais** → vérifier que `ALERTS_ENABLED=true` et que la date du dernier release dans `data/gold_bot.db` n'est pas déjà la plus récente

---

## ⚠️ Disclaimer

Ce bot produit des rapports informatifs uniquement. Aucun signal n'est un
conseil en investissement. **Gérez toujours votre risque** et confrontez
l'analyse fondamentale à votre propre analyse technique avant d'entrer en
position.
