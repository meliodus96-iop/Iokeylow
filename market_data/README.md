# Free multi-asset market-data layer

This research-only layer provides a free-first collection path for crypto, XAUUSD/other supported metals and spot Forex. CME/Nasdaq and other listed venues are optional. The configured public fetchers do not require paid data subscriptions, paid AI models or exchange API keys.

## Stack

- NautilusTrader 1.231.0: open-source event-driven research and backtesting engine.
- CCXT 4.5.92: public crypto exchange API client.
- Hyperliquid WebSocket collector: raw trades, L2 snapshots and candle capture from the time it is started.
- Binance Vision: optional historical candles/aggregate trades; use only for personal non-commercial non-production research under its current restrictive terms.
- Dukascopy Node 1.51.1: free historical bid/ask ticks and OHLC for XAUUSD, FX and selected other instruments; Node.js 20+ required.

## Install on Windows

Install Git, Python 3.12 x64 and Node.js 20+. From PowerShell in the cloned repository:

~~~powershell
git fetch origin
git checkout feature/free-market-data-fetchers
git pull origin feature/free-market-data-fetchers
powershell -ExecutionPolicy Bypass -File .\tools\install_market_data.ps1
~~~

## Fetch data

BTC/USDT USD-M 1-minute candles (example, one day):

~~~powershell
.\.venv-marketdata\Scripts\python.exe tools\fetch_crypto_ccxt.py --exchange binanceusdm --symbol BTC/USDT --kind ohlcv --timeframe 1m --since 2026-11-01 --until 2026-11-02
~~~

XAUUSD tick quotes (one day):

~~~powershell
.\tools\fetch_dukascopy.ps1 -Instrument xauusd -FromDate 2026-11-02 -ToDate 2026-11-03 -Timeframe tick
~~~

Collect Hyperliquid live trades, L2 and 1-minute candles from now onward:

~~~powershell
.\.venv-marketdata\Scripts\python.exe tools\collect_hyperliquid_stream.py --coins BTC ETH --channels trades,l2Book,candle --interval 1m
~~~

Keep the collector terminal running; Ctrl+C stops it. Captured files are stored below data/raw and are Git-ignored. Disconnects are recorded as possible data gaps.

## Important precision boundaries

CCXT's one-time order-book snapshot is not historical L2. The Hyperliquid collector stores L2 snapshots from startup, not L3 order-by-order events, and cannot recover data missed before startup or during a disconnect. Dukascopy XAUUSD/FX tick records are OTC bid/ask quote changes, not centralized executed trades or a global order book; they are not COMEX GC/MGC or MCX Gold data. Use broker-matched data for execution-sensitive validation where possible.

Binance Vision's current archive terms limit use to personal non-commercial non-production research/backtesting and prohibit live proprietary execution/commercial order generation. The archive downloader requires an explicit acknowledgement and is not an unrestricted source for funded/live strategies.

## Reviewed free order-flow terminals

- HyperData Terminal: free Apache-2.0, public Hyperliquid/Binance/Bybit/OKX/Deribit data, live CVD/liquidation/whale views; monitor/API/MCP, not a full multi-year raw archive.
- Tape & Book: free MIT, Binance live depth/tape and public historical candles; its Nasdaq/CME path requires a paid feed.
- EdgeDepth Terminal: free self-hosted AGPL-3.0 app with MIT gateway, Binance public feed and replay packs; observed depth history starts at launch and is bounded. Hosted extras may be paid.
- MarketBridge: broad self-hosted crypto market-data API and order-flow features; README displays an MIT badge, but no root LICENSE file was found, and no Gold/Forex connector was found. Do not vendor its code until its license is clarified.

Databento is excluded. Historical data is usage-priced; its live Standard plan is a paid monthly subscription. New-account credits are temporary, not a permanent free tier.

See FREE_SOURCE_SELECTION.md for the full project-by-project comparison and user setup flow; providers.json for the source registry; DATA_CONTRACT.md for event and data-quality semantics.