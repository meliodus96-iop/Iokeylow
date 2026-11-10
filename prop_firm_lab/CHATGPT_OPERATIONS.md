# ChatGPT ↔ GitHub research operating protocol

This document defines how a ChatGPT session with the user's GitHub connector can operate the research platform.

## What is automated

- A change to `prop_firm_lab/requests/current_run.json` on the research branch triggers GitHub Actions.
- GitHub Actions installs the pinned engines, runs the strategy adapter, custom account-rule replay and LuxAlgo bootstrap Monte Carlo.
- Results are attached to the exact workflow run as an artifact.
- ChatGPT can read the run metadata, logs, and artifact through the connected GitHub integration, then write a review and the next run request.

This is **turn-driven orchestration**, not an always-on ChatGPT process. GitHub Actions runs independently after a push. ChatGPT does not receive an unsolicited conversation callback when a job completes; it must inspect the run during the current or a later turn. Do not promise background monitoring or claim a run completed before GitHub confirms it.

## ChatGPT run procedure

1. Read this file, `README.md`, `ARCHITECTURE.md`, the active request, the selected firm profile, strategy config, and the previous run manifest.
2. Confirm the repository is private before placing market data, account exports or full research artifacts in it.
3. Check that the profile has `verification.status = "verified"`, official source URLs and a recent verification timestamp. If not, stop and request/perform rule verification before a research run.
4. Check the selected challenge/rule semantics, timezone/session reset, contract specs, leverage/margin, fees, spread, slippage, financing, data vendor, instrument, data range, timestamp quality and strategy code version.
5. Check that the request points to a valid Nautilus strategy adapter returning:
   - `trade_log.csv`: `open_time,close_time,r,direction`, with net-of-costs `r` values and timezone-aware timestamps.
   - `equity_events.csv`: `timestamp,balance,equity,event_type`, where event types are `mark`, `trade_close` or `day_end`.
6. Set `mode = "research"` and fill only verified input paths/parameters in `requests/current_run.json`. Use a deterministic seed and preserve the exact config.
7. Commit the request update to `prop-firm-research-platform`. The push event is the trigger; the GitHub connector does not expose a separate workflow-dispatch action in this environment.
8. Query the GitHub Actions run list for the new head SHA. Wait until GitHub reports `completed`; inspect the job steps and logs. A failed or cancelled run is not a result.
9. Download the artifact associated with that run. Read `run_manifest.json`, the custom rule summary and ledger, the LuxAlgo raw JSON/assumption flags, payout estimate and Nautilus manifest. Verify input checksums and commit SHA match the requested run.
10. Report results with market evidence separated from software tests. Include breach times, pass probability and confidence interval, expected attempts/cost, funded payout probability, drawdown distribution, limitations and data granularity. Treat simulations as conditional estimates, not predictions.
11. Recommend one bounded follow-up test at a time. Do not automatically optimize on the untouched holdout or change multiple parameters after seeing results.

## Fail-closed conditions

Stop rather than guess when:
- the repository is public;
- the official firm rules or contract specification are ambiguous/unverified;
- strategy adapter or input paths are missing;
- timestamps lack timezone offsets or the data is corrupted;
- trade logs do not contain reliable net R values;
- equity-event granularity cannot support the firm's loss-rule checks;
- a rule mode/metric combination is unsupported;
- a dependency or workflow check fails.

## Safety and scope

This platform is research-only. Do not connect live broker trading, place orders, store broker passwords/API keys in the repository, or imply a simulated account has equivalent live-market fills. Keep real account data, trade logs and reports in a private repository or private storage. Use GitHub Actions secrets for any future vendor credentials and never print secrets into logs.
