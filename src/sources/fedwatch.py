"""CME FedWatch — probability of Fed rate moves at next FOMC meeting.

CME exposes the FedWatch probabilities behind a JS-rendered page. We can use
their JSON endpoint that powers the chart.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Internal CME endpoint used by the FedWatch tool. The exact path tends to
# change; we try a couple of known endpoints and fall back gracefully.
ENDPOINTS = [
    "https://www.cmegroup.com/services/fed-watch-tool/probabilities-currentMeetingDate",
    "https://www.cmegroup.com/CmeWS/mvc/Quotes/FedWatch/Probabilities",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GoldFundBot/1.0)",
    "Accept": "application/json,text/plain,*/*",
}


def fetch_fedwatch() -> dict:
    out: dict = {
        "next_meeting": None,
        "prob_cut": None,
        "prob_hold": None,
        "prob_hike": None,
        "source": None,
    }
    for url in ENDPOINTS:
        try:
            with httpx.Client(timeout=10.0, headers=HEADERS, follow_redirects=True) as client:
                r = client.get(url)
                if r.status_code != 200:
                    logger.debug("FedWatch %s returned %s", url, r.status_code)
                    continue
                data: Any = r.json()
            parsed = _parse(data)
            if parsed:
                parsed["source"] = url
                return parsed
        except Exception as exc:  # noqa: BLE001
            logger.debug("FedWatch endpoint %s failed: %s", url, exc)
            continue
    logger.warning("All CME FedWatch endpoints failed — using None probabilities")
    return out


def _parse(data: Any) -> dict | None:
    """Best-effort parser for CME's evolving payload shape."""
    if not isinstance(data, dict):
        return None
    # Common keys observed in older payloads
    meeting = data.get("meetingDate") or data.get("nextMeeting") or data.get("date")
    cut = data.get("probCut") or data.get("ease") or data.get("cut")
    hold = data.get("probHold") or data.get("unchanged") or data.get("hold")
    hike = data.get("probHike") or data.get("tighten") or data.get("hike")
    if any(v is not None for v in (cut, hold, hike)):
        return {
            "next_meeting": meeting,
            "prob_cut": _as_pct(cut),
            "prob_hold": _as_pct(hold),
            "prob_hike": _as_pct(hike),
        }
    return None


def _as_pct(value) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
        return round(v if v <= 1 else v, 2) if v > 1 else round(v * 100, 2)
    except (ValueError, TypeError):
        return None
