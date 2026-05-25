"""Report formatter — produces the Markdown report defined in the master prompt."""
from __future__ import annotations

from datetime import datetime

from .scoring import ScoreResult, Signal


def _fmt(value, suffix: str = "", digits: int = 2) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}{suffix}"
    return f"{value}{suffix}"


def _signal_emoji(score: int) -> str:
    return {1: "🟢", -1: "🔴", 0: "🟡"}.get(score, "🟡")


def _risk_level(news: dict) -> tuple[str, str]:
    tilt = news.get("tilt", "neutral")
    bull = news.get("bull_hits", 0)
    bear = news.get("bear_hits", 0)
    if tilt == "bullish_strong" or bull >= 6:
        return ("ÉLEVÉ", "🔴")
    if tilt == "bullish" or bull >= 3:
        return ("MODÉRÉ", "🟡")
    return ("FAIBLE", "🟢")


def _fed_tone(prob_cut: float | None) -> tuple[str, str]:
    if prob_cut is None:
        return ("INCONNU", "❔")
    if prob_cut >= 60:
        return ("DOVISH", "🕊️")
    if prob_cut <= 25:
        return ("HAWKISH", "🦅")
    return ("NEUTRE", "⚖️")


def _trade_setup(price: float | None, bias: str, conviction: str) -> dict:
    if price is None:
        return {}
    band = 0.005 if conviction == "FORTE" else 0.008
    sl_pct = 0.012
    tp1_pct = 0.015
    tp2_pct = 0.030
    if bias == "HAUSSIER":
        entry_low = round(price * (1 - band), 2)
        entry_high = round(price, 2)
        sl = round(price * (1 - sl_pct - band), 2)
        tp1 = round(price * (1 + tp1_pct), 2)
        tp2 = round(price * (1 + tp2_pct), 2)
    elif bias == "BAISSIER":
        entry_low = round(price, 2)
        entry_high = round(price * (1 + band), 2)
        sl = round(price * (1 + sl_pct + band), 2)
        tp1 = round(price * (1 - tp1_pct), 2)
        tp2 = round(price * (1 - tp2_pct), 2)
    else:
        return {}
    risk = abs(entry_high - sl) if bias == "BAISSIER" else abs(entry_low - sl)
    reward = abs(tp1 - entry_high) if bias == "BAISSIER" else abs(tp1 - entry_low)
    rr = round(reward / risk, 2) if risk else None
    return {
        "entry_low": entry_low,
        "entry_high": entry_high,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "rr": rr,
    }


def render_report(
    fred: dict,
    markets: dict,
    cot: dict,
    fedwatch: dict,
    etf: dict,
    news: dict,
    calendar_events: list,
    score: ScoreResult,
) -> str:
    now = datetime.now()
    price = markets.get("gold_price")
    g24 = markets.get("gold_change_24h_pct")
    g7 = markets.get("gold_change_7d_pct")

    risk_label, risk_emoji = _risk_level(news)
    fed_label, fed_emoji = _fed_tone(fedwatch.get("prob_cut"))
    bias = score.bias_label()
    conv_label, conv_emoji = score.conviction_label()
    horizon = "Court terme 1-3j" if conv_label == "FAIBLE" else "Moyen terme 1-3 sem."

    lines: list[str] = []
    p = lines.append

    p("════════════════════════════════════════")
    p("🥇 *GOLD FUNDAMENTAL REPORT*")
    p(f"📅 {now.strftime('%Y-%m-%d')} | ⏰ {now.strftime('%H:%M')}")
    p("════════════════════════════════════════")
    p("")
    p(f"💰 *Prix Spot* : {_fmt(price, ' USD/oz', 2)}")
    p(f"📈 24h : {_fmt(g24, '%', 2)} | 7j : {_fmt(g7, '%', 2)}")
    if markets.get("xau_xag_ratio"):
        p(f"⚖️ Ratio XAU/XAG : {markets['xau_xag_ratio']:.2f}")
    p("")

    p("──────────────────────────────────")
    p("🌍 *1. GÉOPOLITIQUE & RISQUE*")
    p("──────────────────────────────────")
    p(f"Niveau de risque : {risk_emoji} {risk_label}")
    p(
        f"Bull/Bear hits sur news : {news.get('bull_hits', 0)} / "
        f"{news.get('bear_hits', 0)} ({news.get('total_items', 0)} articles)"
    )
    failed = news.get("failed_sources", [])
    if failed:
        p(f"⚠️ Sources indisponibles : {', '.join(failed[:4])}")
    top_headlines = news.get("items", [])[:3]
    if top_headlines:
        p("Headlines clés :")
        for h in top_headlines:
            title = (h.get("title") or "")[:90]
            p(f"  • _{h.get('source')}_ : {title}")
    p("")

    p("──────────────────────────────────")
    p("📡 *2. NARRATIF FED & MACRO*")
    p("──────────────────────────────────")
    p(f"Ton Fed : {fed_emoji} {fed_label}")
    p(
        f"Proba baisse taux : {_fmt(fedwatch.get('prob_cut'), '%', 1)} | "
        f"Prochaine réunion : {fedwatch.get('next_meeting') or 'n/a'}"
    )
    p(f"NFP dernier : {_fmt(fred.get('nfp_last'), ' K', 1)}")
    p("")

    p("──────────────────────────────────")
    p("📉 *3. INDICATEURS FONDAMENTAUX*")
    p("──────────────────────────────────")
    rows: list[tuple[str, str, int]] = []
    for sig in score.signals:
        rows.append((sig.name, _format_signal_value(sig), sig.score))
    if rows:
        p("```")
        p(f"{'Indicateur':<26} {'Valeur':<14} Signal")
        p("─" * 50)
        for name, value, scr in rows:
            p(f"{name:<26} {value:<14} {_signal_emoji(scr)}")
        p("```")
    p("")

    p("──────────────────────────────────")
    p("🪙 *4. FLUX & POSITIONNEMENT*")
    p("──────────────────────────────────")
    mm_net = cot.get("managed_money_net")
    mm_long = cot.get("managed_money_long")
    mm_short = cot.get("managed_money_short")
    if mm_net is not None:
        side = "LONG NET" if mm_net >= 0 else "SHORT NET"
        p(
            f"COT Managed Money : {side} {abs(mm_net):,} contrats "
            f"(L:{mm_long or 0:,} / S:{mm_short or 0:,})"
        )
    else:
        p("COT Managed Money : n/a")
    p(f"COT Report date   : {cot.get('report_date') or 'n/a'}")

    gld_t = etf.get("gld_tonnes")
    gld_d = etf.get("gld_tonnes_change_5d")
    if gld_t is not None:
        p(
            f"GLD ETF : {gld_t:.2f} t "
            f"({'+' if (gld_d or 0) >= 0 else ''}{_fmt(gld_d, ' t (5j)', 2)})"
        )
    else:
        p("GLD ETF : n/a")
    p("")

    p("──────────────────────────────────")
    p("📅 *5. CATALYSEURS À VENIR (7j)*")
    p("──────────────────────────────────")
    if calendar_events:
        for ev in calendar_events[:8]:
            p(f"  • {ev.date} — {ev.event} ({ev.impact})")
    else:
        p("  • Aucun événement majeur identifié")
    p("")

    p("──────────────────────────────────")
    p("🎯 *6. BIAIS DIRECTIONNEL FINAL*")
    p("──────────────────────────────────")
    bias_emoji = {"HAUSSIER": "🟢", "BAISSIER": "🔴", "NEUTRE": "🟡"}[bias]
    p(f"BIAIS      : {bias_emoji} *{bias}*")
    p(f"CONVICTION : {conv_emoji} *{conv_label}*")
    p(f"HORIZON    : {horizon}")
    p(f"Signaux haussiers : {score.bull_count}")
    p(f"Signaux baissiers : {score.bear_count}")
    p("")

    dominant = _dominant_factor(score)
    risk_factor = _principal_risk(score)
    p(f"→ Facteur dominant : {dominant}")
    p(f"→ Risque principal : {risk_factor}")
    if price:
        key_level = round(price * (1.01 if bias == "HAUSSIER" else 0.99 if bias == "BAISSIER" else 1.0), 2)
        p(f"→ Niveau clé : {key_level} USD/oz")
    p("")

    setup = _trade_setup(price, bias, conv_label)
    if setup:
        p("📌 *TRADE SETUP SUGGÉRÉ*")
        p(f"→ Entrée : {setup['entry_low']} – {setup['entry_high']}")
        p(f"→ Stop   : {setup['sl']}")
        p(f"→ TP1    : {setup['tp1']}")
        p(f"→ TP2    : {setup['tp2']}")
        if setup.get("rr"):
            p(f"→ R/R    : 1:{setup['rr']}")
    elif bias == "NEUTRE":
        p("⏸️ Signaux contradictoires — *NE PAS TRADER*. Attendre catalyseur.")
    p("")
    p("════════════════════════════════════════")
    p("⚠️ _Rapport informatif. Gérez toujours votre risque._")
    p("════════════════════════════════════════")

    return "\n".join(lines)


def _format_signal_value(sig: Signal) -> str:
    v = sig.value
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.2f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)[:14]


def _dominant_factor(score: ScoreResult) -> str:
    if not score.signals:
        return "données insuffisantes"
    if score.bull_count > score.bear_count:
        winners = [s for s in score.signals if s.score > 0]
    elif score.bear_count > score.bull_count:
        winners = [s for s in score.signals if s.score < 0]
    else:
        return "signaux équilibrés"
    if not winners:
        return "signaux équilibrés"
    top = winners[0]
    return f"{top.name} ({top.rationale})"


def _principal_risk(score: ScoreResult) -> str:
    if not score.signals:
        return "manque de données"
    if score.bull_count >= score.bear_count:
        opposite = [s for s in score.signals if s.score < 0]
    else:
        opposite = [s for s in score.signals if s.score > 0]
    if not opposite:
        return "renversement du sentiment news"
    top = opposite[0]
    return f"{top.name} ({top.rationale})"
