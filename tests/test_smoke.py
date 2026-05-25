"""Smoke tests — no network, just import + scoring + rendering with stub data."""
from __future__ import annotations

import importlib


def test_imports():
    for mod in (
        "src.config",
        "src.scoring",
        "src.report",
        "src.analysis",
        "src.bot",
        "src.cli",
        "src.sources.fred",
        "src.sources.markets",
        "src.sources.cot",
        "src.sources.fedwatch",
        "src.sources.etf",
        "src.sources.news",
        "src.sources.calendar",
    ):
        importlib.import_module(mod)


def test_scoring_and_report_with_stub_data():
    from src.scoring import score_all
    from src.report import render_report
    from src.sources.calendar import CalendarEvent

    fred = {
        "real_rate_10y": 1.2,
        "breakeven_10y": 2.5,
        "dxy": 102.5,
        "us10y": 4.2,
        "us2y": 4.0,
        "yield_curve_bps": 20,
        "cpi_yoy": 3.2,
        "pce_yoy": 2.9,
        "nfp_last": 180.0,
        "vix": 18.5,
    }
    markets = {
        "gold_price": 2400.0,
        "gold_change_24h_pct": 0.6,
        "gold_change_7d_pct": 1.8,
        "xau_xag_ratio": 84.0,
        "dxy_live": 102.5,
        "dxy_change_5d_pct": -0.5,
        "dxy_below_ma50": True,
        "vix_live": 18.5,
        "gld_close": 215.4,
        "gld_change_5d_pct": 1.2,
    }
    cot = {
        "report_date": "2026-05-20",
        "managed_money_long": 180_000,
        "managed_money_short": 40_000,
        "managed_money_net": 140_000,
    }
    fedwatch = {"next_meeting": "2026-06-17", "prob_cut": 65, "prob_hold": 33, "prob_hike": 2}
    etf = {"gld_tonnes": 870.5, "gld_tonnes_change_5d": 4.2, "gld_date": "2026-05-23"}
    news = {
        "items": [
            {"source": "ZeroHedge", "title": "Gold rally as Fed signals rate cut", "link": "", "published": None}
        ],
        "bull_hits": 5,
        "bear_hits": 1,
        "neutral_hits": 2,
        "tilt": "bullish",
        "total_items": 8,
        "failed_sources": [],
    }
    events = [
        CalendarEvent(date="2026-06-12", event="CPI (US Inflation)", impact="FORT"),
        CalendarEvent(date="2026-06-17", event="FOMC Meeting + Statement", impact="FORT"),
    ]

    score = score_all(fred, markets, cot, fedwatch, etf, news)
    assert score.bull_count > 0
    report = render_report(fred, markets, cot, fedwatch, etf, news, events, score)
    assert "GOLD FUNDAMENTAL REPORT" in report
    assert "BIAIS" in report
    assert "Trade Setup" in report or "TRADE SETUP" in report.upper() or score.bias_label() == "NEUTRE"


def test_config_missing_token(monkeypatch):
    from src import config

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    import pytest

    with pytest.raises(RuntimeError):
        config.load_settings()
