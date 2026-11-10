# Massive market-data integration

This folder documents two complementary ways to use Massive.

## 1. LLM-facing MCP connector

Massive hosts its MCP server at https://mcp.massive.com/. It uses OAuth, so a compatible client can connect without installing a local server or putting an API key in this repository.

This repository includes .vscode/mcp.json for VS Code / GitHub Copilot. Open the MCP panel in VS Code, start the Massive server, and complete the browser-based OAuth flow. Data access follows the Massive account's subscription entitlements.

For ChatGPT, connect the Massive app from the ChatGPT app directory and complete OAuth. The repository configuration does not automatically install an app into a ChatGPT account or this conversation. Setup instructions: https://massive.com/docs/ai-tools/clients/chatgpt

## 2. Historical-data ingestion for GitHub Actions / NautilusTrader

The research environment uses Massive's official Python SDK, pinned in pyproject.toml as massive==2.9.1.

Set MASSIVE_API_KEY as a GitHub Actions secret in the repository that will hold the private research environment. Never put it in a committed file, workflow YAML, notebook, or log.

Example local command:

    export MASSIVE_API_KEY=your_key
    python -m propfirm_lab.market_data.fetch --ticker X:BTCUSD --multiplier 5 --timespan minute --from-date 2025-01-01 --to-date 2025-02-01 --output prop_firm_lab/data/input/btcusd_5m.csv

Ticker formats are provider-specific. Examples include AAPL for a stock, C:EURUSD for a forex pair, and X:BTCUSD for a crypto pair. Verify the exact ticker and data entitlement in Massive before running. XAUUSD/CFD broker feeds must be checked for coverage and must not be assumed equivalent to COMEX Gold futures or a prop firm's broker quote.

The downloader uses Massive's official REST client (including pagination), writes UTC candle timestamps, OHLCV, VWAP and transaction count to CSV, rejects empty results, duplicate timestamps and invalid OHLC values, and writes a SHA-256 manifest beside the dataset.

This is an aggregate-bar downloader. It does not create tick, bid/ask quote, Level 2, or Level 3 data. Those must be fetched from the relevant endpoint and are subject to separate subscription entitlements.

## GitHub Actions

Use the Massive Market Data Fetch workflow after it is merged into the default branch. It requires:

1. A private repository (the current repository is public, so real-data workflows intentionally fail closed).
2. A repository Actions secret named MASSIVE_API_KEY.
3. A valid ticker, timeframe and date range supported by the account's plan.

Downloaded datasets are uploaded as workflow artifacts and are not committed to Git. Keep broker-specific and subscription-restricted market data in private storage and follow the vendor's data-use terms.
