#!/usr/bin/env python3
"""Capture public Hyperliquid trades, L2 snapshots and candles to raw JSONL.

This is a forward collector: it starts recording when launched. It does not
download complete past order-book history, infer missing events, or create an
L3 order-by-order book. Public market-data subscriptions require no API key.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import websockets

ROOT = Path(__file__).resolve().parents[1]
WS_URL = "wss://api.hyperliquid.xyz/ws"
VALID_CHANNELS = {"trades", "l2Book", "candle"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def day_key(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


class JsonlArchive:
    def __init__(self, base_dir: Path, flush_every: int = 1) -> None:
        self.base_dir = base_dir
        self.flush_every = max(1, flush_every)
        self._files: dict[tuple[str, str], Any] = {}
        self._counts: dict[tuple[str, str], int] = {}

    def write(self, coin: str, channel: str, record: dict[str, Any]) -> None:
        now = utc_now()
        key = (day_key(now), channel)
        stream = self._files.get(key)
        if stream is None:
            folder = self.base_dir / coin
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{key[0]}_{channel}.jsonl"
            stream = path.open("a", encoding="utf-8", buffering=1)
            self._files[key] = stream
            self._counts[key] = 0

        stream.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n")
        self._counts[key] += 1
        if self._counts[key] % self.flush_every == 0:
            stream.flush()

    def close(self) -> None:
        for stream in self._files.values():
            try:
                stream.flush()
                stream.close()
            except Exception:
                pass
        self._files.clear()


async def collect(args: argparse.Namespace) -> int:
    base_dir = Path(args.output)
    if not base_dir.is_absolute():
        base_dir = ROOT / base_dir
    archive = JsonlArchive(base_dir, args.flush_every)

    coins = [coin.upper() for coin in args.coins]
    channels = [name for name in args.channels.split(",") if name]
    unknown = set(channels) - VALID_CHANNELS
    if unknown:
        raise ValueError(f"Unsupported channels: {sorted(unknown)}")
    if not channels:
        raise ValueError("Select at least one channel")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            # Windows event loops may not support add_signal_handler.
            pass

    attempt = 0
    total_messages = 0
    try:
        while not stop_event.is_set():
            connected_at = utc_now()
            try:
                async with websockets.connect(
                    WS_URL,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                    open_timeout=15,
                    max_size=16 * 1024 * 1024,
                ) as socket:
                    attempt = 0
                    for coin in coins:
                        for channel in channels:
                            subscription: dict[str, Any] = {
                                "type": channel,
                                "coin": coin,
                            }
                            if channel == "candle":
                                subscription["interval"] = args.interval
                            await socket.send(json.dumps({
                                "method": "subscribe",
                                "subscription": subscription,
                            }))
                    archive.write(coins[0], "collector_status", {
                        "record_type": "connection",
                        "state": "connected",
                        "received_at_utc": connected_at.isoformat(),
                        "endpoint": WS_URL,
                        "coins": coins,
                        "channels": channels,
                    })
                    print(
                        f"Connected to Hyperliquid: coins={','.join(coins)} "
                        f"channels={','.join(channels)} output={base_dir}"
                    )

                    async for raw in socket:
                        if stop_event.is_set():
                            break
                        received_at = utc_now()
                        try:
                            message = json.loads(raw)
                        except json.JSONDecodeError:
                            archive.write(coins[0], "collector_status", {
                                "record_type": "parse_error",
                                "received_at_utc": received_at.isoformat(),
                                "raw": str(raw)[:2000],
                            })
                            continue

                        channel = str(message.get("channel", "unknown"))
                        data = message.get("data")
                        if channel not in VALID_CHANNELS:
                            # Keep subscription acknowledgements and provider errors
                            # so diagnostics can explain absent data.
                            archive.write(coins[0], "collector_status", {
                                "record_type": "provider_message",
                                "received_at_utc": received_at.isoformat(),
                                "message": message,
                            })
                            continue

                        data_coin = None
                        if isinstance(data, dict):
                            data_coin = data.get("coin") or data.get("s")
                        elif isinstance(data, list) and data and isinstance(data[0], dict):
                            data_coin = data[0].get("coin") or data[0].get("s")
                        coin = str(data_coin or coins[0]).upper()
                        if coin not in coins:
                            coin = coins[0]
                        archive.write(coin, channel, {
                            "record_type": "market_data",
                            "provider": "hyperliquid",
                            "channel": channel,
                            "coin": coin,
                            "received_at_utc": received_at.isoformat(),
                            "payload": data,
                        })
                        total_messages += 1
                        if total_messages % 1000 == 0:
                            print(f"Captured {total_messages:,} market-data messages")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                attempt += 1
                failed_at = utc_now()
                archive.write(coins[0], "collector_status", {
                    "record_type": "connection",
                    "state": "disconnected",
                    "connected_at_utc": connected_at.isoformat(),
                    "disconnected_at_utc": failed_at.isoformat(),
                    "reconnect_attempt": attempt,
                    "error": f"{type(exc).__name__}: {exc}",
                    "data_gap_possible": True,
                })
                print(
                    f"Feed disconnected (attempt {attempt}): {type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
                delay = min(args.reconnect_max, args.reconnect_base * (2 ** min(attempt - 1, 6)))
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
    finally:
        archive.close()
    print(f"Stopped. Total received market-data messages: {total_messages:,}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coins", nargs="+", default=["BTC", "ETH"], help="Hyperliquid coin names, e.g. BTC ETH SOL")
    parser.add_argument("--channels", default="trades,l2Book,candle", help="Comma list: trades,l2Book,candle")
    parser.add_argument("--interval", default="1m", help="Candle interval for the candle subscription")
    parser.add_argument("--output", default="data/raw/hyperliquid", help="Output root, default data/raw/hyperliquid")
    parser.add_argument("--flush-every", type=int, default=1, help="Flush after N messages per output file (default 1 for safer capture)")
    parser.add_argument("--reconnect-base", type=float, default=1.0, help="Reconnect base delay in seconds")
    parser.add_argument("--reconnect-max", type=float, default=30.0, help="Maximum reconnect delay in seconds")
    return parser


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(collect(build_parser().parse_args())))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
