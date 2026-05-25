"""Configuration loader for the Gold bot."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _parse_csv_ids(raw: str | None) -> list[int]:
    if not raw:
        return []
    out: list[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(int(chunk))
        except ValueError:
            logging.warning("Ignoring non-integer ID in TELEGRAM_ALLOWED_USERS: %r", chunk)
    return out


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: int
    telegram_allowed_users: list[int] = field(default_factory=list)

    daily_run_time: str = "06:00"
    timezone: str = "Europe/Paris"

    fred_api_key: str | None = None
    x_bearer_token: str | None = None

    log_level: str = "INFO"

    @property
    def authorized_user_ids(self) -> set[int]:
        ids = set(self.telegram_allowed_users)
        ids.add(self.telegram_chat_id)
        return ids


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

    return Settings(
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        telegram_allowed_users=_parse_csv_ids(os.getenv("TELEGRAM_ALLOWED_USERS")),
        daily_run_time=os.getenv("DAILY_RUN_TIME", "06:00").strip() or "06:00",
        timezone=os.getenv("TIMEZONE", "Europe/Paris").strip() or "Europe/Paris",
        fred_api_key=(os.getenv("FRED_API_KEY") or "").strip() or None,
        x_bearer_token=(os.getenv("X_BEARER_TOKEN") or "").strip() or None,
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
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
