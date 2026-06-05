"""Signal scoring for the Gold fundamental analysis.

Implements the bullish/bearish grid from the master prompt. Each indicator
contributes a single +/- vote (or 0 = neutral / missing data).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Signal:
    name: str
    value: float | int | str | None
    score: int                  # +1 bullish, -1 bearish, 0 neutral
    rationale: str = ""


@dataclass
class ScoreResult:
    signals: list[Signal] = field(default_factory=list)
    bull_count: int = 0
    bear_count: int = 0

    @property
    def net(self) -> int:
        return self.bull_count - self.bear_count

    def add(self, signal: Signal) -> None:
        self.signals.append(signal)
        if signal.score > 0:
            self.bull_count += 1
        elif signal.score < 0:
            self.bear_count += 1

    def bias_label(self) -> str:
        if self.net >= 2:
            return "HAUSSIER"
        if self.net <= -2:
            return "BAISSIER"
        return "NEUTRE"

    def conviction_label(self) -> tuple[str, str]:
        # (label, emoji)
        aligned = max(self.bull_count, self.bear_count)
        if aligned >= 6:
            return ("FORTE", "⚡")
        if aligned >= 4:
            return ("MODÉRÉE", "📊")
        if aligned >= 2:
            return ("FAIBLE", "⚠️")
        return ("INDÉTERMINÉE", "🔄")


def score_all(
    fred: dict,
    markets: dict,
    cot: dict,
    fedwatch: dict,
    etf: dict,
    news: dict,
) -> ScoreResult:
    result = ScoreResult()

    # 1) Real rates 10Y
    rr = fred.get("real_rate_10y")
    if rr is not None:
        if rr < 1.5:
            result.add(Signal("Taux réels 10Y", rr, +1, "< 1.5% → soutien Gold"))
        elif rr > 2.0:
            result.add(Signal("Taux réels 10Y", rr, -1, "> 2.0% → pression vendeuse"))
        else:
            result.add(Signal("Taux réels 10Y", rr, 0, "Zone neutre 1.5-2.0%"))

    # 2) DXY (prefer FRED broad index, else live)
    dxy_val = fred.get("dxy") or markets.get("dxy_live")
    dxy_change = markets.get("dxy_change_5d_pct")
    dxy_below_ma = markets.get("dxy_below_ma50")
    if dxy_change is not None:
        if dxy_change < -0.4 or (dxy_below_ma is True):
            result.add(Signal("DXY", dxy_val, +1, f"5d Δ {dxy_change:+.2f}% — Dollar faible"))
        elif dxy_change > 0.4:
            result.add(Signal("DXY", dxy_val, -1, f"5d Δ {dxy_change:+.2f}% — Dollar fort"))
        else:
            result.add(Signal("DXY", dxy_val, 0, f"5d Δ {dxy_change:+.2f}% — stable"))

    # 3) Breakeven inflation 10Y
    be = fred.get("breakeven_10y")
    if be is not None:
        if be > 2.4:
            result.add(Signal("Breakeven 10Y", be, +1, "Inflation anticipée élevée"))
        elif be < 2.0:
            result.add(Signal("Breakeven 10Y", be, -1, "Inflation anticipée faible"))
        else:
            result.add(Signal("Breakeven 10Y", be, 0, "Anticipations stables"))

    # 4) CPI YoY
    cpi = fred.get("cpi_yoy")
    if cpi is not None:
        if cpi > 3.0:
            result.add(Signal("CPI YoY", cpi, +1, "Inflation persistante > 3%"))
        elif cpi < 2.2:
            result.add(Signal("CPI YoY", cpi, -1, "Désinflation marquée"))
        else:
            result.add(Signal("CPI YoY", cpi, 0, "Zone cible 2-3%"))

    # 5) Yield curve (10Y-2Y)
    curve = fred.get("yield_curve_bps")
    if curve is not None:
        if curve < 0:
            result.add(Signal("Courbe 10Y-2Y", curve, +1, "Inversée — récession anticipée"))
        elif curve > 80:
            result.add(Signal("Courbe 10Y-2Y", curve, -1, "Steepening agressif — risk-on"))
        else:
            result.add(Signal("Courbe 10Y-2Y", curve, 0, "Normale"))

    # 6) Fed Watch — prob baisse
    prob_cut = fedwatch.get("prob_cut")
    if prob_cut is not None:
        if prob_cut >= 60:
            result.add(Signal("Proba baisse taux Fed", prob_cut, +1, f"{prob_cut:.0f}% — Fed dovish"))
        elif prob_cut <= 25:
            result.add(Signal("Proba baisse taux Fed", prob_cut, -1, f"{prob_cut:.0f}% — Fed hawkish"))
        else:
            result.add(Signal("Proba baisse taux Fed", prob_cut, 0, "Marché incertain"))

    # 7) VIX
    vix = markets.get("vix_live") or fred.get("vix")
    if vix is not None:
        if vix > 20:
            result.add(Signal("VIX", vix, +1, "Risk-off → fuite vers refuge"))
        elif vix < 14:
            result.add(Signal("VIX", vix, -1, "Risk-on prononcé"))
        else:
            result.add(Signal("VIX", vix, 0, "Volatilité normale"))

    # 8) COT — Managed money net
    cot_net = cot.get("managed_money_net")
    if cot_net is not None:
        if cot_net > 150_000:
            result.add(Signal("COT MM Net", cot_net, +1, "Long net élevé — momentum"))
        elif cot_net < 50_000:
            result.add(Signal("COT MM Net", cot_net, -1, "Long net faible / shorts dominants"))
        else:
            result.add(Signal("COT MM Net", cot_net, 0, "Positionnement modéré"))

    # 9) GLD ETF flows (5d)
    gld_change = etf.get("gld_tonnes_change_5d")
    if gld_change is not None:
        if gld_change > 3:
            result.add(Signal("GLD ETF flows 5d", gld_change, +1, "Entrées > +3t — institutionnels acheteurs"))
        elif gld_change < -3:
            result.add(Signal("GLD ETF flows 5d", gld_change, -1, "Sorties > -3t — distribution"))
        else:
            result.add(Signal("GLD ETF flows 5d", gld_change, 0, "Flux flat"))

    # 10) News sentiment / geopolitical tilt
    tilt = news.get("tilt")
    bull_hits = news.get("bull_hits", 0)
    bear_hits = news.get("bear_hits", 0)
    if tilt:
        if tilt in ("bullish", "bullish_strong"):
            result.add(
                Signal(
                    "Sentiment News/Géopolitique",
                    f"{bull_hits} bull / {bear_hits} bear",
                    +1,
                    "Narratif favorable au refuge",
                )
            )
        elif tilt in ("bearish", "bearish_strong"):
            result.add(
                Signal(
                    "Sentiment News/Géopolitique",
                    f"{bull_hits} bull / {bear_hits} bear",
                    -1,
                    "Narratif risk-on / détente",
                )
            )
        else:
            result.add(
                Signal(
                    "Sentiment News/Géopolitique",
                    f"{bull_hits} bull / {bear_hits} bear",
                    0,
                    "Sentiment mixte",
                )
            )

    # 11) Gold momentum 7d (technical confirmation only)
    g7 = markets.get("gold_change_7d_pct")
    if g7 is not None:
        if g7 > 1.5:
            result.add(Signal("Momentum 7j Gold", g7, +1, "Tendance haussière confirmée"))
        elif g7 < -1.5:
            result.add(Signal("Momentum 7j Gold", g7, -1, "Tendance baissière confirmée"))
        else:
            result.add(Signal("Momentum 7j Gold", g7, 0, "Consolidation"))

    return result
