"""FRED (Federal Reserve Economic Data) connector.

Pulls real rates, breakeven inflation, DXY, US10Y/US2Y, CPI, PCE, NFP via the
public FRED API. Falls back to scraping the public CSV endpoint when no API
key is configured.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

# Series IDs documented at https://fred.stlouisfed.org/
SERIES = {
    "real_rate_10y": "DFII10",        # 10Y TIPS yield
    "breakeven_10y": "T10YIE",        # 10Y breakeven inflation
    "dxy": "DTWEXBGS",                # USD broad index (close proxy to DXY)
    "us10y": "DGS10",                 # 10Y nominal Treasury
    "us2y": "DGS2",                   # 2Y nominal Treasury
    "cpi_yoy": "CPIAUCSL",            # CPI all urban consumers (compute YoY)
    "pce_yoy": "PCEPI",               # PCE price index (compute YoY)
    "nfp": "PAYEMS",                  # Total nonfarm payrolls (compute MoM diff)
    "vix": "VIXCLS",                  # CBOE VIX
}


@dataclass
class FredObservation:
    series_id: str
    value: float | None
    date: str
    raw: list[dict] | None = None


class FredClient:
    BASE = "https://api.stlouisfed.org/fred/series/observations"
    FALLBACK = "https://fred.stlouisfed.org/graph/fredgraph.csv"
    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GoldFundBot/1.0)"}

    def __init__(self, api_key: str | None, timeout: float = 15.0):
        self.api_key = api_key
        self.timeout = timeout

    def fetch(self, series_id: str, lookback_days: int = 720) -> FredObservation:
        end = datetime.utcnow().date()
        start = end - timedelta(days=lookback_days)
        if self.api_key:
            try:
                return self._fetch_api(series_id, start.isoformat(), end.isoformat())
            except Exception as exc:  # noqa: BLE001
                logger.warning("FRED API failed for %s (%s) — falling back to CSV", series_id, exc)
        return self._fetch_csv(series_id, start.isoformat(), end.isoformat())

    def _fetch_api(self, series_id: str, start: str, end: str) -> FredObservation:
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start,
            "observation_end": end,
            "sort_order": "desc",
        }
        with httpx.Client(timeout=self.timeout, headers=self.HEADERS) as client:
            r = client.get(self.BASE, params=params)
            r.raise_for_status()
            data = r.json()
        obs = data.get("observations", [])
        latest = next((o for o in obs if o.get("value") not in (".", "", None)), None)
        if not latest:
            return FredObservation(series_id=series_id, value=None, date="", raw=obs)
        return FredObservation(
            series_id=series_id,
            value=float(latest["value"]),
            date=latest["date"],
            raw=obs,
        )

    def _fetch_csv(self, series_id: str, start: str, end: str) -> FredObservation:
        params = {"id": series_id, "cosd": start, "coed": end}
        with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.HEADERS) as client:
            r = client.get(self.FALLBACK, params=params)
            r.raise_for_status()
            lines = [ln for ln in r.text.strip().splitlines() if ln]
        if len(lines) < 2:
            return FredObservation(series_id=series_id, value=None, date="")
        header = lines[0].split(",")
        rows = [dict(zip(header, ln.split(","))) for ln in lines[1:]]
        value_col = header[1] if len(header) > 1 else "VALUE"
        # iterate from the end to find the latest non-"." value
        for row in reversed(rows):
            v = row.get(value_col)
            if v and v != ".":
                try:
                    return FredObservation(
                        series_id=series_id,
                        value=float(v),
                        date=row.get(header[0], ""),
                        raw=rows,
                    )
                except ValueError:
                    continue
        return FredObservation(series_id=series_id, value=None, date="", raw=rows)


def collect_fred(api_key: str | None) -> dict:
    """Collect the headline FRED indicators we use to score Gold."""
    client = FredClient(api_key)
    snapshot: dict = {}

    def safe(name: str) -> FredObservation | None:
        try:
            return client.fetch(SERIES[name])
        except Exception as exc:  # noqa: BLE001
            logger.error("FRED fetch failed for %s: %s", name, exc)
            return None

    real_rate_10y = safe("real_rate_10y")
    breakeven_10y = safe("breakeven_10y")
    dxy = safe("dxy")
    us10y = safe("us10y")
    us2y = safe("us2y")
    cpi = safe("cpi_yoy")
    pce = safe("pce_yoy")
    nfp = safe("nfp")
    vix = safe("vix")

    snapshot["real_rate_10y"] = real_rate_10y.value if real_rate_10y else None
    snapshot["real_rate_10y_date"] = real_rate_10y.date if real_rate_10y else None
    snapshot["breakeven_10y"] = breakeven_10y.value if breakeven_10y else None
    snapshot["dxy"] = dxy.value if dxy else None
    snapshot["us10y"] = us10y.value if us10y else None
    snapshot["us2y"] = us2y.value if us2y else None
    snapshot["yield_curve_bps"] = (
        round((us10y.value - us2y.value) * 100, 1)
        if us10y and us2y and us10y.value is not None and us2y.value is not None
        else None
    )
    snapshot["vix"] = vix.value if vix else None

    snapshot["cpi_yoy"] = _yoy(cpi)
    snapshot["pce_yoy"] = _yoy(pce)
    snapshot["nfp_last"] = _last_diff_thousands(nfp)

    return snapshot


def _yoy(obs: FredObservation | None) -> float | None:
    """Compute YoY % change from a series of monthly index values."""
    if not obs or not obs.raw:
        return None
    rows = [r for r in obs.raw if r.get("value") not in (".", "", None)]
    if len(rows) < 13:
        return None
    try:
        rows_sorted = sorted(rows, key=lambda r: r["date"])
        latest = float(rows_sorted[-1]["value"])
        # find observation closest to ~12 months earlier
        latest_date = datetime.fromisoformat(rows_sorted[-1]["date"]).date()
        target = latest_date - timedelta(days=365)
        prior_row = min(
            rows_sorted[:-1],
            key=lambda r: abs((datetime.fromisoformat(r["date"]).date() - target).days),
        )
        prior = float(prior_row["value"])
        if prior == 0:
            return None
        return round((latest / prior - 1) * 100, 2)
    except (KeyError, ValueError, TypeError) as exc:
        logger.debug("YoY calc failed: %s", exc)
        return None


def _last_diff_thousands(obs: FredObservation | None) -> float | None:
    """Return the last MoM diff in thousands (NFP-style)."""
    if not obs or not obs.raw:
        return None
    rows = [r for r in obs.raw if r.get("value") not in (".", "", None)]
    if len(rows) < 2:
        return None
    try:
        rows_sorted = sorted(rows, key=lambda r: r["date"])
        latest = float(rows_sorted[-1]["value"])
        prior = float(rows_sorted[-2]["value"])
        return round(latest - prior, 1)  # already in thousands of jobs
    except (KeyError, ValueError, TypeError):
        return None
