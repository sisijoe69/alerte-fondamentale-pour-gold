"""GLD / IAU ETF flows.

SPDR publishes daily holdings of GLD as a CSV; iShares publishes IAU holdings
as JSON. The CSV format is more stable, so we use it for GLD and approximate
IAU flows from share count + close price via yfinance.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

GLD_HOLDINGS_CSV = "https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv"


def fetch_etf_holdings() -> dict:
    out: dict = {
        "gld_tonnes": None,
        "gld_tonnes_prev": None,
        "gld_tonnes_change_5d": None,
        "gld_aum_usd": None,
        "gld_date": None,
    }
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            r = client.get(
                GLD_HOLDINGS_CSV,
                headers={"User-Agent": "Mozilla/5.0 (compatible; GoldFundBot/1.0)"},
            )
            r.raise_for_status()
            text = r.text
        rows = _parse_gld_csv(text)
        if rows:
            # rows are date-sorted ascending; latest at end
            latest = rows[-1]
            prev_5d = rows[-6] if len(rows) >= 6 else rows[0]
            out["gld_tonnes"] = latest["tonnes"]
            out["gld_aum_usd"] = latest["aum_usd"]
            out["gld_date"] = latest["date"]
            out["gld_tonnes_prev"] = prev_5d["tonnes"]
            if latest["tonnes"] is not None and prev_5d["tonnes"] is not None:
                out["gld_tonnes_change_5d"] = round(latest["tonnes"] - prev_5d["tonnes"], 2)
    except Exception as exc:  # noqa: BLE001
        logger.warning("GLD holdings fetch failed: %s", exc)
    return out


def _parse_gld_csv(text: str) -> list[dict]:
    """SPDR's archive CSV has a few preamble lines, then a header row."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    # Find header line containing "Date" and "Tonnes" (case-insensitive)
    start = None
    for i, ln in enumerate(lines):
        if "Date" in ln and ("Tonnes" in ln or "Tonnes in the Trust" in ln):
            start = i
            break
    if start is None:
        return []
    reader = csv.DictReader(lines[start:])
    parsed: list[dict] = []
    for row in reader:
        date_str = (row.get("Date") or "").strip()
        tonnes_str = (
            row.get("Tonnes in the Trust") or row.get("Tonnes") or ""
        ).strip().replace(",", "")
        aum_str = (
            row.get("Value (USD)") or row.get("AUM") or ""
        ).strip().replace(",", "").replace("$", "")
        try:
            parsed.append(
                {
                    "date": _norm_date(date_str),
                    "tonnes": float(tonnes_str) if tonnes_str else None,
                    "aum_usd": float(aum_str) if aum_str else None,
                }
            )
        except ValueError:
            continue
    # Sort by date ascending
    parsed.sort(key=lambda r: r["date"] or "")
    return parsed


def _norm_date(raw: str) -> str | None:
    if not raw:
        return None
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return raw
