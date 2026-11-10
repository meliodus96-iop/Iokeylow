#!/usr/bin/env python3
"""Download public crypto candles or take a current public market snapshot.

No exchange account, API key, or trading permission is used. Exchange rate
limits and historical-retention policies still apply.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ccxt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "raw" / "crypto"


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def make_exchange(exchange_id: str):
    if exchange_id not in ccxt.exchanges:
        raise ValueError(f"Unknown CCXT exchange id: {exchange_id}")
    exchange_class = getattr(ccxt, exchange_id, None)
    if exchange_class is None:
        raise ValueError(f"CCXT exchange class is unavailable: {exchange_id}")
    exchange = exchange_class({"enableRateLimit": True, "timeout": 30000})
    exchange.load_markets()
    return exchange


def fetch_ohlcv(exchange: Any, symbol: str, timeframe: str, since_ms: int, until_ms: int, limit: int):
    if not exchange.has.get("fetchOHLCV"):
        raise RuntimeError(f"{exchange.id} does not expose fetchOHLCV")
    timeframe_ms = int(exchange.parse_timeframe(timeframe) * 1000)
    if timeframe_ms <= 0:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    rows_by_time: dict[int, list] = {}
    cursor = since_ms
    pages = 0
    while cursor < until_ms:
        page = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=limit)
        pages += 1
        if not page:
            break

        valid = []
        for row in page:
            ts = int(row[0])
            if since_ms <= ts < until_ms and ts not in rows_by_time:
                rows_by_time[ts] = row
                valid.append(ts)

        if not valid:
            break
        next_cursor = max(valid) + timeframe_ms
        if next_cursor <= cursor:
            raise RuntimeError("Pagination made no forward progress; refusing duplicate/infinite fetch")
        cursor = next_cursor

        # A short page is normally the end of the available range.
        if len(page) < limit and cursor >= until_ms:
            break

    if not rows_by_time:
        raise RuntimeError("No candles returned. Check the symbol, exchange and requested dates.")

    ordered = [rows_by_time[key] for key in sorted(rows_by_time)]
    frame = pd.DataFrame(
        ordered,
        columns=["timestamp_ms", "open", "high", "low", "close", "volume"],
    )
    frame["ts_event"] = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True)
    frame["exchange"] = exchange.id
    frame["symbol"] = symbol
    frame["timeframe"] = timeframe
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    duplicates = int(frame["timestamp_ms"].duplicated().sum())
    frame = frame.drop_duplicates(subset=["timestamp_ms"]).sort_values("timestamp_ms")
    all_steps = pd.Series(frame["timestamp_ms"].diff().dropna())
    internal_gaps = int((all_steps > timeframe_ms).sum())
    return frame, {
        "pages_requested": pages,
        "rows": int(len(frame)),
        "duplicate_timestamps_removed": duplicates,
        "internal_gap_count": internal_gaps,
        "first_timestamp_utc": frame["ts_event"].iloc[0].isoformat(),
        "last_timestamp_utc": frame["ts_event"].iloc[-1].isoformat(),
        "requested_start_utc": datetime.fromtimestamp(since_ms / 1000, timezone.utc).isoformat(),
        "requested_end_exclusive_utc": datetime.fromtimestamp(until_ms / 1000, timezone.utc).isoformat(),
        "timeframe_ms": timeframe_ms,
    }


def output_dir(exchange_id: str, symbol: str) -> Path:
    path = DEFAULT_OUT / safe_name(exchange_id) / safe_name(symbol)
    path.mkdir(parents=True, exist_ok=True)
    return path


def run(args: argparse.Namespace) -> int:
    exchange = make_exchange(args.exchange)
    try:
        if args.kind == "ohlcv":
            if not args.since or not args.until:
                raise ValueError("--since and --until are required for OHLCV (end is exclusive)")
            since_dt, until_dt = parse_utc(args.since), parse_utc(args.until)
            if until_dt <= since_dt:
                raise ValueError("--until must be later than --since")
            since_ms = int(since_dt.timestamp() * 1000)
            until_ms = int(until_dt.timestamp() * 1000)
            frame, quality = fetch_ohlcv(
                exchange, args.symbol, args.timeframe, since_ms, until_ms, args.limit
            )
            target = output_dir(exchange.id, args.symbol)
            stem = f"{args.timeframe}_{since_dt:%Y%m%d}_{until_dt:%Y%m%d}"
            data_path = target / f"{stem}.parquet"
            frame.to_parquet(data_path, index=False)
            metadata = {
                "provider": "CCXT public exchange API",
                "exchange": exchange.id,
                "symbol": args.symbol,
                "kind": "OHLCV",
                "timeframe": args.timeframe,
                "data_path": str(data_path.relative_to(ROOT)),
                "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                "credentials_used": False,
                "quality": quality,
                "limitations": [
                    "Exchange retention and pagination limits apply.",
                    "An exchange candle is not an exchange-wide consolidated price.",
                    "No synthetic candles were inserted for missing intervals.",
                ],
            }
            (target / f"{stem}.metadata.json").write_text(
                json.dumps(metadata, indent=2), encoding="utf-8"
            )
            print(json.dumps(metadata, indent=2))
            return 0

        if args.kind == "orderbook":
            if not exchange.has.get("fetchOrderBook"):
                raise RuntimeError(f"{exchange.id} does not expose fetchOrderBook")
            book = exchange.fetch_order_book(args.symbol, limit=args.limit)
            target = output_dir(exchange.id, args.symbol)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            payload = {
                "provider": "CCXT public exchange API",
                "exchange": exchange.id,
                "symbol": args.symbol,
                "kind": "current_orderbook_snapshot",
                "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                "credentials_used": False,
                "timestamp": book.get("timestamp"),
                "datetime": book.get("datetime"),
                "nonce": book.get("nonce"),
                "bids": book.get("bids", []),
                "asks": book.get("asks", []),
                "limitations": [
                    "This is a single current snapshot, not historical depth.",
                    "It is not L3/MBO unless the venue explicitly documents order-level IDs.",
                    "Do not join snapshots into a historical book without sequence-valid deltas.",
                ],
            }
            data_path = target / f"orderbook_{stamp}.json"
            data_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"Saved current order-book snapshot: {data_path}")
            return 0

        if args.kind == "trades":
            trades = exchange.fetch_trades(args.symbol, limit=args.limit)
            if not trades:
                raise RuntimeError("No public trades returned")
            target = output_dir(exchange.id, args.symbol)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            frame = pd.DataFrame(trades)
            data_path = target / f"recent_trades_{stamp}.parquet"
            frame.to_parquet(data_path, index=False)
            print(f"Saved {len(frame)} recent public trades: {data_path}")
            print("NOTE: this is the exchange's recent-trades page, not complete deep history.")
            return 0

        raise ValueError(f"Unsupported kind: {args.kind}")
    finally:
        close = getattr(exchange, "close", None)
        if callable(close):
            close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exchange", default="binanceusdm", help="CCXT exchange id; e.g. binanceusdm, binance, bybit, okx, hyperliquid")
    parser.add_argument("--symbol", default="BTC/USDT:USDT", help="CCXT unified symbol; check the venue's markets")
    parser.add_argument("--kind", choices=("ohlcv", "orderbook", "trades"), default="ohlcv")
    parser.add_argument("--timeframe", default="1m", help="Exchange-supported candle timeframe")
    parser.add_argument("--since", help="UTC start, e.g. 2024-01-01 (OHLCV only)")
    parser.add_argument("--until", help="UTC end, exclusive, e.g. 2025-01-01 (OHLCV only)")
    parser.add_argument("--limit", type=int, default=1000, help="Page size for OHLCV or depth/trade snapshot")
    return parser


if __name__ == "__main__":
    try:
        raise SystemExit(run(build_parser().parse_args()))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
