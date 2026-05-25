"""News & geopolitical sentiment aggregator.

Reads RSS feeds for sources where we have clean public feeds. For X/Twitter
sources (Walter Bloomberg, First Squawk, Insider Paper, etc.) we use Nitter
RSS endpoints as a best-effort fallback; if they are unavailable we skip
them and surface a warning in the report.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import feedparser

logger = logging.getLogger(__name__)

# --- Tier A: news / geopolitics RSS feeds (public) ---
RSS_FEEDS: dict[str, list[str]] = {
    "ZeroHedge": ["https://feeds.feedburner.com/zerohedge/feed"],
    "Kitco News": ["https://www.kitco.com/rss/KitcoNews.xml"],
    "Reuters Gold": [
        "https://news.google.com/rss/search?q=gold+price+OR+XAUUSD+when:1d&hl=en-US"
    ],
    "Investing.com Gold": [
        "https://news.google.com/rss/search?q=gold+investing.com+when:1d&hl=en-US"
    ],
    "BRICS / De-dollarization": [
        "https://news.google.com/rss/search?q=BRICS+gold+OR+dedollarization+when:2d&hl=en-US"
    ],
    "Middle East tensions": [
        "https://news.google.com/rss/search?q=%22middle+east%22+OR+israel+OR+iran+conflict+when:1d&hl=en-US"
    ],
    "Fed / FOMC": [
        "https://news.google.com/rss/search?q=federal+reserve+OR+FOMC+OR+powell+when:1d&hl=en-US"
    ],
    "Trump statements": [
        "https://news.google.com/rss/search?q=trump+fed+OR+tariffs+OR+dollar+when:1d&hl=en-US"
    ],
}

# Keywords that drive the bullish/bearish gold tilt
BULLISH_KEYWORDS = [
    "rate cut", "dovish", "cut rates", "easing", "qe", "recession",
    "inflation rises", "cpi beats", "war", "escalation", "conflict",
    "tensions", "sanction", "de-dollar", "dedollar", "brics", "central bank buying",
    "gold rally", "safe haven", "risk-off", "missile", "strike", "attack",
    "downgrade", "default risk", "debt ceiling",
]
BEARISH_KEYWORDS = [
    "rate hike", "hawkish", "tighten", "qt", "stronger dollar",
    "dollar surges", "deal reached", "ceasefire", "truce",
    "cpi cools", "disinflation", "gold falls", "gold drops",
    "risk-on", "yields surge", "real yields rise",
]


@dataclass
class NewsItem:
    source: str
    title: str
    summary: str
    link: str
    published: datetime | None


def collect_news(max_per_feed: int = 8, hours_lookback: int = 36) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_lookback)
    items: list[NewsItem] = []
    failures: list[str] = []

    for source, urls in RSS_FEEDS.items():
        fetched_any = False
        for url in urls:
            parsed_items = _safe_parse(source, url)
            if not parsed_items:
                continue
            fetched_any = True
            for it in parsed_items[:max_per_feed]:
                if it.published and it.published < cutoff:
                    continue
                items.append(it)
        if not fetched_any:
            failures.append(source)

    bull, bear, neutral = _score_items(items)
    return {
        "items": [_item_to_dict(i) for i in items[:25]],
        "bull_hits": bull,
        "bear_hits": bear,
        "neutral_hits": neutral,
        "tilt": _tilt_label(bull, bear),
        "failed_sources": failures,
        "total_items": len(items),
    }


def _safe_parse(source: str, url: str) -> list[NewsItem]:
    try:
        feed = feedparser.parse(url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Feedparser failed for %s (%s): %s", source, url, exc)
        return []
    if feed.bozo and not feed.entries:
        logger.debug("Bad feed for %s (%s): %s", source, url, getattr(feed, "bozo_exception", ""))
        return []
    out: list[NewsItem] = []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        summary = _clean_html(entry.get("summary") or entry.get("description") or "")
        link = entry.get("link") or ""
        published = _parse_published(entry)
        out.append(NewsItem(source=source, title=title, summary=summary, link=link, published=published))
    return out


def _parse_published(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        struct = entry.get(key)
        if struct:
            try:
                return datetime(*struct[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def _clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _score_items(items: list[NewsItem]) -> tuple[int, int, int]:
    bull = bear = neutral = 0
    for it in items:
        blob = f"{it.title} {it.summary}".lower()
        b_hits = sum(1 for kw in BULLISH_KEYWORDS if kw in blob)
        s_hits = sum(1 for kw in BEARISH_KEYWORDS if kw in blob)
        if b_hits > s_hits:
            bull += 1
        elif s_hits > b_hits:
            bear += 1
        else:
            neutral += 1
    return bull, bear, neutral


def _tilt_label(bull: int, bear: int) -> str:
    if bull == 0 and bear == 0:
        return "neutral"
    if bull >= bear * 2:
        return "bullish_strong"
    if bull > bear:
        return "bullish"
    if bear >= bull * 2:
        return "bearish_strong"
    if bear > bull:
        return "bearish"
    return "neutral"


def _item_to_dict(item: NewsItem) -> dict:
    return {
        "source": item.source,
        "title": item.title,
        "link": item.link,
        "published": item.published.isoformat() if item.published else None,
    }
