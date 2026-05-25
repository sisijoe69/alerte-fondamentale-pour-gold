"""Telegram bot entrypoint.

- Schedules a daily analysis at the configured time and pushes the report to
  the dedicated chat.
- Exposes commands:
    /start  : Welcome message
    /id     : Print the current chat ID (useful to populate TELEGRAM_CHAT_ID)
    /now    : Trigger an immediate analysis
    /status : Show last run timestamp and next scheduled run
    /help   : Command list
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from .analysis import run_analysis
from .config import Settings, load_settings, setup_logging

logger = logging.getLogger(__name__)

# Module-level state for /status
_LAST_RUN: dict[str, datetime | str | None] = {"at": None, "bias": None, "conviction": None}


def _is_authorized(update: Update, settings: Settings) -> bool:
    if not update.effective_user:
        return False
    return update.effective_user.id in settings.authorized_user_ids


async def _send_long(bot, chat_id: int, text: str) -> None:
    """Telegram caps messages at 4096 chars — split if needed."""
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


# ── Command handlers ───────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🥇 *Gold Fundamental Bot* prêt.\n\n"
        "Commandes :\n"
        "• /now — Analyse immédiate\n"
        "• /status — État du planning\n"
        "• /id — Récupérer votre chat ID\n"
        "• /help — Aide",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id if update.effective_chat else "?"
    user_id = update.effective_user.id if update.effective_user else "?"
    await update.message.reply_text(
        f"Chat ID : `{chat_id}`\nUser ID : `{user_id}`\n\n"
        "Collez l'un de ces IDs dans `TELEGRAM_CHAT_ID` (.env).",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    scheduler: AsyncIOScheduler = context.application.bot_data["scheduler"]
    job = scheduler.get_job("daily_gold_analysis")
    next_run = job.next_run_time if job else None
    last_at = _LAST_RUN.get("at")
    msg_lines = [
        "📊 *Statut du bot Gold*",
        f"• Dernière analyse : {last_at.strftime('%Y-%m-%d %H:%M %Z') if isinstance(last_at, datetime) else 'jamais'}",
        f"• Prochain run auto : {next_run.strftime('%Y-%m-%d %H:%M %Z') if next_run else 'non planifié'}",
        f"• Timezone : {settings.timezone}",
        f"• Heure quotidienne : {settings.daily_run_time}",
    ]
    if _LAST_RUN.get("bias"):
        msg_lines.append(f"• Dernier biais : {_LAST_RUN['bias']} ({_LAST_RUN['conviction']})")
    await update.message.reply_text("\n".join(msg_lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not _is_authorized(update, settings):
        await update.message.reply_text("⛔ Non autorisé.")
        return
    await update.message.reply_text("⏳ Analyse en cours… (15-30 sec)")
    try:
        result = await asyncio.to_thread(run_analysis, settings)
        _LAST_RUN["at"] = datetime.now(ZoneInfo(settings.timezone))
        _LAST_RUN["bias"] = result.score.bias_label()
        _LAST_RUN["conviction"] = result.score.conviction_label()[0]
        await _send_long(context.bot, update.effective_chat.id, result.report_markdown)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Manual analysis failed")
        await update.message.reply_text(f"❌ Erreur pendant l'analyse : `{exc}`", parse_mode=ParseMode.MARKDOWN)


# ── Scheduled job ──────────────────────────────────────────────────────

async def scheduled_run(application: Application) -> None:
    settings: Settings = application.bot_data["settings"]
    logger.info("Daily scheduled analysis triggered")
    try:
        result = await asyncio.to_thread(run_analysis, settings)
        _LAST_RUN["at"] = datetime.now(ZoneInfo(settings.timezone))
        _LAST_RUN["bias"] = result.score.bias_label()
        _LAST_RUN["conviction"] = result.score.conviction_label()[0]
        await _send_long(application.bot, settings.telegram_chat_id, result.report_markdown)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Scheduled analysis failed")
        try:
            await application.bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=f"❌ *Échec de l'analyse quotidienne* : `{exc}`",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to even notify Telegram of the failure")


# ── Application bootstrap ──────────────────────────────────────────────

def _parse_hhmm(value: str) -> tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"DAILY_RUN_TIME must be HH:MM, got {value!r}")
    return int(parts[0]), int(parts[1])


def build_application(settings: Settings) -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.bot_data["settings"] = settings

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("now", cmd_now))
    app.add_handler(CommandHandler("analyse", cmd_now))
    app.add_handler(CommandHandler("status", cmd_status))

    tz = ZoneInfo(settings.timezone)
    scheduler = AsyncIOScheduler(timezone=tz)
    hour, minute = _parse_hhmm(settings.daily_run_time)
    scheduler.add_job(
        scheduled_run,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=tz),
        args=[app],
        id="daily_gold_analysis",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    app.bot_data["scheduler"] = scheduler

    async def _post_init(application: Application) -> None:
        scheduler.start()
        logger.info(
            "Scheduler started — next run at %s (%s)",
            scheduler.get_job("daily_gold_analysis").next_run_time,
            settings.timezone,
        )
        await application.bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=(
                "✅ *Gold Fundamental Bot en ligne*\n"
                f"Prochaine analyse auto : `{settings.daily_run_time}` ({settings.timezone})\n"
                "Tapez /now pour une analyse immédiate."
            ),
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _shutdown(application: Application) -> None:
        scheduler.shutdown(wait=False)

    app.post_init = _post_init
    app.post_shutdown = _shutdown
    return app


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)
    app = build_application(settings)
    logger.info("Polling Telegram…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
