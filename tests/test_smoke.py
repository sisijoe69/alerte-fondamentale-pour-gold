"""Smoke tests — no network, just imports + scoring + rendering + DB roundtrip."""
from __future__ import annotations

import importlib
import os
from pathlib import Path


def test_imports():
    for mod in (
        "src.config",
        "src.scoring",
        "src.report",
        "src.analysis",
        "src.bot",
        "src.cli",
        "src.db",
        "src.alerts",
        "src.chart",
        "src.webhook",
        "src.sources.fred",
        "src.sources.markets",
        "src.sources.cot",
        "src.sources.fedwatch",
        "src.sources.etf",
        "src.sources.news",
        "src.sources.calendar",
        "src.sources.truthsocial",
    ):
        importlib.import_module(mod)


def test_scoring_and_report_with_stub_data():
    from src.scoring import score_all
    from src.report import render_report
    from src.sources.calendar import CalendarEvent

    fred = {
        "real_rate_10y": 1.2, "breakeven_10y": 2.5, "dxy": 102.5,
        "us10y": 4.2, "us2y": 4.0, "yield_curve_bps": 20,
        "cpi_yoy": 3.2, "pce_yoy": 2.9, "nfp_last": 180.0, "vix": 18.5,
    }
    markets = {
        "gold_price": 2400.0, "gold_change_24h_pct": 0.6, "gold_change_7d_pct": 1.8,
        "xau_xag_ratio": 84.0, "dxy_live": 102.5, "dxy_change_5d_pct": -0.5,
        "dxy_below_ma50": True, "vix_live": 18.5,
        "gld_close": 215.4, "gld_change_5d_pct": 1.2,
    }
    cot = {"report_date": "2026-05-20", "managed_money_long": 180_000,
           "managed_money_short": 40_000, "managed_money_net": 140_000}
    fedwatch = {"next_meeting": "2026-06-17", "prob_cut": 65, "prob_hold": 33, "prob_hike": 2}
    etf = {"gld_tonnes": 870.5, "gld_tonnes_change_5d": 4.2, "gld_date": "2026-05-23"}
    news = {
        "items": [{"source": "ZeroHedge", "title": "Gold rally as Fed signals cut", "link": "", "published": None}],
        "bull_hits": 5, "bear_hits": 1, "neutral_hits": 2, "tilt": "bullish",
        "total_items": 8, "failed_sources": [],
    }
    truthsocial = {
        "items": [{"text": "Powell must lower rates NOW!", "url": "", "created_at": None,
                   "bull_hits": 2, "bear_hits": 0}],
        "bull_hits": 1, "bear_hits": 0, "tilt": "bullish", "failed": False,
    }
    events = [CalendarEvent(date="2026-06-17", event="FOMC Meeting", impact="FORT")]

    score = score_all(fred, markets, cot, fedwatch, etf, news)
    assert score.bull_count > 0
    report = render_report(fred, markets, cot, fedwatch, etf, news, events, score, truthsocial=truthsocial)
    assert "GOLD FUNDAMENTAL REPORT" in report
    assert "Trump" in report
    assert "BIAIS" in report


def test_db_roundtrip(tmp_path):
    from src.db import Database

    db = Database(tmp_path / "test.db")
    created = db.upsert_subscriber(user_id=42, chat_id=42, username="alice", first_name="Alice", is_admin=True)
    assert created is True
    again = db.upsert_subscriber(user_id=42, chat_id=42, username="alice", first_name="Alice")
    assert again is False

    sub = db.get_subscriber(42)
    assert sub and sub.is_admin and sub.receives_daily

    db.set_pref(42, alerts=False)
    assert db.get_subscriber(42).receives_alerts is False

    rid = db.save_report(
        bias="HAUSSIER", conviction="FORTE", bull_count=8, bear_count=0,
        gold_price=2400.0, summary="test", raw={"foo": "bar"},
    )
    assert rid > 0
    reports = db.last_reports(limit=5)
    assert len(reports) == 1 and reports[0].bias == "HAUSSIER"

    assert db.macro_known("CPIAUCSL", "2026-05-01") is False
    db.macro_remember("CPIAUCSL", "2026-05-01", 320.5)
    assert db.macro_known("CPIAUCSL", "2026-05-01") is True
    last = db.macro_last_value("CPIAUCSL")
    assert last == ("2026-05-01", 320.5)


def test_alerts_format():
    from src.alerts import MacroEvent, format_alert_message

    events = [
        MacroEvent(
            series_id="CPIAUCSL", name="CPI (US Inflation)",
            observation_date="2026-05-01", value=323.1, prior_value=322.0,
            surprise=0.4, bullish_for_gold=True,
            headline="📢 *CPI* publié : 323.10 (prior 322.00) (YoY shift +0.40pp)",
        )
    ]
    text = format_alert_message(events)
    assert "ALERTE MACRO" in text
    assert "CPI" in text


def test_webhook_format():
    from src.webhook import _format_payload

    msg = _format_payload(
        {"symbol": "XAUUSD", "action": "BUY", "price": 2402.5, "message": "Break out"},
        last_bias="HAUSSIER (FORTE)",
    )
    assert "BUY XAUUSD" in msg
    assert "2402.5" in msg
    assert "HAUSSIER" in msg


def test_config_missing_token(monkeypatch):
    from src import config

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    import pytest

    with pytest.raises(RuntimeError):
        config.load_settings()
