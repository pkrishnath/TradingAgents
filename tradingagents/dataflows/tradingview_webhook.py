"""FastAPI webhook server for receiving TradingView OHLCV alerts.

Run standalone:
    python -m tradingagents.dataflows.tradingview_webhook
    # or via entry point:
    tradingagents-webhook
"""

import os
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel

from .tradingview_db import get_available_tickers, get_date_range, insert_bar

app = FastAPI(title="TradingView Webhook Receiver", version="0.1.0")


# ── Pydantic models ──────────────────────────────────────────────────────────

class OHLCVBar(BaseModel):
    """Standard OHLCV bar from a TradingView alert.

    TradingView alert message template:
        {"ticker":"{{ticker}}","time":"{{time}}","open":{{open}},
         "high":{{high}},"low":{{low}},"close":{{close}},"volume":{{volume}}}
    """
    ticker: str
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/webhook")
async def receive_bar(bar: OHLCVBar):
    """Receive a standard OHLCV bar from TradingView."""
    insert_bar(
        ticker=bar.ticker,
        timestamp=bar.time,
        open_=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
    )
    return {"status": "ok", "ticker": bar.ticker, "time": bar.time}


@app.post("/webhook/raw")
async def receive_raw(request: Request):
    """Flexible endpoint for non-standard payloads.

    Attempts to extract OHLCV fields from arbitrary JSON. Useful when
    TradingView alert field names differ from the standard template.
    """
    data = await request.json()

    # Try common field name variations
    ticker = data.get("ticker") or data.get("symbol") or data.get("pair")
    time_val = data.get("time") or data.get("timestamp") or data.get("date")
    open_val = data.get("open") or data.get("o")
    high_val = data.get("high") or data.get("h")
    low_val = data.get("low") or data.get("l")
    close_val = data.get("close") or data.get("c")
    volume_val = data.get("volume") or data.get("v") or 0

    if not all([ticker, time_val, open_val, high_val, low_val, close_val]):
        return {"status": "error", "message": "Missing required OHLCV fields"}

    insert_bar(
        ticker=str(ticker),
        timestamp=str(time_val),
        open_=float(open_val),
        high=float(high_val),
        low=float(low_val),
        close=float(close_val),
        volume=int(volume_val),
    )
    return {"status": "ok", "ticker": ticker, "time": time_val}


@app.get("/status")
async def status():
    """Show available tickers and their date ranges."""
    tickers = get_available_tickers()
    result = {}
    for t in tickers:
        info = get_date_range(t)
        if info:
            result[t] = info
    return {"tickers": result}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    port = int(os.environ.get("TRADINGVIEW_WEBHOOK_PORT", "8089"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
