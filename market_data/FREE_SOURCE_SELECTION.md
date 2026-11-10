# Free market-data sources and tool selection

## User requirement

Primary coverage is crypto, XAUUSD/other supported spot metals, and spot FX. CME, Nasdaq and other listed exchanges are optional. The selection must not require a paid market-data plan, paid API key, paid model, or third-party subscription.

The software license and the underlying data terms are separate. A free GitHub repository does not automatically make every upstream market-data archive free for every use.

## Selected collection paths

### Crypto: CCXT + native public feeds

- CCXT (MIT): https://github.com/ccxt/ccxt
- Binance public market-data endpoints: https://developers.binance.com/
- Hyperliquid public WebSocket: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket

The project fetcher tools/fetch_crypto_ccxt.py downloads exchange OHLCV, a recent public-trade page, or a current order-book snapshot using public exchange endpoints. It does not need account credentials for these public operations. Retention, pagination, symbol conventions, geographic restrictions and rate limits remain exchange-specific.

For Hyperliquid, tools/collect_hyperliquid_stream.py subscribes to public trades, L2 book snapshots and candles, then archives raw WebSocket envelopes locally as JSONL. The collector records receive timestamps and disconnect markers. It starts collecting only when launched; it cannot reconstruct messages missed before startup or during network gaps. It records L2 snapshots, not L3 individual orders.

The Binance USD-M/spot public WebSocket endpoints can expose trades, candles and book updates without API credentials. The CCXT order-book command is only a one-time snapshot. For a strategy that specifically needs Binance depth history, run an explicit sequence-aware collector and archive the stream; do not mistake a current snapshot for a historical book.

### Crypto historical archives: Binance Vision (restricted optional path)

- Repository: https://github.com/binance/binance-public-data
- Fetcher: tools/fetch_binance_vision.py
- Data: monthly/daily klines and aggregate trades for supported Binance spot, USD-M and COIN-M markets.
- Integrity: the fetcher downloads the corresponding checksum, verifies SHA-256 and then converts the CSV to Parquet.

Important terms: the current Binance Vision agreement limits the archive to non-commercial uses such as personal non-production historical backtesting and explicitly prohibits live proprietary trading execution and commercial order generation. It is therefore NOT the default evidence source for a strategy intended for funded/live proprietary execution. The script requires the explicit --accept-noncommercial-terms option and should only be used when that restriction fits the actual use. Binance public API/WS calls are a separate route and are governed by the exchange's applicable terms.

### Gold, silver and Forex: Dukascopy Node

- Repository/tool: https://github.com/Leo4815162342/dukascopy-node
- Source fetcher code license: MIT
- Wrapper in this repository: tools/fetch_dukascopy.ps1
- Node.js 20+ required by the current tool documentation; no API key is configured.

The upstream instrument catalogue includes XAUUSD with tick and OHLC data, EURUSD and other FX pairs, and some other spot metals/commodities. Examples include xauusd, eurusd, xagaud, xaucad, xpdcmdusd and xptcmdusd; verify the current instrument catalogue before requesting another contract.

Dukascopy tick records are bid/ask price updates with provider timestamps and quote sizes. They are not centralized executed trades, not exchange aggressor volume, and not order-book depth. XAUUSD is an OTC/CFD quote stream, not COMEX GC/MGC or MCX Gold. Its prices and spread can differ from the user's execution broker. For execution-sensitive backtests, later compare the signal and cost assumptions to the actual intended broker feed.

## Specialist open-source terminals: what they actually cost

| Project | Code cost/license | Free data path | Important boundary | Our decision |
|---|---|---|---|---|
| HyperData Terminal: https://github.com/Co-Messi/HyperData-Terminal | Free, Apache-2.0 | Public Hyperliquid, Binance, Bybit, OKX, Coinbase and Deribit feeds; no exchange keys for its public-feed functions | Live dashboard/API/MCP and in-memory hub, not a multi-year raw historical archive; crypto-focused, not Gold/FX | Recommended optional live crypto monitor, not the canonical archive |
| Tape & Book: https://github.com/Tworasos/tape-and-book | Free, MIT | Binance live depth/tape without an API key; Binance REST historical klines with exchange-reported taker-buy volume | Its live book is Binance, not Hyperliquid. It does not give free NQ/MNQ CME depth; the README says CME history/live depth needs a paid feed/subscription. Do not treat candle bars as historical L2 | Useful optional Binance order-flow terminal and research journal |
| EdgeDepth Terminal: https://github.com/edgedepthhq/edgedepth-terminal | Free self-hosted terminal, AGPL-3.0; gateway MIT | Local Docker terminal with Binance public futures feed; no local API key/account; free published replay packs | Depth history starts when the local feed starts; recent observed footprint history is bounded and lost at restart. Hosted EdgeDepth provides extra replay/depth features on subscription | Useful optional visual order-flow terminal; not needed for core validation |
| MarketBridge: https://github.com/tianrking/MarketBridge | Public GitHub source; README shows an MIT badge, but no root LICENSE file was found in this review | Self-hosted public CEX feeds including Binance, Bybit, OKX and Hyperliquid, plus L2 snapshots, trades, funding/OI, candles and derived order-flow endpoints | It is a fast-moving v0.0.6 project. The default research config disables collectors and needs explicit configuration. The docs reviewed do not show a Dukascopy Gold/FX connector. Missing formal license file means do not vendor/copy its code until the author supplies a clear license | Keep under evaluation; do not make it a dependency yet |

These tools are not all paid subscriptions. HyperData Terminal, Tape & Book, and the self-hosted EdgeDepth terminal are free/open-source. EdgeDepth's hosted service has separate paid/limited features. Tape & Book documents paid CME data only for its optional Nasdaq-futures path. MarketBridge is self-hosted and does not advertise a mandatory subscription for public CEX endpoints, but its formal code license needs clarification.

## Databento: excluded from the free-only configuration

Databento is a data vendor, not a prerequisite for any of the free public feed paths above. Its historical data is usage-priced by data volume (no monthly subscription required for historical downloads); its Standard plan is a paid monthly plan that includes live data. New accounts may receive a one-time $125 historical-data credit, but that is not a permanent free data tier. We do not install its SDK or request its data in the free-only runtime.

## What accuracy means in this stack

- Crypto: exchange-reported public trades and exchange depth from one named venue can support genuine venue-specific CVD/footprint and L2 features. Keep Binance, Hyperliquid and other venues separate. A combined exchange book is not a real consolidated global book.
- Gold/Forex: Dukascopy bid/ask ticks can support quote-aware price/spread research. They cannot support true executed trade delta, footprint, absorption or DOM claims because OTC quote updates are not a centralized exchange tape/book.
- Historical order flow: the forward Hyperliquid collector accumulates from its start date onward. Binance historical aggTrades can support trade-flow research subject to its restrictive archive license. Free historical L2/L3 coverage is not guaranteed.
- No strategy is validated until it has a verified data manifest, correct instrument mapping, no look-ahead, costs and an untouched out-of-sample test.

## Local setup: the only required user actions

1. Install Git, Python 3.12 x64 and Node.js 20+ on the Windows computer. Node.js is needed only for Gold/FX Dukascopy downloads.
2. Open PowerShell in the cloned Iokeylow folder and check out the free-data branch (or use main after its pull request is merged):
   
   git fetch origin
   git checkout feature/free-market-data-fetchers
   git pull origin feature/free-market-data-fetchers

3. Install the isolated research runtime:
   
   powershell -ExecutionPolicy Bypass -File .\tools\install_market_data.ps1

4. Start with a small crypto candle test (end date is exclusive):
   
   .\.venv-marketdata\Scripts\python.exe tools\fetch_crypto_ccxt.py --exchange binanceusdm --symbol "BTC/USDT:USDT" --kind ohlcv --timeframe 1m --since 2026-11-01 --until 2026-11-02

5. Start a small Gold bid/ask tick test:
   
   .\tools\fetch_dukascopy.ps1 -Instrument xauusd -FromDate 2026-11-02 -ToDate 2026-11-03 -Timeframe tick

6. Start a continuous Hyperliquid capture when you want to begin accumulating raw order-flow history:
   
   .\.venv-marketdata\Scripts\python.exe tools\collect_hyperliquid_stream.py --coins BTC ETH --channels trades,l2Book,candle --interval 1m

   Keep that terminal running; Ctrl+C stops the collector. Data is stored below data/raw/hyperliquid. A local computer that sleeps or disconnects creates gaps. A VPS is optional for longer collection, not required to start.

7. Send the strategy rules and the downloaded data/report folder or commit the data-quality report to GitHub. I can inspect the rules/code and run analysis against the available files/reports. ChatGPT does not directly see files remaining only on your computer or maintain the WebSocket session inside chat.

No exchange API key, Databento key, paid model, broker login or trading permission is required by these free read-only fetchers. Do not paste passwords, private API keys or exchange credentials into chat or commit them to GitHub.
