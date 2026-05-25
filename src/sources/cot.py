"""CFTC Commitment of Traders (COT) connector — Gold futures positioning.

Pulls the latest TFF "Disaggregated" or "Legacy" report for gold via the public
data.cftc.gov Socrata endpoint (no auth required).
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

# Socrata dataset: CFTC Disaggregated Futures Only Reports (commodity)
# https://publicreporting.cftc.gov/resource/72hh-3qpy.json
SOCRATA_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
GOLD_CONTRACT_MARKET_NAME = "GOLD"
GOLD_CFTC_CODE = "088691"  # Gold COMEX


def fetch_cot() -> dict:
    out: dict = {
        "report_date": None,
        "managed_money_long": None,
        "managed_money_short": None,
        "managed_money_net": None,
        "noncomm_long": None,
        "noncomm_short": None,
        "noncomm_net": None,
        "open_interest": None,
    }
    try:
        params = {
            "$where": f"cftc_contract_market_code='{GOLD_CFTC_CODE}'",
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": 1,
        }
        headers = {"User-Agent": "Mozilla/5.0 (compatible; GoldFundBot/1.0)"}
        with httpx.Client(timeout=15.0, headers=headers) as client:
            r = client.get(SOCRATA_URL, params=params)
            r.raise_for_status()
            data = r.json()
        if not data:
            logger.warning("COT endpoint returned no rows for Gold")
            return out
        row = data[0]
        out["report_date"] = row.get("report_date_as_yyyy_mm_dd")
        mm_long = _to_int(row.get("m_money_positions_long_all"))
        mm_short = _to_int(row.get("m_money_positions_short_all"))
        nc_long = _to_int(row.get("noncomm_positions_long_all"))
        nc_short = _to_int(row.get("noncomm_positions_short_all"))
        out["managed_money_long"] = mm_long
        out["managed_money_short"] = mm_short
        out["managed_money_net"] = (
            mm_long - mm_short if mm_long is not None and mm_short is not None else None
        )
        out["noncomm_long"] = nc_long
        out["noncomm_short"] = nc_short
        out["noncomm_net"] = (
            nc_long - nc_short if nc_long is not None and nc_short is not None else None
        )
        out["open_interest"] = _to_int(row.get("open_interest_all"))
    except Exception as exc:  # noqa: BLE001
        logger.error("COT fetch failed: %s", exc)
    return out


def _to_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None
