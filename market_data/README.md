# Multi-asset market-data layer

## Status

This is an additive integration layer for the existing research repository. It does not replace the current `bhav`-based NIFTY strategy, alter its results, or switch any strategy to live execution.

The goal is one normalized data/research engine across crypto, metals, FX, equities and listed options, without installing several terminals that collect the same trades and books.

## Selected stack

### 1. Core engine: NautilusTrader

Repository: https://github.com/nautechsystems/nautilus_trader

Use NautilusTrader as the single event-driven market-data, historical-replay and backtesting engine. It has native adapters for major crypto venues, Deribit, Databento and Interactive Brokers, with custom adapters available for other REST/WebSocket sources.

The initial research environment is pinned to the stable 1.x line:

- Python 3.12 in a separate environment.
- `nautilus_trader==1.231.0` (the last published 1.x line).
- Do not mix 1.x code examples with the 2.x API; the APIs differ.
- NautilusTrader 2.0.0 release candidates are for testing, not the default live-capital runtime. Re-evaluate after an official stable 2.0 release.

Pinned local install (separate from the existing NIFTY environment):

```powershell
# Windows PowerShell, from the repository root
.\tools\install_market_data.ps1
```

The script creates `.venv-marketdata`, installs the exact versions in
`requirements-marketdata.txt`, and runs an import smoke test. It does not
change the existing `requirements.txt` or NIFTY strategy environment.

For Linux/macOS:

```bash
python3.12 -m venv .venv-marketdata
source .venv-marketdata/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-marketdata.txt
python tools/check_marketdata_install.py
```

Pinned packages:

- `nautilus_trader==1.231.0` — latest stable 1.x runtime; the 2.0 line is still release-candidate software.
- `databento==0.90.0` — official Python SDK for standalone file downloads, metadata lookups and cost estimates.

**Important:** NautilusTrader already bundles its Databento adapter using Databento's Rust client. The separate `databento` Python SDK is not required for that adapter; it is installed as a companion utility for direct historical-data and metadata workflows. Neither package grants data entitlement or supplies a Databento API key.

### 2. Institutional non-crypto feed: Databento

Provider: https://databento.com/

Use Databento where exchange-native book depth and historical trade data are required, especially:

- COMEX Gold futures (GC/MGC) and other CME Group futures/options through `GLBX.MDP3`.
- MBO for order-by-order/L3 reconstruction where the dataset supplies it.
- MBP-10 for ten-level/L2 depth where the dataset supplies it.
- US equities and listed options only with the correct venue-specific dataset/schema. Do not assume every Databento equity dataset contains MBO; for example, the EQUS Mini product is aggregated top-of-book, not MBO.
- OPRA options data is trades/quotes/NBBO coverage, not an order-by-order options book.

Databento is a paid/licensed data provider, not a GitHub dependency. Validate instrument, venue, schema, history and redistribution rights before purchasing or collecting.

#### Ordinary candles and in-depth data

The same provider can supply both. For the CME Globex dataset, Databento's native OHLCV schemas are:

- `ohlcv-1s`: 1-second candles
- `ohlcv-1m`: 1-minute candles
- `ohlcv-1h`: 1-hour candles
- `ohlcv-1d`: daily candles

Five-minute and 15-minute bars can be resampled from 1-minute bars, or aggregated from raw trades through NautilusTrader. No candle is emitted for an interval with no trade, so missing intervals must remain explicitly missing rather than be filled with invented prices.

Choose OHLCV for ordinary charting and longer-horizon research. Choose TRADES/TBBO/MBP-10/MBO when the hypothesis needs trade-by-trade activity or order-book detail. The correct schema and history depth depend on the specific dataset and data plan; not every asset class or dataset exposes MBO.

### 3. Native crypto feeds through NautilusTrader

Start with only the venues that add research value:

- Binance: spot and perpetual markets.
- Hyperliquid: spot and perpetual markets.
- Deribit: crypto futures and options.
- Bybit: spot, perpetuals and supported options markets.
- Coinbase: spot market context.

Subscribe only to data types that each venue actually exposes. Store venue-separated trade flow and book data; never silently combine different venue books into one fictitious consolidated order book.

## Asset coverage and honest limits

| Asset/product | Preferred source | Important limitation |
|---|---|---|
| BTC/ETH and liquid crypto perps | Native NautilusTrader venue adapters | Book depth, history and aggressor fields vary by venue and product. |
| BTC/ETH crypto options | Deribit adapter; add another venue only when trade-level data is available | An option chain or OI snapshot is not options flow. |
| COMEX Gold futures (GC/MGC) | Databento `GLBX.MDP3` | Paid data. Request MBO or MBP-10 explicitly; a candle feed is not order flow. |
| MCX Gold futures | Official MCX feed or licensed distributor, then a custom Nautilus adapter | Not treated as covered by a built-in Nautilus adapter. |
| XAUUSD spot/CFD | Broker/ECN feed | OTC liquidity is fragmented. A broker's DOM is not a consolidated global Gold order book. |
| CME FX futures | Databento `GLBX.MDP3` | Centralized futures order flow; it is not identical to spot FX. |
| Spot FX | Broker feed such as Interactive Brokers, subject to entitlements | Broker-specific liquidity/depth, not a consolidated global FX book. |
| US equities | Databento venue-specific feed or Interactive Brokers | L3/MBO availability is dataset-specific. |
| US equity options | OPRA through a licensed provider | Trades/quotes/NBBO do not imply a full MBO book. |
| NSE equities and NIFTY F&O | Licensed NSE real-time/tick feed or authorised vendor, then a custom adapter | Exchange permissions and data licensing apply. |
| MCX non-Gold commodities | Licensed MCX feed or approved distributor, then a custom adapter | Contract-specific depth and historical availability must be confirmed. |

For India, official exchange feeds are the correct route for genuine exchange data. NSE documents L1, L2, L3 and tick-by-tick products. MCX documents historical order-book and trade-book data, with tick-by-tick history available for selected commodities/contracts. Neither is a free, universal public feed.

## Data path

```text
Exchange / licensed vendor
        |
        v
NautilusTrader venue or provider adapter
        |
        v
Normalized timestamped events + venue/instrument identity
        |
        +----> immutable raw archive / Parquet catalog
        |
        +----> order-book reconstruction and data-quality checks
        |
        v
Order-flow analytics
  footprint | delta/CVD | OFI | absorption | sweeps | liquidity changes
        |
        v
Backtest / paper simulation / research reports
        |
        v
ChatGPT analysis through the connected GitHub project and saved reports
```

The new source registry lives in `market_data/providers.json`. The data semantics and minimum quality rules are in `market_data/DATA_CONTRACT.md`.

## Why we are not adding more terminals

These projects overlap the selected ingestion/analytics layer and are not being installed as separate collectors:

- Flowdepth: useful crypto-specific UI, footprint and GEX research, but duplicates the core ingestion and footprint pipeline and is beta software.
- HyperData Terminal: useful cross-venue liquidation/whale monitor, but its CVD and positioning coverage overlaps the selected feeds; it is not a full footprint engine.
- EdgeDepth and Tape & Book: useful visual/research references, but their tape/DOM/footprint features overlap the analytics we will compute once from normalized events.
- MarketBridge: interesting aggregator and footprint API, but it duplicates the chosen connector layer and its repository does not declare a recognised open-source licence. Do not copy or vendor its code without permission/licence clarification.
- GC-MBO-ML: a narrow COMEX Gold experiment, not a general multi-asset engine; its documented directional model gates were NO-GO. Do not use its model as a source of trading signals.

This is intentional deduplication: one collection path, one canonical event model, one analytics implementation.

## ChatGPT / GitHub connection

The GitHub connector is linked to this repository, so ChatGPT can inspect the source registry, read research outputs, review code and make repository changes when asked.

ChatGPT does **not** maintain a persistent WebSocket connection or ingest an always-on tick stream directly inside a chat. The live collector must run on a user-controlled workstation/VPS or another always-on host. GitHub Actions should handle bounded jobs such as manifest checks, scheduled historical backfills, research runs and report publishing—not a permanent low-latency market-data daemon.

For an assistant-readable handoff, publish compact, timestamped, read-only summaries and validation reports into this repository. Never publish API keys, private keys, account identifiers or raw account data. Put credentials in the runtime's secret manager/GitHub Actions Secrets and keep the market API read-only during research.

## Activation gates

1. Confirm the intended instrument universe and data entitlements.
2. Run a provider smoke test and verify sequence continuity, timestamps and instrument mapping.
3. Record raw events before computing derived features.
4. Validate footprint aggressor-side semantics, depth continuity and missing-data handling.
5. Compare derived features against exchange/vendor reference outputs.
6. Only then expose the feature stream to a strategy or backtest.
7. Keep all live order execution disabled until separately reviewed and explicitly enabled.

No profitability claim is made by this integration.
