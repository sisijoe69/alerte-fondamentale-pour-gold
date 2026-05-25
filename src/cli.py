"""CLI entrypoint: run a single analysis and print to stdout.

Useful for debugging / cron alternatives:
    python -m src.cli            -> print report
    python -m src.cli --send     -> also push to the configured Telegram chat
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from telegram import Bot
from telegram.constants import ParseMode

from .analysis import run_analysis
from .config import load_settings, setup_logging

logger = logging.getLogger(__name__)


async def _send(bot_token: str, chat_id: int, text: str) -> None:
    bot = Bot(token=bot_token)
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
    parser.add_argument("--send", action="store_true", help="Also push the report to Telegram")
    parser.add_argument(
        "--no-network",
        action="store_true",
        help="(reserved) skip outbound calls — sources will likely return empty",
    )
    args = parser.parse_args()

    settings = load_settings()
    setup_logging(settings.log_level)
    result = run_analysis(settings)
    print(result.report_markdown)
    if args.send:
        try:
            asyncio.run(_send(settings.telegram_bot_token, settings.telegram_chat_id, result.report_markdown))
            logger.info("Pushed report to Telegram chat %s", settings.telegram_chat_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("Telegram send failed: %s", exc)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
