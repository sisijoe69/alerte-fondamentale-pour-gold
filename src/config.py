"""Configuration loader for the Gold bot."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "y", "on")


def _opt_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: int
    owner_user_id: int | None = None
    invite_code: str | None = None

    daily_run_time: str = "06:00"
    timezone: str = "Europe/Paris"

    alerts_enabled: bool = True
    alerts_check_time: str = "14:35"

    webhook_enabled: bool = False
    webhook_port: int = 8080
    webhook_secret: str | None = None

    fred_api_key: str | None = None
    truth_social_account_id: str = "107780257626128497"

    log_level: str = "INFO"

    data_dir: Path = field(default_factory=lambda: ROOT_DIR / "data")


def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id_raw = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN manquant dans .env")
    if not chat_id_raw:
        raise RuntimeError("TELEGRAM_CHAT_ID manquant dans .env")

    try:
        chat_id = int(chat_id_raw)
    except ValueError as exc:
        raise RuntimeError(f"TELEGRAM_CHAT_ID doit être un entier, reçu: {chat_id_raw!r}") from exc

    data_dir = ROOT_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        owner_user_id=_opt_int(os.getenv("OWNER_USER_ID")),
        invite_code=(os.getenv("INVITE_CODE") or "").strip() or None,
        daily_run_time=os.getenv("DAILY_RUN_TIME", "06:00").strip() or "06:00",
        timezone=os.getenv("TIMEZONE", "Europe/Paris").strip() or "Europe/Paris",
        alerts_enabled=_bool(os.getenv("ALERTS_ENABLED"), default=True),
        alerts_check_time=os.getenv("ALERTS_CHECK_TIME", "14:35").strip() or "14:35",
        webhook_enabled=_bool(os.getenv("WEBHOOK_ENABLED"), default=False),
        # Railway / Heroku expose the assigned port via $PORT; honor it first.
        webhook_port=int(os.getenv("PORT") or os.getenv("WEBHOOK_PORT") or "8080"),
        webhook_secret=(os.getenv("WEBHOOK_SECRET") or "").strip() or None,
        fred_api_key=(os.getenv("FRED_API_KEY") or "").strip() or None,
        truth_social_account_id=(
            os.getenv("TRUTH_SOCIAL_ACCOUNT_ID") or "107780257626128497"
        ).strip(),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        data_dir=data_dir,
    )


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
