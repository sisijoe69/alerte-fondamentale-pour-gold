"""Telegram bot entrypoint.

Features:
- Daily scheduled analysis at the configured time, broadcast to all subscribers
- /now command for on-demand analysis
- Multi-user: /subscribe (optional invite code), /unsubscribe
- /history [N] for recent reports
- Admin commands: /users, /kick <user_id>
- Intra-day macro release watchdog (CPI / NFP / PCE / PPI)
- Optional TradingView webhook server (port WEBHOOK_PORT)
- Gold price chart attached to every report
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Iterable
from zoneinfo import ZoneInfo

from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import Forbidden, TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes

from .alerts import check_releases, format_alert_message
from .analysis import run_analysis
from .chart import build_gold_chart
from .config import Settings, load_settings, setup_logging
from .db import Database
from .webhook import build_webhook_app

logger = logging.getLogger(__name__)

_LAST_RUN: dict = {"at": None, "bias": None, "conviction": None}


# ── Helpers ───────────────────────────────────────────────────────

def _is_admin(user_id: int, db: Database, settings: Settings) -> bool:
    if settings.owner_user_id and user_id == settings.owner_user_id:
        return True
    sub = db.get_subscriber(user_id)
    return bool(sub and sub.is_admin)


async def _send_long(bot, chat_id: int, text: str) -> None:
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


async def _broadcast(
    application: Application,
    chat_ids: Iterable[int],
    text: str,
    photo: bytes | None = None,
    photo_caption: str | None = None,
) -> int:
    """Send text (and optional photo) to a list of chat_ids. Returns count delivered."""
    db: Database = application.bot_data["db"]
    delivered = 0
    for chat_id in chat_ids:
        try:
            if photo is not None:
                from io import BytesIO
                await application.bot.send_photo(
                    chat_id=chat_id,
                    photo=BytesIO(photo),
                    caption=(photo_caption or "")[:1024],
                    parse_mode=ParseMode.MARKDOWN,
                )
            await _send_long(application.bot, chat_id, text)
            delivered += 1
        except Forbidden:
            logger.warning("User %s blocked the bot — removing subscription", chat_id)
            try:
                db.remove_subscriber(chat_id)  # chat_id == user_id in DM
            except Exception:  # noqa: BLE001
                pass
        except TelegramError as exc:
            logger.warning("Telegram error sending to %s: %s", chat_id, exc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error sending to %s: %s", chat_id, exc)
    return delivered


# ── Command handlers ──────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    db: Database = context.application.bot_data["db"]
    user = update.effective_user
    if user and settings.owner_user_id and user.id == settings.owner_user_id:
        db.upsert_subscriber(
            user_id=user.id,
            chat_id=update.effective_chat.id,
            username=user.username,
            first_name=user.first_name,
            is_admin=True,
        )
    welcome = (
        "🥇 *Gold Fundamental Bot*\n\n"
        "Commandes :\n"
        "• /subscribe `[code]` — recevoir les rapports quotidiens\n"
        "• /unsubscribe — se désinscrire\n"
        "• /now ou /analyse — analyse immédiate\n"
        "• /history `[N]` — derniers rapports (défaut 5)\n"
        "• /status — état du planning\n"
        "• /id — votre chat ID / user ID\n"
        "• /alerts on|off — activer/désactiver les alertes macro intra-day\n"
    )
    if settings.invite_code:
        welcome += (
            f"\n_Une invitation est requise. Demandez le code au propriétaire du bot._"
        )
    await update.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id if update.effective_chat else "?"
    user_id = update.effective_user.id if update.effective_user else "?"
    await update.message.reply_text(
        f"Chat ID : `{chat_id}`\nUser ID : `{user_id}`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    db: Database = context.application.bot_data["db"]
    user = update.effective_user
    if not user:
        return
    args = context.args or []
    if settings.invite_code:
        provided = args[0] if args else ""
        if provided != settings.invite_code:
            await update.message.reply_text(
                "🔒 Code d'invitation requis : `/subscribe MONCODE`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
    created = db.upsert_subscriber(
        user_id=user.id,
        chat_id=update.effective_chat.id,
        username=user.username,
        first_name=user.first_name,
        is_admin=(settings.owner_user_id == user.id),
    )
    if created:
        await update.message.reply_text(
            "✅ Inscription confirmée. Vous recevrez le rapport quotidien et les alertes macro.\n"
            "Tapez /alerts off pour désactiver les flashs intra-day."
        )
        try:
            await context.bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=f"👤 Nouveau subscriber : @{user.username or user.first_name} (`{user.id}`)",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:  # noqa: BLE001
            pass
    else:
        await update.message.reply_text("ℹ️ Vous étiez déjà inscrit. Préférences mises à jour.")


async def cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    user = update.effective_user
    if not user:
        return
    if db.remove_subscriber(user.id):
        await update.message.reply_text("👋 Désinscrit. Tapez /subscribe pour revenir.")
    else:
        await update.message.reply_text("Vous n'étiez pas inscrit.")


async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    user = update.effective_user
    if not user:
        return
    sub = db.get_subscriber(user.id)
    if not sub:
        await update.message.reply_text("Inscrivez-vous d'abord avec /subscribe.")
        return
    arg = (context.args[0].lower() if context.args else "")
    if arg in ("on", "true", "1"):
        db.set_pref(user.id, alerts=True)
        await update.message.reply_text("🔔 Alertes macro intra-day : *ON*", parse_mode=ParseMode.MARKDOWN)
    elif arg in ("off", "false", "0"):
        db.set_pref(user.id, alerts=False)
        await update.message.reply_text("🔕 Alertes macro intra-day : *OFF*", parse_mode=ParseMode.MARKDOWN)
    else:
        state = "ON" if sub.receives_alerts else "OFF"
        await update.message.reply_text(
            f"Alertes : *{state}*. Utilisez `/alerts on` ou `/alerts off`.",
            parse_mode=ParseMode.MARKDOWN,
        )


async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    db: Database = context.application.bot_data["db"]
    user = update.effective_user
    if not user or not _is_admin(user.id, db, settings):
        await update.message.reply_text("⛔ Admin uniquement.")
        return
    subs = db.list_subscribers()
    if not subs:
        await update.message.reply_text("Aucun subscriber.")
        return
    lines = [f"👥 *Subscribers ({len(subs)})*"]
    for s in subs:
        flags = []
        if s.is_admin:
            flags.append("ADMIN")
        if not s.receives_daily:
            flags.append("no-daily")
        if not s.receives_alerts:
            flags.append("no-alerts")
        suffix = f" [{', '.join(flags)}]" if flags else ""
        name = s.username or s.first_name or "?"
        lines.append(f"• `{s.user_id}` — {name}{suffix}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    db: Database = context.application.bot_data["db"]
    user = update.effective_user
    if not user or not _is_admin(user.id, db, settings):
        await update.message.reply_text("⛔ Admin uniquement.")
        return
    if not context.args:
        await update.message.reply_text("Usage : /kick <user_id>")
        return
    try:
        target = int(context.args[0])
    except ValueError:
        await update.message.reply_text("user_id doit être un entier.")
        return
    if target == settings.owner_user_id:
        await update.message.reply_text("Impossible de retirer le owner.")
        return
    if db.remove_subscriber(target):
        await update.message.reply_text(f"✅ Utilisateur `{target}` retiré.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("Pas trouvé.")


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    n = 5
    if context.args:
        try:
            n = max(1, min(20, int(context.args[0])))
        except ValueError:
            pass
    reports = db.last_reports(limit=n)
    if not reports:
        await update.message.reply_text("📭 Aucun rapport enregistré pour l'instant.")
        return
    lines = [f"📚 *{len(reports)} derniers rapports*", ""]
    for r in reports:
        when = r.created_at.replace("T", " ")
        price = f"{r.gold_price:.2f}" if r.gold_price else "n/a"
        lines.append(
            f"• `{when}` — {r.bias} ({r.conviction})  "
            f"📊 bull {r.bull_count}/bear {r.bear_count}  💰 {price}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    scheduler: AsyncIOScheduler = context.application.bot_data["scheduler"]
    db: Database = context.application.bot_data["db"]
    daily_job = scheduler.get_job("daily_gold_analysis")
    alerts_job = scheduler.get_job("macro_release_watchdog")
    last_at = _LAST_RUN.get("at")
    subs = db.list_subscribers()
    lines = [
        "📊 *Statut du bot Gold*",
        f"• Subscribers : {len(subs)}",
        f"• Dernière analyse : {last_at.strftime('%Y-%m-%d %H:%M %Z') if isinstance(last_at, datetime) else 'jamais'}",
        f"• Daily run : {daily_job.next_run_time.strftime('%Y-%m-%d %H:%M %Z') if daily_job and daily_job.next_run_time else 'inactif'}",
        f"• Alerts watchdog : {alerts_job.next_run_time.strftime('%Y-%m-%d %H:%M %Z') if alerts_job and alerts_job.next_run_time else 'désactivé'}",
        f"• Webhook TV : {'ON port '+str(settings.webhook_port) if settings.webhook_enabled else 'OFF'}",
        f"• Timezone : {settings.timezone}",
    ]
    if _LAST_RUN.get("bias"):
        lines.append(f"• Dernier biais : {_LAST_RUN['bias']} ({_LAST_RUN['conviction']})")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    db: Database = context.application.bot_data["db"]
    user = update.effective_user
    if not user:
        return
    sub = db.get_subscriber(user.id)
    is_owner = settings.owner_user_id == user.id
    if not sub and not is_owner:
        await update.message.reply_text(
            "🔒 Inscrivez-vous avec /subscribe avant d'utiliser /now."
        )
        return
    await update.message.reply_text("⏳ Analyse en cours… (15-30 sec)")
    try:
        result = await asyncio.to_thread(run_analysis, settings)
        _LAST_RUN["at"] = datetime.now(ZoneInfo(settings.timezone))
        _LAST_RUN["bias"] = result.score.bias_label()
        _LAST_RUN["conviction"] = result.score.conviction_label()[0]

        gold_price = result.raw.get("markets", {}).get("gold_price")
        db.save_report(
            bias=result.score.bias_label(),
            conviction=result.score.conviction_label()[0],
            bull_count=result.score.bull_count,
            bear_count=result.score.bear_count,
            gold_price=gold_price,
            summary=_short_summary(result.report_markdown),
            raw=result.raw,
        )

        chart_bytes = await asyncio.to_thread(build_gold_chart, 30)
        if chart_bytes:
            from io import BytesIO
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=BytesIO(chart_bytes),
                caption="📈 Gold spot — 30 jours",
            )
        await _send_long(context.bot, update.effective_chat.id, result.report_markdown)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Manual analysis failed")
        await update.message.reply_text(
            f"❌ Erreur pendant l'analyse : `{exc}`", parse_mode=ParseMode.MARKDOWN
        )


# ── Scheduled jobs ────────────────────────────────────────────────

async def scheduled_daily(application: Application) -> None:
    settings: Settings = application.bot_data["settings"]
    db: Database = application.bot_data["db"]
    logger.info("Daily scheduled analysis triggered")
    try:
        result = await asyncio.to_thread(run_analysis, settings)
        _LAST_RUN["at"] = datetime.now(ZoneInfo(settings.timezone))
        _LAST_RUN["bias"] = result.score.bias_label()
        _LAST_RUN["conviction"] = result.score.conviction_label()[0]

        gold_price = result.raw.get("markets", {}).get("gold_price")
        db.save_report(
            bias=result.score.bias_label(),
            conviction=result.score.conviction_label()[0],
            bull_count=result.score.bull_count,
            bear_count=result.score.bear_count,
            gold_price=gold_price,
            summary=_short_summary(result.report_markdown),
            raw=result.raw,
        )

        chart_bytes = await asyncio.to_thread(build_gold_chart, 30)

        chat_ids = [s.chat_id for s in db.list_subscribers(only_daily=True)]
        if not chat_ids:
            chat_ids = [settings.telegram_chat_id]

        delivered = await _broadcast(
            application,
            chat_ids,
            result.report_markdown,
            photo=chart_bytes,
            photo_caption="📈 Gold spot — 30 jours",
        )
        logger.info("Daily report delivered to %d/%d chats", delivered, len(chat_ids))
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


async def scheduled_alerts(application: Application) -> None:
    settings: Settings = application.bot_data["settings"]
    db: Database = application.bot_data["db"]
    logger.info("Macro release watchdog tick")
    try:
        events = await asyncio.to_thread(check_releases, settings.fred_api_key, db)
        if not events:
            return
        message = format_alert_message(events)
        for ev in events:
            db.log_alert("macro_release", {
                "series_id": ev.series_id, "date": ev.observation_date,
                "value": ev.value, "prior": ev.prior_value, "surprise": ev.surprise,
            })
        chat_ids = [s.chat_id for s in db.list_subscribers(only_alerts=True)]
        if not chat_ids:
            chat_ids = [settings.telegram_chat_id]
        delivered = await _broadcast(application, chat_ids, message)
        logger.info("Macro alert delivered to %d/%d chats (%d events)", delivered, len(chat_ids), len(events))
    except Exception:  # noqa: BLE001
        logger.exception("Macro watchdog failed")


def _short_summary(report_md: str) -> str:
    """Extract a one-line summary from the rendered report."""
    for line in report_md.splitlines():
        if "BIAIS" in line and ":" in line:
            return line.strip()
    return report_md[:200]


# ── Bootstrap ────────────────────────────────────────────────────

def _parse_hhmm(value: str) -> tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"DAILY_RUN_TIME must be HH:MM, got {value!r}")
    return int(parts[0]), int(parts[1])


def build_application(settings: Settings) -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()
    db = Database(settings.data_dir / "gold_bot.db")

    if settings.owner_user_id:
        db.upsert_subscriber(
            user_id=settings.owner_user_id,
            chat_id=settings.telegram_chat_id,
            username=None,
            first_name="Owner",
            is_admin=True,
        )

    app.bot_data["settings"] = settings
    app.bot_data["db"] = db

    handlers = [
        ("start", cmd_start),
        ("help", cmd_help),
        ("id", cmd_id),
        ("subscribe", cmd_subscribe),
        ("unsubscribe", cmd_unsubscribe),
        ("alerts", cmd_alerts),
        ("users", cmd_users),
        ("kick", cmd_kick),
        ("history", cmd_history),
        ("status", cmd_status),
        ("now", cmd_now),
        ("analyse", cmd_now),
    ]
    for name, fn in handlers:
        app.add_handler(CommandHandler(name, fn))

    tz = ZoneInfo(settings.timezone)
    scheduler = AsyncIOScheduler(timezone=tz)
    h, m = _parse_hhmm(settings.daily_run_time)
    scheduler.add_job(
        scheduled_daily,
        trigger=CronTrigger(hour=h, minute=m, timezone=tz),
        args=[app],
        id="daily_gold_analysis",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    if settings.alerts_enabled:
        ah, am = _parse_hhmm(settings.alerts_check_time)
        scheduler.add_job(
            scheduled_alerts,
            trigger=CronTrigger(day_of_week="mon-fri", hour=ah, minute=am, timezone=tz),
            args=[app],
            id="macro_release_watchdog",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    app.bot_data["scheduler"] = scheduler

    webhook_runner: dict = {"runner": None, "site": None}

    async def _post_init(application: Application) -> None:
        scheduler.start()
        next_run = scheduler.get_job("daily_gold_analysis").next_run_time
        logger.info("Scheduler started — next daily run at %s", next_run)

        if settings.webhook_enabled:
            await _start_webhook(application, settings, db, webhook_runner)

        try:
            await application.bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=(
                    "✅ *Gold Fundamental Bot en ligne*\n"
                    f"Daily auto : `{settings.daily_run_time}` ({settings.timezone})\n"
                    f"Alertes intra-day : `{'ON' if settings.alerts_enabled else 'OFF'}`\n"
                    f"Webhook TradingView : `{'ON port '+str(settings.webhook_port) if settings.webhook_enabled else 'OFF'}`\n"
                    "Tapez /now pour une analyse immédiate."
                ),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to send startup notice", exc_info=True)

    async def _shutdown(application: Application) -> None:
        scheduler.shutdown(wait=False)
        runner = webhook_runner.get("runner")
        if runner is not None:
            await runner.cleanup()

    app.post_init = _post_init
    app.post_shutdown = _shutdown
    return app


async def _start_webhook(
    application: Application,
    settings: Settings,
    db: Database,
    holder: dict,
) -> None:
    async def broadcast(text: str) -> None:
        chat_ids = [s.chat_id for s in db.list_subscribers(only_alerts=True)]
        if not chat_ids:
            chat_ids = [settings.telegram_chat_id]
        await _broadcast(application, chat_ids, text)

    webapp = build_webhook_app(settings, db, broadcast)
    runner = web.AppRunner(webapp)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=settings.webhook_port)
    await site.start()
    holder["runner"] = runner
    holder["site"] = site
    logger.info("TradingView webhook listening on 0.0.0.0:%d", settings.webhook_port)


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)
    app = build_application(settings)
    logger.info("Polling Telegram…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
