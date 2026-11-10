from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CSV_FIELDS = [
    "timestamp", "timestamp_ms", "open", "high", "low", "close",
    "volume", "vwap", "transactions",
]


def _field(row: Any, *names: str) -> Any:
    """Read a field from either an SDK model object or a dict response."""
    for name in names:
        if isinstance(row, dict) and name in row:
            return row[name]
        if hasattr(row, name):
            value = getattr(row, name)
            if value is not None:
                return value
    return None


def normalize_aggregate(row: Any) -> dict[str, Any]:
    """Normalize a Massive aggregate to an explicit UTC OHLCV record."""
    timestamp_ms = _field(row, "timestamp", "t")
    if timestamp_ms is None:
        raise ValueError("Aggregate is missing its millisecond timestamp")
    timestamp_ms = int(timestamp_ms)

    values = {
        "open": _field(row, "open", "o"),
        "high": _field(row, "high", "h"),
        "low": _field(row, "low", "l"),
        "close": _field(row, "close", "c"),
    }
    if any(value is None for value in values.values()):
        raise ValueError("Aggregate is missing one or more OHLC values")

    values = {key: float(value) for key, value in values.items()}
    if not all(math.isfinite(value) for value in values.values()):
        raise ValueError("Aggregate contains a non-finite OHLC value")
    if values["high"] < max(values["open"], values["close"], values["low"]):
        raise ValueError("Aggregate high is inconsistent with OHLC values")
    if values["low"] > min(values["open"], values["close"], values["high"]):
        raise ValueError("Aggregate low is inconsistent with OHLC values")

    volume = _field(row, "volume", "v")
    vwap = _field(row, "vwap", "vw")
    transactions = _field(row, "transactions", "n")

    return {
        "timestamp": datetime.fromtimestamp(
            timestamp_ms / 1000, tz=timezone.utc
        ).isoformat(),
        "timestamp_ms": timestamp_ms,
        **values,
        "volume": "" if volume is None else float(volume),
        "vwap": "" if vwap is None else float(vwap),
        "transactions": "" if transactions is None else int(transactions),
    }


def normalize_aggregates(rows: Iterable[Any]) -> list[dict[str, Any]]:
    records = [normalize_aggregate(row) for row in rows]
    records.sort(key=lambda item: item["timestamp_ms"])
    if not records:
        raise ValueError(
            "Massive returned zero aggregate bars. Check ticker, dates, "
            "subscription entitlements, and market coverage."
        )
    timestamps = [item["timestamp_ms"] for item in records]
    if len(timestamps) != len(set(timestamps)):
        raise ValueError("Duplicate candle timestamps detected")
    return records


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(args: argparse.Namespace) -> dict[str, Any]:
    api_key = os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "MASSIVE_API_KEY is not set. Add it as an environment variable "
            "or GitHub Actions secret; never commit the key."
        )

    try:
        from massive import RESTClient
    except ImportError as exc:
        raise RuntimeError(
            "The official Massive SDK is not installed. Install "
            "'massive==2.9.1' in the research environment."
        ) from exc

    client = RESTClient(api_key=api_key)
    # The official SDK handles API authentication and pagination.
    rows = client.list_aggs(
        ticker=args.ticker,
        multiplier=args.multiplier,
        timespan=args.timespan,
        from_=args.from_date,
        to=args.to_date,
        adjusted=args.adjusted,
        sort="asc",
        limit=args.limit,
    )
    records = normalize_aggregates(rows)

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(records)

    manifest = {
        "source": "Massive.com",
        "ticker": args.ticker,
        "multiplier": args.multiplier,
        "timespan": args.timespan,
        "from": args.from_date,
        "to": args.to_date,
        "adjusted": args.adjusted,
        "bars": len(records),
        "first_timestamp_utc": records[0]["timestamp"],
        "last_timestamp_utc": records[-1]["timestamp"],
        "timestamp_unit": "milliseconds converted to ISO-8601 UTC",
        "granularity": "aggregate_bar",
        "data_sha256": sha256_file(output),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "limitations": [
            "Bar data is not tick, quote, or full order-book data.",
            "Availability, history, delay, and permissions depend on the Massive subscription and ticker.",
            "Do not treat provider aggregates as broker-executable bid/ask prices without validation.",
        ],
    }
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"data_path": str(output), "manifest_path": str(manifest_path), **manifest}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download historical aggregate candles from Massive.com."
    )
    parser.add_argument("--ticker", required=True, help="Massive ticker, e.g. AAPL, C:EURUSD, X:BTCUSD")
    parser.add_argument("--multiplier", required=True, type=int)
    parser.add_argument(
        "--timespan",
        required=True,
        choices=("minute", "hour", "day", "week", "month", "quarter", "year"),
    )
    parser.add_argument("--from-date", required=True, dest="from_date")
    parser.add_argument("--to-date", required=True, dest="to_date")
    parser.add_argument("--output", default="prop_firm_lab/data/input/massive_bars.csv")
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument(
        "--adjusted",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Corporate-action adjustment flag (principally relevant to equities).",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = fetch(args)
    except Exception as exc:
        print(f"Market-data fetch failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
