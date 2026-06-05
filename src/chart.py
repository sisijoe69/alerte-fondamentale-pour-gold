"""Gold price chart generator — returns a PNG suitable for Telegram."""
from __future__ import annotations

import io
import logging
from datetime import datetime

import matplotlib

matplotlib.use("Agg")  # headless / no display
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import yfinance as yf  # noqa: E402

logger = logging.getLogger(__name__)


def build_gold_chart(days: int = 30) -> bytes | None:
    """Download Gold history and render a chart. Returns PNG bytes or None."""
    period = f"{max(days, 5)}d"
    try:
        data = None
        for ticker in ("GC=F", "XAUUSD=X"):
            try:
                t = yf.Ticker(ticker)
                data = t.history(period=period, interval="1d", auto_adjust=False)
                if data is not None and not data.empty:
                    break
            except Exception:  # noqa: BLE001
                continue
        if data is None or data.empty:
            logger.warning("Gold chart: no data returned by yfinance")
            return None

        fig, ax = plt.subplots(figsize=(10, 5))
        close = data["Close"]
        ax.plot(close.index, close.values, color="#d4a017", linewidth=2.0, label="XAU/USD")
        ax.fill_between(close.index, close.values, close.min(), alpha=0.18, color="#d4a017")

        if len(close) >= 7:
            ma7 = close.rolling(7).mean()
            ax.plot(ma7.index, ma7.values, color="#1f6feb", linewidth=1.2, linestyle="--", label="MA7")
        if len(close) >= 20:
            ma20 = close.rolling(20).mean()
            ax.plot(ma20.index, ma20.values, color="#a371f7", linewidth=1.2, linestyle="--", label="MA20")

        last_price = float(close.iloc[-1])
        first_price = float(close.iloc[0])
        change_pct = (last_price / first_price - 1) * 100 if first_price else 0

        ax.set_title(
            f"Gold (XAU/USD) — {days}j  |  Spot {last_price:.2f}  |  {change_pct:+.2f}%",
            fontsize=13, fontweight="bold",
        )
        ax.set_ylabel("USD / oz")
        ax.grid(True, alpha=0.25, linestyle=":")
        ax.legend(loc="upper left", fontsize=9)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d-%b"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
        fig.autofmt_xdate(rotation=20, ha="right")

        fig.text(
            0.99, 0.02,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            ha="right", va="bottom", fontsize=7, color="#888",
        )
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        logger.error("Gold chart generation failed: %s", exc)
        return None
