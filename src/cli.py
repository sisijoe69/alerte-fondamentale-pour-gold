"""CLI entrypoint: run a single analysis and print to stdout.

Useful for debugging / cron alternatives:
    python -m src.cli            -> print report
    python -m src.cli --send     -> also push to all subscribers
    python -m src.cli --chart    -> include the Gold chart when sending
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from io import BytesIO

from telegram import Bot
from telegram.constants import ParseMode

from .analysis import run_analysis
from .chart import build_gold_chart
from .config import load_settings, setup_logging
from .db import Database

logger = logging.getLogger(__name__)


async def _send(bot_token: str, chat_ids: list[int], text: str, photo: bytes | None) -> None:
    bot = Bot(token=bot_token)
    for chat_id in chat_ids:
        try:
            if photo is not None:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=BytesIO(photo),
                    caption="📈 Gold spot — 30 jours",
                )
            await _send_text(bot, chat_id, text)
        except Exception as exc:  # noqa: BLE001
            logger.error("Send to %s failed: %s", chat_id, exc)


async def _send_text(bot: Bot, chat_id: int, text: str) -> None:
    MAX = 3900
    if len(text) <= MAX:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
        return
    chunks: list[str] = []
    cur = ""
    for line in text.splitlines(keepends=True):
        if len(cur) + len(line) > MAX:
            chunks.append(cur)
            cur = line
        else:
            cur += line
    if cur:
        chunks.append(cur)
    for i, c in enumerate(chunks, 1):
        await bot.send_message(
            chat_id=chat_id,
            text=c + (f"\n\n_(suite {i}/{len(chunks)})_" if len(chunks) > 1 else ""),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a one-shot Gold fundamental analysis")
    parser.add_argument("--send", action="store_true", help="Also push the report to all subscribers")
    parser.add_argument("--chart", action="store_true", help="Include Gold chart when sending")
    parser.add_argument("--all-subscribers", action="store_true",
                        help="Send to all subscribers (default) — set off via --primary-only")
    parser.add_argument("--primary-only", action="store_true",
                        help="Send only to TELEGRAM_CHAT_ID (owner)")
    args = parser.parse_args()

    settings = load_settings()
    setup_logging(settings.log_level)
    result = run_analysis(settings)
    print(result.report_markdown)

    if args.send:
        db = Database(settings.data_dir / "gold_bot.db")
        gold_price = result.raw.get("markets", {}).get("gold_price")
        db.save_report(
            bias=result.score.bias_label(),
            conviction=result.score.conviction_label()[0],
            bull_count=result.score.bull_count,
            bear_count=result.score.bear_count,
            gold_price=gold_price,
            summary=result.report_markdown[:200],
            raw=result.raw,
        )
        chat_ids: list[int]
        if args.primary_only:
            chat_ids = [settings.telegram_chat_id]
        else:
            subs = db.list_subscribers(only_daily=True)
            chat_ids = [s.chat_id for s in subs] or [settings.telegram_chat_id]
        photo = build_gold_chart(30) if args.chart else None
        try:
            asyncio.run(_send(settings.telegram_bot_token, chat_ids, result.report_markdown, photo))
            logger.info("Pushed report to %d chat(s)", len(chat_ids))
        except Exception as exc:  # noqa: BLE001
            logger.error("Telegram send failed: %s", exc)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
