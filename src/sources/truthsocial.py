"""Truth Social posts scraper (public, no auth).

Truth Social exposes a Mastodon-compatible public API. We hit the statuses
endpoint of a given account. If it fails (rate-limit, geo-block, layout
change), we silently return empty — the news.py aggregator picks up
"Trump statements" via Google News as a fallback signal.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

# Trump's account_id on Truth Social (stable since 2022)
DEFAULT_ACCOUNT_ID = "107780257626128497"
BASE_URL = "https://truthsocial.com/api/v1/accounts/{account_id}/statuses"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GoldFundBot/1.0)",
    "Accept": "application/json",
}

# Keywords that affect Gold via Trump statements
BULLISH_KW = [
    "fed", "powell", "rate cut", "lower rate", "dollar", "weak dollar",
    "tariff", "sanction", "gold", "inflation", "fire powell",
]
BEARISH_KW = [
    "deal", "agreement", "ceasefire", "strong dollar", "rate hike",
    "boom", "great economy",
]


def fetch_truth_social_posts(
    account_id: str = DEFAULT_ACCOUNT_ID,
    limit: int = 10,
    hours_lookback: int = 24,
) -> dict:
    out: dict = {
        "items": [],
        "bull_hits": 0,
        "bear_hits": 0,
        "tilt": "neutral",
        "failed": False,
    }
    try:
        with httpx.Client(timeout=12.0, headers=HEADERS, follow_redirects=True) as client:
            r = client.get(
                BASE_URL.format(account_id=account_id),
                params={"limit": limit, "exclude_replies": "true"},
            )
            if r.status_code != 200:
                logger.warning("Truth Social returned %s", r.status_code)
                out["failed"] = True
                return out
            data = r.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Truth Social fetch failed: %s", exc)
        out["failed"] = True
        return out

    if not isinstance(data, list):
        out["failed"] = True
        return out

    cutoff = datetime.now(timezone.utc).timestamp() - hours_lookback * 3600
    items = []
    bull = bear = 0
    for post in data:
        created_at = post.get("created_at")
        if created_at:
            try:
                ts = datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
                if ts < cutoff:
                    continue
            except ValueError:
                pass
        content_html = post.get("content") or ""
        text = _strip_html(content_html)
        if not text:
            continue
        url = post.get("url") or ""
        blob = text.lower()
        b_hits = sum(1 for kw in BULLISH_KW if kw in blob)
        s_hits = sum(1 for kw in BEARISH_KW if kw in blob)
        if b_hits > s_hits:
            bull += 1
        elif s_hits > b_hits:
            bear += 1
        items.append(
            {
                "text": text[:280],
                "url": url,
                "created_at": created_at,
                "bull_hits": b_hits,
                "bear_hits": s_hits,
            }
        )

    out["items"] = items
    out["bull_hits"] = bull
    out["bear_hits"] = bear
    out["tilt"] = (
        "bullish" if bull > bear else "bearish" if bear > bull else "neutral"
    )
    return out


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ").strip()
