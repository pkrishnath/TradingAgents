"""TradingView data vendor — reads OHLCV from SQLite, calculates indicators via stockstats."""

from typing import Annotated
from datetime import datetime
from dateutil.relativedelta import relativedelta

import pandas as pd
from stockstats import wrap

from .tradingview_db import query_ohlcv


class TradingViewDataNotAvailableError(Exception):
    """Raised when TradingView SQLite has no data for the requested ticker/range."""
    pass


def get_stock_data(
    symbol: Annotated[str, "ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Read OHLCV from SQLite and return CSV string matching yfinance format."""
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    df = query_ohlcv(symbol, start_date, end_date)

    if df.empty:
        raise TradingViewDataNotAvailableError(
            f"No TradingView data for '{symbol}' between {start_date} and {end_date}"
        )

    # Round numerical values to 2 decimal places
    for col in ["Open", "High", "Low", "Close"]:
        if col in df.columns:
            df[col] = df[col].round(2)

    csv_string = df.to_csv(index=False)

    header = f"# Stock data for {symbol} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(df)}\n"
    header += f"# Source: TradingView webhook\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


def get_indicators(
    symbol: Annotated[str, "ticker symbol"],
    indicator: Annotated[str, "technical indicator to calculate"],
    curr_date: Annotated[str, "current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    """Calculate technical indicators from TradingView OHLCV data via stockstats."""
    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)

    # Fetch extra 200 days for indicator warm-up (SMA-200, etc.)
    warmup_start = before - relativedelta(days=200)

    df = query_ohlcv(symbol, warmup_start.strftime("%Y-%m-%d"), curr_date)

    if df.empty:
        raise TradingViewDataNotAvailableError(
            f"No TradingView data for '{symbol}' to calculate {indicator}"
        )

    # stockstats expects lowercase column names
    ss_df = df.copy()
    ss_df.columns = [c.lower() for c in ss_df.columns]
    ss_df = wrap(ss_df)

    # Trigger indicator calculation
    ss_df[indicator]

    # Add formatted date column for lookups
    ss_df["date_str"] = pd.to_datetime(ss_df["date"]).dt.strftime("%Y-%m-%d")

    # Build date-to-value map
    indicator_map = {}
    for _, row in ss_df.iterrows():
        val = row[indicator]
        indicator_map[row["date_str"]] = "N/A" if pd.isna(val) else str(val)

    # Generate output for the lookback window
    ind_string = ""
    current_dt = curr_date_dt
    while current_dt >= before:
        date_str = current_dt.strftime("%Y-%m-%d")
        value = indicator_map.get(date_str, "N/A: Not a trading day (weekend or holiday)")
        ind_string += f"{date_str}: {value}\n"
        current_dt = current_dt - relativedelta(days=1)

    result_str = (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        + ind_string
        + f"\n\nSource: TradingView webhook data"
    )

    return result_str
