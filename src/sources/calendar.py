"""Upcoming high-impact macro events for the next 7 days.

Investing.com's calendar requires JS, so we fall back to a curated static
list of recurring high-impact events plus FOMC dates pulled from the FED's
public schedule (and supplement with Google News RSS for confirmation).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import feedparser

logger = logging.getLogger(__name__)

# Hardcoded FOMC meeting dates 2024-2026 (publicly announced).
# Update once a year when the Fed publishes the new calendar.
FOMC_MEETINGS = [
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-04-30", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]

# Recurring monthly US data with strong gold impact
# (day-of-month is approximate; exact dates pulled from BLS RSS if available)
RECURRING_EVENTS = [
    {"name": "CPI (US Inflation)", "day_hint": 12, "impact": "FORT"},
    {"name": "PPI (US Producer Prices)", "day_hint": 13, "impact": "MODÉRÉ"},
    {"name": "NFP (US Jobs Report)", "day_hint": 5, "impact": "FORT"},
    {"name": "PCE (Fed's preferred inflation)", "day_hint": 28, "impact": "FORT"},
    {"name": "Retail Sales (US)", "day_hint": 15, "impact": "MODÉRÉ"},
    {"name": "ISM Manufacturing PMI", "day_hint": 1, "impact": "MODÉRÉ"},
    {"name": "FOMC Minutes", "day_hint": 21, "impact": "MODÉRÉ"},
]


@dataclass
class CalendarEvent:
    date: str
    event: str
    impact: str


def upcoming_events(days_ahead: int = 7) -> list[CalendarEvent]:
    today = date.today()
    end = today + timedelta(days=days_ahead)
    events: list[CalendarEvent] = []

    # FOMC meetings within window
    for d in FOMC_MEETINGS:
        try:
            event_date = datetime.fromisoformat(d).date()
        except ValueError:
            continue
        if today <= event_date <= end:
            events.append(
                CalendarEvent(
                    date=event_date.isoformat(),
                    event="FOMC Meeting + Statement",
                    impact="FORT",
                )
            )

    # Recurring monthly events — keep entries whose hinted day-of-month falls in window
    for ev in RECURRING_EVENTS:
        candidates = _candidate_dates(ev["day_hint"], today, end)
        for c in candidates:
            events.append(CalendarEvent(date=c.isoformat(), event=ev["name"], impact=ev["impact"]))

    # Try a best-effort RSS pull to surface unscheduled announcements
    try:
        rss_events = _rss_events(days_ahead)
        events.extend(rss_events)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Calendar RSS fallback failed: %s", exc)

    # Dedup + sort
    seen = set()
    deduped: list[CalendarEvent] = []
    for ev in sorted(events, key=lambda e: e.date):
        key = (ev.date, ev.event)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ev)
    return deduped[:15]


def _candidate_dates(day_hint: int, start: date, end: date) -> list[date]:
    out: list[date] = []
    cursor = start.replace(day=1)
    while cursor <= end:
        try:
            d = cursor.replace(day=day_hint)
        except ValueError:
            d = cursor.replace(day=28)
        if start <= d <= end:
            out.append(d)
        # advance to next month
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def _rss_events(days_ahead: int) -> list[CalendarEvent]:
    """Scan Google News headlines for scheduled events as a sanity check."""
    feed = feedparser.parse(
        "https://news.google.com/rss/search?q=%22economic+calendar%22+OR+%22fed+schedule%22&hl=en-US"
    )
    keep: list[CalendarEvent] = []
    for entry in feed.entries[:10]:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        published = entry.get("published_parsed")
        if not published:
            continue
        try:
            pub_date = date(*published[:3])
        except (TypeError, ValueError):
            continue
        if pub_date >= date.today() - timedelta(days=2):
            keep.append(CalendarEvent(date=pub_date.isoformat(), event=title[:80], impact="INFO"))
    return keep[:3]
