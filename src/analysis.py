"""Orchestrator: collects data from all sources, scores, and renders the report."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .config import Settings
from .report import render_report
from .scoring import ScoreResult, score_all
from .sources import calendar as cal_src
from .sources import cot as cot_src
from .sources import etf as etf_src
from .sources import fedwatch as fw_src
from .sources import fred as fred_src
from .sources import markets as mk_src
from .sources import news as news_src

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    report_markdown: str
    score: ScoreResult
    raw: dict


def run_analysis(settings: Settings) -> AnalysisResult:
    logger.info("Starting Gold fundamental analysis…")

    tasks = {
        "fred": lambda: fred_src.collect_fred(settings.fred_api_key),
        "markets": mk_src.collect_markets,
        "cot": cot_src.fetch_cot,
        "fedwatch": fw_src.fetch_fedwatch,
        "etf": etf_src.fetch_etf_holdings,
        "news": news_src.collect_news,
        "calendar": cal_src.upcoming_events,
    }

    results: dict = {}
    with ThreadPoolExecutor(max_workers=len(tasks)) as ex:
        futures = {ex.submit(fn): name for name, fn in tasks.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                results[name] = fut.result(timeout=45)
                logger.info("Source %-9s OK", name)
            except Exception as exc:  # noqa: BLE001
                logger.error("Source %-9s FAILED: %s", name, exc)
                results[name] = {} if name != "calendar" else []

    fred = results.get("fred") or {}
    markets = results.get("markets") or {}
    cot = results.get("cot") or {}
    fedwatch = results.get("fedwatch") or {}
    etf = results.get("etf") or {}
    news = results.get("news") or {}
    calendar_events = results.get("calendar") or []

    score = score_all(fred, markets, cot, fedwatch, etf, news)
    report_md = render_report(
        fred=fred,
        markets=markets,
        cot=cot,
        fedwatch=fedwatch,
        etf=etf,
        news=news,
        calendar_events=calendar_events,
        score=score,
    )
    logger.info(
        "Analysis complete | bias=%s | bull=%d bear=%d",
        score.bias_label(),
        score.bull_count,
        score.bear_count,
    )
    return AnalysisResult(report_markdown=report_md, score=score, raw=results)
