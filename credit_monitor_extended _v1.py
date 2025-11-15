"""
credit_monitor_extended.py
--------------------------------
Monitor US credit-market indicators:
- TOTALSLAR: Total Consumer Credit Growth (monthly)
- BAMLH0A0HYM2: ICE BofA US High Yield OAS (daily)
- NFCI: Chicago Fed National Financial Conditions Index (weekly)

Sends Telegram alerts when:
  1. New data is released, or
  2. Any metric breaches configured thresholds.
"""

import os
import asyncio
from datetime import datetime, date
import pandas as pd
from pandas_datareader import data as web
from telegram import Bot
from dotenv import load_dotenv
import html

# ============================================================
# 1️⃣ Configuration
# ============================================================

class Config:
    def __init__(self):
        load_dotenv()
        self.TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
        self.CHAT_ID = os.getenv("CHAT_ID")
        if not self.TELEGRAM_TOKEN or not self.CHAT_ID:
            raise RuntimeError("Missing TELEGRAM_TOKEN or CHAT_ID in .env")

        # Data series
        self.FRED_SERIES = {
            "consumer_credit": "TOTALSLAR",
            "hy_spread": "BAMLH0A0HYM2",
            "nfci": "NFCI"
        }

        # Thresholds
        self.CREDIT_THRESHOLD = 0.10       # % growth
        self.HY_SPREAD_THRESHOLD = 400     # bps
        self.NFCI_THRESHOLD = 0.0          # positive = tightening

        # Data freshness window
        self.STALE_DAYS = 90
        self.START_DATE = "2010-01-01"

        # the series code and threshold
        self.FRED_SERIES = {
            "consumer_credit": "TOTALSLAR",
            "hy_spread": "BAMLH0A0HYM2",
            "nfci": "NFCI",
            "consumer_sentiment": "UMCSENT"
        }
        # Example threshold
        self.SENTIMENT_THRESHOLD = 60.0   # e.g., if sentiment drops below 60


# ============================================================
# 2️⃣ Data Fetchers
# ============================================================

class FredFetcher:
    """Unified FRED data fetcher."""
    def __init__(self, series_name: str):
        self.series_name = series_name

    def fetch(self, start: str, end: str | None = None) -> pd.DataFrame:
        if end is None:
            end = datetime.now().strftime("%Y-%m-%d")
        df = web.DataReader(self.series_name, "fred", start, end).dropna()
        return df


def fetch_consumer_credit(start='2000-01-01', end=None):
    df = FredFetcher("TOTALSLAR").fetch(start, end)
    df.columns = ['pct_change_consumer_credit']
    df["latest_date"] = df.index
    return df


def fetch_hy_spread(start='2000-01-01', end=None):
    df = FredFetcher("BAMLH0A0HYM2").fetch(start, end)
    df.columns = ['hy_oas']
    df["hy_oas_bps"] = df["hy_oas"] * 100
    df["latest_date"] = df.index
    return df


def fetch_nfci(start='2000-01-01', end=None):
    df = FredFetcher("NFCI").fetch(start, end)
    df.columns = ['nfci']
    df["latest_date"] = df.index
    return df

def fetch_sentiment(start='2000-01-01', end=None):
    df = FredFetcher("UMCSENT").fetch(start, end)
    df.columns = ['consumer_sentiment']
    df["latest_date"] = df.index
    return df

# ============================================================
# 3️⃣ Telegram Notifier
# ============================================================

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.bot = Bot(token=token)
        self.chat_id = chat_id

    async def send(self, message: str):
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        safe_message = html.escape(message)               # ✅ escape all <, >, &
        print(f"[{timestamp}] {message}")
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=safe_message,
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"⚠️ Telegram send error: {e}")

# ============================================================
# 4️⃣ Credit Monitor Logic
# ============================================================

class CreditMonitor:
    def __init__(self, config: Config):
        self.cfg = config
        self.notifier = TelegramNotifier(config.TELEGRAM_TOKEN, config.CHAT_ID)

    def _check_staleness(self, latest_date: date) -> bool:
        today = datetime.now().date()
        return (today - latest_date).days > self.cfg.STALE_DAYS

    def _compare_new_data(self, df: pd.DataFrame, cache_file: str) -> bool:
        """Return True if the latest data date is new compared to cache file."""
        latest_date = df.index.max().date()
        os.makedirs("cache", exist_ok=True)
        path = os.path.join("cache", cache_file)
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write(str(latest_date))
            return True
        with open(path, "r") as f:
            prev_date = f.read().strip()
        if prev_date != str(latest_date):
            with open(path, "w") as f:
                f.write(str(latest_date))
            return True
        return False

    async def run(self):
        """Fetch all indicators and send alerts as needed."""

        # ---------- Consumer Credit ----------
        cc = fetch_consumer_credit(self.cfg.START_DATE)
        cc_latest_date = cc.index.max().date()
        cc_latest_value = cc.iloc[-1]['pct_change_consumer_credit']
        cc_stale = self._check_staleness(cc_latest_date)
        cc_new = self._compare_new_data(cc, "consumer_credit.txt")

        if cc_new:
            await self.notifier.send(f"🆕 New Consumer Credit data ({cc_latest_date}): {cc_latest_value:.2f}%")
        if cc_stale:
            await self.notifier.send("⚠️ Consumer credit data is stale.")
        if cc_latest_value < self.cfg.CREDIT_THRESHOLD:
            await self.notifier.send(f"📉 Credit Warning: growth {cc_latest_value:.2f}% (<{self.cfg.CREDIT_THRESHOLD}%)")

        # ---------- High-Yield Spread ----------
        hy = fetch_hy_spread(self.cfg.START_DATE)
        hy_latest_date = hy.index.max().date()
        hy_latest_value = hy.iloc[-1]['hy_oas_bps']
        hy_new = self._compare_new_data(hy, "hy_spread.txt")

        if hy_new:
            await self.notifier.send(f"🆕 New HY Spread data ({hy_latest_date}): {hy_latest_value:.0f} bps")
        if hy_latest_value > self.cfg.HY_SPREAD_THRESHOLD:
            await self.notifier.send(f"🚨 HY Spread above {self.cfg.HY_SPREAD_THRESHOLD} bps: {hy_latest_value:.0f} bps")

        # ---------- Financial Conditions (NFCI) ----------
        nfci = fetch_nfci(self.cfg.START_DATE)
        nfci_latest_date = nfci.index.max().date()
        nfci_latest_value = nfci.iloc[-1]['nfci']
        nfci_new = self._compare_new_data(nfci, "nfci.txt")

        if nfci_new:
            await self.notifier.send(f"🆕 New NFCI data ({nfci_latest_date}): {nfci_latest_value:.2f}")
        if nfci_latest_value > self.cfg.NFCI_THRESHOLD:
            await self.notifier.send(f"📈 NFCI turned positive ({nfci_latest_value:.2f}) — tightening conditions.")

        # ---------- Consumer Sentiment ----------
        sent = fetch_sentiment(self.cfg.START_DATE)
        sent_latest_date = sent.index.max().date()
        sent_latest_value = sent.iloc[-1]['consumer_sentiment']
        sent_new = self._compare_new_data(sent, "consumer_sentiment.txt")

        if sent_new:
            await self.notifier.send(f"🆕 New Consumer Sentiment data ({sent_latest_date}): {sent_latest_value:.2f}")
        if sent_latest_value < self.cfg.SENTIMENT_THRESHOLD:
            await self.notifier.send(f"⚠️ Consumer Sentiment Warning: {sent_latest_value:.2f} (<{self.cfg.SENTIMENT_THRESHOLD})")

# ============================================================
# 5️⃣ Entry Point
# ============================================================

#if __name__ == "__main__":
#    cfg = Config()
#    monitor = CreditMonitor(cfg)
#    asyncio.run(monitor.run())
