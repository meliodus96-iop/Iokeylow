# Prop Firm Research Lab

This is a GitHub Actions research platform that joins three separate layers:

1. **NautilusTrader 2.x** — event-driven market backtesting and execution simulation.
2. **Custom prop-firm rule engine** — intratrade equity, daily loss, overall loss, session resets, consistency and payout-buffer checks.
3. **LuxAlgo Prop Firm Sim CLI** — deterministic Monte Carlo challenge/funded-account economics using timestamped R-multiple trade logs.

It is a research system, not a live-trading bot. No broker credentials, prop-firm credentials, or order-routing permissions belong here.

## Important repository privacy notice

The initial scaffold is being added to the existing `meliodus96-iop/Iokeylow` repository, which is **public** and currently contains a separate NIFTY Phase-1 research project. The prop-firm files are isolated under `prop_firm_lab/` and on branch `prop-firm-research-platform`.

The workflow intentionally blocks `research` mode on public repositories. Do not commit proprietary market data, account statements, strategy source, or real performance reports to this public repository. Move this scaffold to a dedicated private repository before real research runs.

## Quick start

### Software-only smoke test

1. Open GitHub → Actions → **Prop Firm Research**.
2. Run workflow with `run_mode = smoke`.
3. The workflow installs NautilusTrader 2.x and the pinned LuxAlgo CLI, tests the custom rule engine, runs a synthetic NautilusTrader backtest, and runs a synthetic LuxAlgo Monte Carlo check.
4. Download the `prop-firm-smoke-*` artifact.

Smoke data is only a software check. It is not a strategy backtest, market evidence, or a profitability claim.

### Full research run

Full research requires a **private GitHub repository**, real market data, a strategy module, a verified firm profile, and a strategy configuration. The full workflow is:

1. A strategy adapter runs a NautilusTrader backtest.
2. The adapter writes `trade_log.csv` and `equity_events.csv`.
3. The custom rule engine replays equity events at the available market-data resolution and records every rule breach.
4. LuxAlgo Prop Firm Sim bootstraps the timestamped R-multiple history against the selected challenge rules.
5. A manifest, annotated rule ledger, custom-rule summary, Monte Carlo result and assumptions are saved as a GitHub Actions artifact.

To request a run, edit `requests/current_run.json` in the private repository. A push to the tracked branch starts the workflow. ChatGPT can prepare that request through the connected GitHub integration and inspect the completed Actions run/artifact in a subsequent interaction.

## Nautilus strategy adapter contract

Set `strategy_entrypoint` to `python_module:function_name`. The function must accept keyword arguments:

```python
def run_backtest(*, data_path, output_dir, config):
    # Build/run a NautilusTrader BacktestEngine or BacktestNode.
    # Use real historical data and realistic instrument/venue specifications.
    # Export closed trades and timestamped account equity marks.
    return {
        "trade_log": "trade_log.csv",
        "equity_events": "equity_events.csv",
        "data_granularity": "quote",  # tick | quote | trade | bar | close-only
    }
```

Required output files:

- `trade_log.csv`: `open_time,close_time,r,direction`. Timestamps must include a UTC offset. R must be net of the costs applied in the backtest. At least 10 completed R observations are required by the LuxAlgo bootstrap route.
- `equity_events.csv`: `timestamp,balance,equity,event_type`, where `event_type` is `mark`, `trade_close`, or `day_end`. Include sufficiently frequent marked-to-market snapshots to test floating loss and intraday trailing rules. A bar-only or close-only series cannot establish true tick-level breach behaviour.

Do not call a bar-based simulation "tick accurate". The run manifest records the supplied data granularity.

## Firm profiles

Start from `profiles/profile.template.json`. Fill the profile only after checking the firm's current official terms and platform specifications. Set `verification.status = "verified"`, record the date and official source URLs, and complete every loss-rule semantic.

The rule engine deliberately rejects unverified or incomplete profiles in research mode. It does not assume that phrases such as "daily loss" or "trailing drawdown" have a universal meaning.

The LuxAlgo ruleset can be selected using either:
- `luxalgo.mode = "directory"` with the exact directory firm and challenge IDs; or
- `luxalgo.mode = "inline"` with a path to a reviewed LuxAlgo-compatible JSON spec.

LuxAlgo's assumptions and flags must be retained in the report. Its documented limitations include same-day trade modelling and no intra-trade adverse/favourable excursions; the custom event-level rule engine is a separate control, not a claim that those limitations disappear.

## Security and reproducibility

- No API keys are needed for the software smoke path.
- Never put secrets in workflow files or commits.
- Pin Python package and npm CLI versions for reproducibility.
- Use a fixed Monte Carlo seed and preserve the run manifest.
- Keep raw market datasets and real account exports in private storage.
- Keep the original data immutable; store checksums in the run manifest.
- Treat third-party rule directories as references; official firm terms are authoritative.


## ChatGPT research control

See [CHATGPT_OPERATIONS.md](./CHATGPT_OPERATIONS.md) for the turn-driven ChatGPT/GitHub run protocol, artifact review checklist and fail-closed conditions.

A strategy adapter template is provided at `strategies/adapter_template.py`. It intentionally raises `NotImplementedError` until a real strategy is implemented; no trades or performance are fabricated.
