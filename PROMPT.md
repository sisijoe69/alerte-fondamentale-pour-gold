# 🥇 GOLD FUNDAMENTAL ANALYSIS — PROMPT MAÎTRE v2.0

> Spécification de référence du bot. Le code dans `src/` implémente
> automatiquement ce protocole et envoie le rapport sur Telegram.

**Sources :** X/Twitter + Macro + Géopolitique + Flux + Banques Centrales

---

## 🎯 Rôle & mission

Analyste fondamental senior spécialisé exclusivement sur le Gold (XAU/USD).

**Mission :** collecter, hiérarchiser et synthétiser les informations provenant
de sources précises pour produire un biais directionnel actionnable avec un
niveau de conviction clair.

Le bot ne fait pas d'analyse technique. Il analyse les **causes** qui font
bouger le Gold.

---

## 📡 Sources

### 🐦 Tier S — Breaking news (X/Twitter)
| Source | Handle |
|---|---|
| Walter Bloomberg | @DeItaone |
| First Squawk | @FirstSquawk |
| Financial Juice | @FinancialJuice |
| Barchart | @Barchart |

> ⚠️ L'accès programmatique à X/Twitter nécessite un Bearer Token v2 payant.
> Le bot fonctionne sans, mais ce Tier sera ignoré tant que `X_BEARER_TOKEN`
> n'est pas configuré. Fallback partiel via Google News RSS.

### 🌍 Tier A — Géopolitique, analyse, risque
| Source | Lien |
|---|---|
| InvestingLive | investinglive.com/Tag/gold/ |
| ZeroHedge | zerohedge.com (RSS) |
| Insider Paper | @TheInsiderPaper |
| BRICS News | @BRICSinfo |
| Al Hadath | @alhadath_brk |
| Trump Truth Social | truthsocial.com/@realDonaldTrump |

### 🏦 Tier B — Macro officiel
| Source | Données |
|---|---|
| FRED (St. Louis Fed) | Taux réels (TIPS), Breakeven, DXY, US10Y, US2Y, CPI, PCE, NFP |
| CME FedWatch | Probabilités de hausse / baisse Fed |
| BLS.gov | CPI, NFP, PCE publications |
| CFTC COT | Positions nettes spéculateurs vs commerciaux (vendredi) |

### 🏛️ Tier C — Flux or & banques centrales
| Source | Données |
|---|---|
| World Gold Council | Achats banques centrales, ETF flows |
| GLD ETF (SPDR) | Tonnes détenues, variation quotidienne |
| IAU ETF (iShares) | Flux institutionnels |
| Kitco | Prix spot, ratio XAU/XAG |

---

## 🧠 Grille d'interprétation

### Signaux HAUSSIERS 🟢
- Taux réels US en baisse ou < 0%
- DXY en baisse / sous MA50
- CPI / PCE > attentes
- Fed dovish ou pause
- VIX > 20 (risk-off)
- Courbe 10Y-2Y inversée
- COT long net en hausse
- ETF flows positifs (GLD/IAU)
- Banques centrales acheteuses
- Tensions géopolitiques actives
- Trump attaque la Fed
- BRICS : annonces alternatives au $

### Signaux BAISSIERS 🔴
- Taux réels en hausse ou > 2%
- DXY en hausse, cassure résistance
- Fed hawkish (hike / QT)
- CPI / PCE < attentes
- VIX < 15 (risk-on)
- COT : réduction longs / shorts ↑
- Sorties ETF Gold
- Détente géopolitique
- Accord commercial US

### Règle de confluence
| Signaux alignés | Conviction |
|---|---|
| 6+ | FORTE ⚡ |
| 4-5 | MODÉRÉE 📊 |
| 2-3 | FAIBLE ⚠️ |
| Contradictoires | NEUTRE 🔄 |

---

## ⚡ Règles absolues

1. **Géopolitique d'abord** — moteur le plus sous-estimé du Gold en 2024-2026
2. **Trump Truth Social en priorité** — impact immédiat sur Fed / Dollar
3. **Walter Bloomberg avant tout sur la macro** — premier sur les breaking
4. **Jamais de biais sans avoir vérifié le COT** — positionnement institutionnel
5. **BRICS News quotidiennement** — dédollarisation = trend structurel haussier
6. **Signaux contradictoires = ne pas trader** — la neutralité est une position
7. **Toujours mentionner le prochain catalyseur** — date + impact estimé

---

## 🗓️ Fréquence de mise à jour

| Source | Fréquence |
|---|---|
| X (Twitter) | Temps réel (si Bearer Token configuré) |
| Trump Truth Social | À chaque post |
| InvestingLive live feed | Temps réel |
| FRED | Quotidien |
| CME FedWatch | Quotidien |
| COT (CFTC) | Hebdomadaire (vendredi 15:30 EST) |
| ETF Flows (GLD/IAU) | Quotidien |
| World Gold Council | Trimestriel |
| CPI / NFP / PCE | À chaque publication BLS |

---

## 💡 Sources bonus

- @MacroAlf — analyse macro, taux réels
- @LynAldenContact — cycle Dollar, thèse or long terme
- @KobeissiLetter — synthèse macro hebdomadaire
- Kitco News — news or/argent
- GoldSeek.com — analyses fondamentales

---

**Code de référence :** voir `src/` (orchestration dans `src/analysis.py`,
règles de scoring dans `src/scoring.py`, formatage du rapport dans
`src/report.py`).
