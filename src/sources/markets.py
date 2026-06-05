"""Market data via Yahoo Finance (Gold spot, DXY, VIX, yields, ETFs)."""
from __future__ import annotations

import logging
from datetime import datetime

import yfinance as yf

logger = logging.getLogger(__name__)

TICKERS = {
    "gold": "GC=F",        # COMEX Gold front month future (proxy for spot)
    "gold_spot": "XAUUSD=X",
    "silver": "SI=F",
    "dxy": "DX-Y.NYB",
    "vix": "^VIX",
    "us10y_yield": "^TNX",
    "us2y_yield": "^IRX",  # actually 13W T-bill; closest free proxy
    "gld": "GLD",
    "iau": "IAU",
}


def _safe_history(ticker: str, period: str = "1mo"):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period, interval="1d", auto_adjust=False)
        if hist is None or hist.empty:
            return None
        return hist
    except Exception as exc:  # noqa: BLE001
        logger.warning("yfinance history failed for %s: %s", ticker, exc)
        return None


def collect_markets() -> dict:
    out: dict = {"timestamp": datetime.utcnow().isoformat() + "Z"}

    gold_hist = _safe_history(TICKERS["gold_spot"]) or _safe_history(TICKERS["gold"])
    if gold_hist is not None and not gold_hist.empty:
        last_close = float(gold_hist["Close"].iloc[-1])
        out["gold_price"] = round(last_close, 2)
        out["gold_change_24h_pct"] = _pct_change(gold_hist, lookback=1)
        out["gold_change_7d_pct"] = _pct_change(gold_hist, lookback=5)
    else:
        out["gold_price"] = None
        out["gold_change_24h_pct"] = None
        out["gold_change_7d_pct"] = None

    silver_hist = _safe_history(TICKERS["silver"])
    if silver_hist is not None and not silver_hist.empty and gold_hist is not None and not gold_hist.empty:
        try:
            out["xau_xag_ratio"] = round(
                float(gold_hist["Close"].iloc[-1]) / float(silver_hist["Close"].iloc[-1]), 2
            )
        except (ZeroDivisionError, ValueError):
            out["xau_xag_ratio"] = None
    else:
        out["xau_xag_ratio"] = None

    dxy_hist = _safe_history(TICKERS["dxy"])
    if dxy_hist is not None and not dxy_hist.empty:
        out["dxy_live"] = round(float(dxy_hist["Close"].iloc[-1]), 3)
        out["dxy_change_5d_pct"] = _pct_change(dxy_hist, lookback=5)
        # crude MA50 (using whatever history we have - bound at 50)
        ma_series = dxy_hist["Close"].tail(50)
        out["dxy_below_ma50"] = bool(dxy_hist["Close"].iloc[-1] < ma_series.mean())
    else:
        out["dxy_live"] = None
        out["dxy_change_5d_pct"] = None
        out["dxy_below_ma50"] = None

    vix_hist = _safe_history(TICKERS["vix"])
    out["vix_live"] = (
        round(float(vix_hist["Close"].iloc[-1]), 2)
        if vix_hist is not None and not vix_hist.empty
        else None
    )

    us10y_hist = _safe_history(TICKERS["us10y_yield"])
    out["us10y_yield_live"] = (
        round(float(us10y_hist["Close"].iloc[-1]) / 10.0, 3)  # ^TNX is quoted x10
        if us10y_hist is not None and not us10y_hist.empty
        else None
    )

    gld_hist = _safe_history(TICKERS["gld"], period="3mo")
    if gld_hist is not None and not gld_hist.empty:
        out["gld_close"] = round(float(gld_hist["Close"].iloc[-1]), 2)
        out["gld_change_5d_pct"] = _pct_change(gld_hist, lookback=5)
        out["gld_change_20d_pct"] = _pct_change(gld_hist, lookback=20)
        try:
            out["gld_volume_last"] = int(gld_hist["Volume"].iloc[-1])
        except (KeyError, ValueError):
            out["gld_volume_last"] = None
    else:
        out["gld_close"] = None
        out["gld_change_5d_pct"] = None
        out["gld_change_20d_pct"] = None
        out["gld_volume_last"] = None

    return out


def _pct_change(hist, lookback: int) -> float | None:
    try:
        if len(hist) <= lookback:
            return None
        latest = float(hist["Close"].iloc[-1])
        prior = float(hist["Close"].iloc[-1 - lookback])
        if prior == 0:
            return None
        return round((latest / prior - 1) * 100, 2)
    except (KeyError, ValueError, TypeError, IndexError):
        return None
