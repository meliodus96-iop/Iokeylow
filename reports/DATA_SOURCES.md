# Phase 1 Data Sources

1. Public NIFTY 5-minute historical release
Source repository: voletiramu/nse-fno-1min-data
Used file: NIFTY_5min_5yr_2021_2026.csv
Coverage: April 2021–April 2026.

2. Public offline NIFTY option sample
Source repository: rajmaurya0904/bhav
Used workbook: sample_data/nifty_1y_1min.xlsx
Coverage: July 2025–June 2026.
Sheets:
- Spot_1min
- ATM_Options_1min

3. Public TickBytes repository
Source: QuantDev-stack/TickBytes
The repository documents and samples:
- NIFTY futures tick/L1/L2 fields
- NIFTY option tick/L1/L2 fields
- top-5 bid/ask depth
- trade quantity/time
- option Greeks
The public repository currently exposes sample files; it is not treated as a free multi-year historical L2 archive.

Important:
The current Phase-1 signal results do NOT use TickBytes historical L2. They use price/participation proxies. That distinction is intentional.
