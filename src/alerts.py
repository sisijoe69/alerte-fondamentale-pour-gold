"""Intra-day macro release watchdog.

Polls FRED for the latest observation of key US series (CPI, NFP, PCE).
When a new monthly datapoint appears, sends a flash alert to all subscribers
who have alerts enabled.

Surprise magnitude is computed vs the prior FRED reading we have stored —
this isn't "vs consensus" (would need a paid feed) but gives an immediate
read on whether the print accelerated/decelerated.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from .db import Database
from .sources.fred import FredClient

logger = logging.getLogger(__name__)


# series_id, friendly name, type (yoy|mom|level), strong_threshold
WATCHED_SERIES = [
    ("CPIAUCSL", "CPI (US Inflation)", "yoy", 0.3),
    ("CPILFESL", "Core CPI", "yoy", 0.2),
    ("PCEPI", "PCE", "yoy", 0.2),
    ("PAYEMS", "NFP (jobs)", "mom_diff", 50.0),       # kept in thousands
    ("UNRATE", "Unemployment rate", "level", 0.2),
    ("PPIACO", "PPI", "yoy", 0.5),
]


@dataclass
class MacroEvent:
    series_id: str
    name: str
    observation_date: str
    value: float
    prior_value: float | None
    surprise: float | None      # MoM diff (NFP) or YoY delta
    bullish_for_gold: bool      # True if hot inflation / weak jobs
    headline: str


def check_releases(fred_api_key: str | None, db: Database) -> list[MacroEvent]:
    """Detect new monthly releases since the last successful check."""
    client = FredClient(fred_api_key)
    new_events: list[MacroEvent] = []

    for series_id, name, kind, threshold in WATCHED_SERIES:
        try:
            obs = client.fetch(series_id, lookback_days=540)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Macro check failed for %s: %s", series_id, exc)
            continue
        if obs.value is None or not obs.date:
            continue
        if db.macro_known(series_id, obs.date):
            continue  # already notified for this release

        prior = _prior_value(obs.raw, obs.date)
        surprise = _surprise(kind, obs.value, prior, obs.raw)
        bullish = _is_bullish_for_gold(name, kind, obs.value, prior, surprise)
        headline = _format_headline(name, kind, obs.value, prior, surprise, threshold)

        new_events.append(
            MacroEvent(
                series_id=series_id,
                name=name,
                observation_date=obs.date,
                value=obs.value,
                prior_value=prior,
                surprise=surprise,
                bullish_for_gold=bullish,
                headline=headline,
            )
        )
        db.macro_remember(series_id, obs.date, obs.value)

    return new_events


def _prior_value(raw: list[dict] | None, latest_date: str) -> float | None:
    if not raw:
        return None
    sorted_rows = sorted(
        (r for r in raw if r.get("value") not in (".", "", None)),
        key=lambda r: r["date"],
    )
    if len(sorted_rows) < 2:
        return None
    # find the entry whose date precedes latest_date
    for row in reversed(sorted_rows):
        if row["date"] < latest_date:
            try:
                return float(row["value"])
            except (ValueError, TypeError):
                return None
    return None


def _surprise(kind: str, current: float, prior: float | None, raw: list[dict] | None) -> float | None:
    if prior is None:
        return None
    if kind == "mom_diff":
        return round(current - prior, 1)
    if kind == "level":
        return round(current - prior, 2)
    if kind == "yoy":
        # need value from ~12 months ago to compute YoY here vs previous YoY
        if not raw:
            return None
        try:
            sorted_rows = sorted(
                (r for r in raw if r.get("value") not in (".", "", None)),
                key=lambda r: r["date"],
            )
            latest = current
            latest_d = datetime.fromisoformat(sorted_rows[-1]["date"]).date()
            year_ago = latest_d - timedelta(days=365)
            ya = min(sorted_rows[:-1], key=lambda r: abs((datetime.fromisoformat(r["date"]).date() - year_ago).days))
            cur_yoy = (latest / float(ya["value"]) - 1) * 100
            # previous YoY (one month back)
            prior_d = datetime.fromisoformat(sorted_rows[-2]["date"]).date()
            year_ago_prev = prior_d - timedelta(days=365)
            ya_prev = min(
                [r for r in sorted_rows if r["date"] < sorted_rows[-1]["date"]],
                key=lambda r: abs((datetime.fromisoformat(r["date"]).date() - year_ago_prev).days),
            )
            prev_yoy = (prior / float(ya_prev["value"]) - 1) * 100
            return round(cur_yoy - prev_yoy, 2)
        except (KeyError, ValueError, TypeError, ZeroDivisionError):
            return None
    return None


def _is_bullish_for_gold(name: str, kind: str, current: float, prior: float | None, surprise: float | None) -> bool:
    """Heuristic gold-impact mapping for macro releases."""
    if surprise is None:
        return False
    n = name.lower()
    if "cpi" in n or "pce" in n or "ppi" in n:
        # hotter inflation → gold bullish
        return surprise > 0
    if "nfp" in n or "jobs" in n:
        # weaker jobs → Fed dovish → gold bullish
        return surprise < 0
    if "unemployment" in n:
        # rising unemployment → dovish → gold bullish
        return surprise > 0
    return False


def _format_headline(
    name: str, kind: str, current: float, prior: float | None, surprise: float | None, threshold: float
) -> str:
    cur_str = f"{current:.2f}" if kind != "mom_diff" else f"{current:,.0f}K"
    prior_str = f"{prior:.2f}" if prior is not None and kind != "mom_diff" else (
        f"{prior:,.0f}K" if prior is not None else "n/a"
    )

    if surprise is None:
        magnitude = ""
    elif kind == "mom_diff":
        magnitude = f" (Δ {surprise:+.0f}K vs prior)"
    elif kind == "yoy":
        magnitude = f" (YoY shift {surprise:+.2f}pp)"
    else:
        magnitude = f" ({surprise:+.2f})"

    is_strong = surprise is not None and abs(surprise) >= threshold
    flag = " ⚡" if is_strong else ""
    return f"📢 *{name}* publié{flag} : {cur_str} (prior {prior_str}){magnitude}"


def format_alert_message(events: list[MacroEvent]) -> str:
    if not events:
        return ""
    lines = ["🚨 *ALERTE MACRO — Nouvelles publications*", ""]
    for ev in events:
        direction = "🟢 Gold favorable" if ev.bullish_for_gold else "🔴 Gold défavorable"
        lines.append(ev.headline)
        lines.append(f"   _{direction}_  · date série : {ev.observation_date}")
        lines.append("")
    lines.append("_Source : FRED / BLS. Surprise calculée vs précédente publication officielle._")
    return "\n".join(lines)
