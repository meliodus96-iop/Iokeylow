#!/usr/bin/env python3
"""Download checksum-verified Binance Vision monthly klines or aggTrades.

Binance Vision's current dataset terms restrict these archives to non-commercial,
personal, non-production research/backtesting. This downloader requires an
explicit acknowledgement before making a request. Do not use these archives
as a production/live trading feed or redistribute them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://data.binance.vision/data"
KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trade_count",
    "taker_buy_base_volume", "taker_buy_quote_volume", "ignore",
]
SPOT_AGG_COLUMNS = [
    "aggregate_trade_id", "price", "quantity", "first_trade_id",
    "last_trade_id", "timestamp", "is_buyer_maker", "is_best_match",
]
FUTURES_AGG_COLUMNS = [
    "aggregate_trade_id", "price", "quantity", "first_trade_id",
    "last_trade_id", "timestamp", "is_buyer_maker",
]


def month_range(start: str, end_exclusive: str) -> Iterator[str]:
    start_date = datetime.strptime(start, "%Y-%m").date().replace(day=1)
    end_date = datetime.strptime(end_exclusive, "%Y-%m").date().replace(day=1)
    if end_date <= start_date:
        raise ValueError("--to-month must be later than --from-month (end exclusive)")
    current = start_date
    while current < end_date:
        yield current.strftime("%Y-%m")
        year = current.year + (current.month == 12)
        month = 1 if current.month == 12 else current.month + 1
        current = current.replace(year=year, month=month, day=1)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, destination: Path, retries: int = 3) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Iokeylow-Free-Market-Data-Research/1.0"},
    )
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as out:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    out.write(block)
            return
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 404:
                raise RuntimeError(f"Archive not found (404): {url}") from exc
            if exc.code not in (429, 500, 502, 503, 504) or attempt >= retries:
                raise
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                raise
        time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"Download failed: {url}: {last_error}")


def archive_url(market: str, kind: str, symbol: str, month: str, interval: str | None) -> str:
    product_path = {
        "spot": "spot",
        "futures_um": "futures/um",
        "futures_cm": "futures/cm",
    }[market]
    if kind == "klines":
        if not interval:
            raise ValueError("--interval is required when --kind=klines")
        filename = f"{symbol}-{interval}-{month}.zip"
        return f"{BASE_URL}/{product_path}/monthly/klines/{symbol}/{interval}/{filename}"
    if kind == "aggTrades":
        filename = f"{symbol}-aggTrades-{month}.zip"
        return f"{BASE_URL}/{product_path}/monthly/aggTrades/{symbol}/{filename}"
    raise ValueError(f"Unsupported kind: {kind}")


def to_utc(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    valid = values.dropna()
    if valid.empty:
        raise ValueError("Timestamp column is empty or non-numeric")
    unit = "us" if int(valid.max()) >= 100_000_000_000_000 else "ms"
    return pd.to_datetime(values, unit=unit, utc=True, errors="coerce")


def normalize_klines(raw: pd.DataFrame, symbol: str, market: str, month: str) -> pd.DataFrame:
    raw = raw.iloc[:, :len(KLINE_COLUMNS)].copy()
    if raw.shape[1] != len(KLINE_COLUMNS):
        raise ValueError(f"Expected 12 kline columns, received {raw.shape[1]}")
    raw.columns = KLINE_COLUMNS
    raw["ts_event"] = to_utc(raw["open_time"])
    raw["ts_close"] = to_utc(raw["close_time"])
    numeric = [
        "open", "high", "low", "close", "volume", "quote_volume",
        "trade_count", "taker_buy_base_volume", "taker_buy_quote_volume",
    ]
    for column in numeric:
        raw[column] = pd.to_numeric(raw[column], errors="coerce")
    raw = raw.dropna(subset=["ts_event", "open", "high", "low", "close"])
    raw["symbol"] = symbol
    raw["market"] = market
    raw["source"] = "Binance Vision"
    raw["source_kind"] = "exchange_ohlcv"
    return raw[
        ["ts_event", "ts_close", "symbol", "market", "source", "source_kind"]
        + numeric
    ].sort_values("ts_event").drop_duplicates(subset=["ts_event"])


def normalize_aggtrades(raw: pd.DataFrame, symbol: str, market: str, month: str) -> pd.DataFrame:
    columns = SPOT_AGG_COLUMNS if market == "spot" else FUTURES_AGG_COLUMNS
    raw = raw.iloc[:, :len(columns)].copy()
    if raw.shape[1] != len(columns):
        raise ValueError(f"Expected {len(columns)} aggTrades columns, received {raw.shape[1]}")
    raw.columns = columns
    raw["ts_event"] = to_utc(raw["timestamp"])
    for column in ("price", "quantity"):
        raw[column] = pd.to_numeric(raw[column], errors="coerce")
    maker = raw["is_buyer_maker"].astype(str).str.lower().map({"true": True, "false": False, "1": True, "0": False})
    raw["is_buyer_maker"] = maker
    # If buyer is maker, the incoming seller was the aggressor; otherwise buyer.
    raw["aggressor_side"] = maker.map({True: "SELL", False: "BUY"})
    raw["aggressor_side_provenance"] = "exchange_reported"
    raw = raw.dropna(subset=["ts_event", "price", "quantity", "is_buyer_maker"])
    raw["symbol"] = symbol
    raw["market"] = market
    raw["source"] = "Binance Vision"
    raw["source_kind"] = "aggregate_trades"
    keep = [
        "ts_event", "symbol", "market", "source", "source_kind",
        "aggregate_trade_id", "price", "quantity", "first_trade_id",
        "last_trade_id", "is_buyer_maker", "aggressor_side",
        "aggressor_side_provenance",
    ]
    if "is_best_match" in raw:
        keep.append("is_best_match")
    return raw[keep].sort_values("ts_event").drop_duplicates(subset=["aggregate_trade_id"])


def process_archive(zip_path: Path, kind: str, symbol: str, market: str, month: str) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise ValueError(f"Expected exactly one CSV in {zip_path.name}; found {csv_names}")
        with archive.open(csv_names[0]) as stream:
            raw = pd.read_csv(stream, header=None, low_memory=False)
    if kind == "klines":
        return normalize_klines(raw, symbol, market, month)
    return normalize_aggtrades(raw, symbol, market, month)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", choices=("spot", "futures_um", "futures_cm"), default="futures_um")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--kind", choices=("klines", "aggTrades"), default="klines")
    parser.add_argument("--interval", default="1m", help="Kline interval, ignored for aggTrades")
    parser.add_argument("--from-month", required=True, help="Inclusive YYYY-MM")
    parser.add_argument("--to-month", required=True, help="Exclusive YYYY-MM")
    parser.add_argument(
        "--accept-noncommercial-terms",
        action="store_true",
        help="Acknowledge Binance Vision's non-commercial, personal, non-production terms",
    )
    args = parser.parse_args()

    if not args.accept_noncommercial_terms:
        parser.error(
            "Binance Vision archives require --accept-noncommercial-terms. "
            "The current license does not permit live proprietary execution or commercial use."
        )
    if not re.fullmatch(r"[A-Z0-9]+", args.symbol.upper()):
        parser.error("--symbol must contain only uppercase letters and digits")

    symbol = args.symbol.upper()
    interval_part = args.interval if args.kind == "klines" else "all"
    root = ROOT / "data" / "raw" / "binance_vision" / args.market / args.kind / symbol / interval_part
    root.mkdir(parents=True, exist_ok=True)

    total_rows = 0
    for month in month_range(args.from_month, args.to_month):
        url = archive_url(args.market, args.kind, symbol, month, args.interval)
        zip_path = root / f"{symbol}-{args.kind}-{args.interval + '-' if args.kind == 'klines' else ''}{month}.zip"
        checksum_path = Path(str(zip_path) + ".CHECKSUM")
        try:
            download(url + ".CHECKSUM", checksum_path)
            checksum_tokens = checksum_path.read_text(encoding="utf-8").strip().split()
            if not checksum_tokens or not re.fullmatch(r"[a-fA-F0-9]{64}", checksum_tokens[0]):
                raise ValueError(f"Unrecognized checksum file format: {checksum_path}")
            download(url, zip_path)
            actual_hash = sha256_file(zip_path)
            if actual_hash.lower() != checksum_tokens[0].lower():
                zip_path.unlink(missing_ok=True)
                raise ValueError(f"SHA-256 mismatch for {zip_path.name}")

            frame = process_archive(zip_path, args.kind, symbol, args.market, month)
            parquet_path = zip_path.with_suffix(".parquet")
            frame.to_parquet(parquet_path, index=False)
            total_rows += len(frame)
            metadata = {
                "provider": "Binance Vision",
                "terms": "CC BY-NC-SA 4.0; personal non-commercial non-production research only",
                "market": args.market,
                "symbol": symbol,
                "kind": args.kind,
                "interval": args.interval if args.kind == "klines" else None,
                "month": month,
                "archive_url": url,
                "sha256": actual_hash,
                "rows": int(len(frame)),
                "parquet_path": str(parquet_path.relative_to(ROOT)),
                "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
                "aggressor_side_provenance": "exchange_reported" if args.kind == "aggTrades" else None,
            }
            Path(str(parquet_path) + ".metadata.json").write_text(
                json.dumps(metadata, indent=2), encoding="utf-8"
            )
            print(f"OK {month}: {len(frame):,} rows -> {parquet_path.relative_to(ROOT)}")
        except Exception as exc:
            print(f"ERROR {month}: {exc}", file=sys.stderr)
            return 1

    print(f"Complete: {total_rows:,} rows across requested months.")
    print("Reminder: this archive is not a live feed and is not licensed for commercial/live proprietary execution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
