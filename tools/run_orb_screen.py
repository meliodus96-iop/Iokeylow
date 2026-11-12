#!/usr/bin/env python3
"""Screen a controlled 240-variant ORB grid with VectorBT.

This is a fast development-screening tool, not final execution validation.
It requires 1-minute OHLC bars with a timestamp column and open/high/low/close.
It uses only data strictly before --dev-end; later observations are not scored.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt

ROOT = Path(__file__).resolve().parents[1]

RANGE_MINUTES = (5, 10, 15, 20, 30)
BREAKOUT_BUFFER_ATR = (0.0, 0.05, 0.10)
STOP_MODES = ("opposite_range", "breakout_bar")
TARGET_R = (1.5, 2.0, 2.5, 3.0)
ENTRY_WINDOWS = (60, 120)


@dataclass(frozen=True)
class Variant:
    variant_id: str
    range_minutes: int
    buffer_atr: float
    stop_mode: str
    target_r: float
    entry_window_minutes: int


def parse_hhmm(value: str) -> int:
    try:
        hour, minute = value.split(":")
        h, m = int(hour), int(minute)
    except Exception as exc:
        raise argparse.ArgumentTypeError("Time must be HH:MM") from exc
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise argparse.ArgumentTypeError("Time must be a valid HH:MM value")
    return h * 60 + m


def variants() -> list[Variant]:
    raw = list(itertools.product(
        RANGE_MINUTES, BREAKOUT_BUFFER_ATR, STOP_MODES, TARGET_R, ENTRY_WINDOWS
    ))
    return [
        Variant(
            variant_id=f"orb_{i:03d}",
            range_minutes=int(rng),
            buffer_atr=float(buf),
            stop_mode=str(stop),
            target_r=float(target),
            entry_window_minutes=int(window),
        )
        for i, (rng, buf, stop, target, window) in enumerate(raw, start=1)
    ]


def parse_timestamp(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        numeric = pd.to_numeric(series, errors="coerce")
        valid = numeric.dropna()
        if valid.empty:
            raise ValueError("Timestamp column contains no numeric values")
        maximum = float(valid.abs().max())
        unit = "us" if maximum >= 1e14 else "ms" if maximum >= 1e11 else "s"
        return pd.to_datetime(numeric, unit=unit, utc=True, errors="coerce")
    # ISO timestamps with explicit offsets are normalized to UTC. Naive
    # timestamps are treated as UTC and then converted to --timezone.
    return pd.to_datetime(series, utc=True, errors="coerce")


def load_data(
    path: Path,
    timestamp_col: str,
    timezone: str,
    dev_end: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() in (".parquet", ".pq"):
        raw = pd.read_parquet(path)
    elif path.suffix.lower() == ".csv":
        raw = pd.read_csv(path)
    else:
        raise ValueError("Input must be .parquet, .pq or .csv")

    raw.columns = [str(c).strip() for c in raw.columns]
    lookup = {c.lower(): c for c in raw.columns}
    if timestamp_col.lower() not in lookup:
        raise ValueError(
            f"Timestamp column {timestamp_col!r} not found. "
            f"Available columns: {list(raw.columns)}"
        )
    required = ("open", "high", "low", "close")
    missing = [name for name in required if name not in lookup]
    if missing:
        raise ValueError(f"Missing required OHLC columns: {missing}")

    timestamp = parse_timestamp(raw[lookup[timestamp_col.lower()]])
    frame = pd.DataFrame({
        "timestamp_utc": timestamp,
        "open": pd.to_numeric(raw[lookup["open"]], errors="coerce"),
        "high": pd.to_numeric(raw[lookup["high"]], errors="coerce"),
        "low": pd.to_numeric(raw[lookup["low"]], errors="coerce"),
        "close": pd.to_numeric(raw[lookup["close"]], errors="coerce"),
    })
    frame = frame.dropna(subset=["timestamp_utc", "open", "high", "low", "close"])
    frame = frame.sort_values("timestamp_utc").reset_index(drop=True)

    # Lock the development window before calculating indicators or signals.
    cutoff = pd.Timestamp(dev_end)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    else:
        cutoff = cutoff.tz_convert("UTC")
    input_rows = len(frame)
    frame = frame.loc[frame["timestamp_utc"] < cutoff].copy()
    if frame.empty:
        raise ValueError("No data remains before --dev-end")

    if frame["timestamp_utc"].duplicated().any():
        duplicates = int(frame["timestamp_utc"].duplicated().sum())
        raise ValueError(f"Found {duplicates} duplicate timestamps; clean the source first")

    invalid_ohlc = (
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
        | (frame["high"] < frame["low"])
    )
    if invalid_ohlc.any():
        raise ValueError(f"Found {int(invalid_ohlc.sum())} invalid OHLC rows")

    try:
        frame["local_timestamp"] = frame["timestamp_utc"].dt.tz_convert(timezone)
    except Exception as exc:
        raise ValueError(f"Invalid timezone {timezone!r}: {exc}") from exc

    frame["local_date"] = frame["local_timestamp"].dt.date
    frame["minute_of_day"] = (
        frame["local_timestamp"].dt.hour * 60
        + frame["local_timestamp"].dt.minute
    )
    frame["bar_minute"] = frame["local_timestamp"].dt.floor("min")

    previous_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    # Use ATR known before the breakout bar, not a future observation.
    frame["atr14"] = true_range.rolling(14, min_periods=14).mean().shift(1)

    gaps = frame["bar_minute"].diff().dropna()
    metadata = {
        "input_path": str(path),
        "input_rows_before_cutoff": input_rows,
        "development_rows": int(len(frame)),
        "development_start_utc": frame["timestamp_utc"].min().isoformat(),
        "development_end_utc_exclusive": cutoff.isoformat(),
        "development_end_row_utc": frame["timestamp_utc"].max().isoformat(),
        "sessions": int(frame["local_date"].nunique()),
        "timezone": timezone,
        "duplicate_timestamps": 0,
        "positive_timestamp_gaps": int((gaps > pd.Timedelta(minutes=1)).sum()),
        "note": "Rows at or after --dev-end were excluded before indicators/signals were calculated.",
    }
    return frame.reset_index(drop=True), metadata


def make_variants() -> list[Variant]:
    return variants()


def create_signals_for_batch(
    frame: pd.DataFrame,
    batch: list[Variant],
    session_start: int,
    session_end: int,
) -> tuple[dict[str, np.ndarray], dict[str, dict[int, float]], dict[str, dict[int, float]]]:
    n_rows = len(frame)
    n_cols = len(batch)
    long_entries = np.zeros((n_rows, n_cols), dtype=np.bool_)
    long_exits = np.zeros((n_rows, n_cols), dtype=np.bool_)
    short_entries = np.zeros((n_rows, n_cols), dtype=np.bool_)
    short_exits = np.zeros((n_rows, n_cols), dtype=np.bool_)
    sl_stop = np.full((n_rows, n_cols), np.nan, dtype=np.float32)
    tp_stop = np.full((n_rows, n_cols), np.nan, dtype=np.float32)
    risk_distance: dict[str, dict[int, float]] = {v.variant_id: {} for v in batch}
    signal_records: dict[str, dict[int, float]] = {v.variant_id: {} for v in batch}

    session_groups = frame.groupby("local_date", sort=True).indices

    for session_date, positions in session_groups.items():
        pos = np.asarray(positions, dtype=np.int64)
        group = frame.iloc[pos]
        in_session = (
            (group["minute_of_day"].to_numpy() >= session_start)
            & (group["minute_of_day"].to_numpy() < session_end)
        )
        session_pos = pos[in_session]
        if len(session_pos) < 20:
            continue

        session_frame = frame.iloc[session_pos]
        minute_values = session_frame["minute_of_day"].to_numpy()
        open_values = session_frame["open"].to_numpy(dtype=float)
        high_values = session_frame["high"].to_numpy(dtype=float)
        low_values = session_frame["low"].to_numpy(dtype=float)
        close_values = session_frame["close"].to_numpy(dtype=float)
        atr_values = session_frame["atr14"].to_numpy(dtype=float)
        timestamp_values = session_frame["local_timestamp"].tolist()

        # Map minute-of-day to this session's local row index.
        minute_to_local_idx: dict[int, int] = {}
        for local_idx, minute in enumerate(minute_values):
            minute_to_local_idx.setdefault(int(minute), local_idx)

        final_local_idx = len(session_pos) - 1
        final_global_idx = int(session_pos[final_local_idx])

        for col, variant in enumerate(batch):
            range_start = session_start
            range_end = session_start + variant.range_minutes
            if range_end >= session_end:
                continue

            range_local_indices = [
                minute_to_local_idx.get(minute)
                for minute in range(range_start, range_end)
            ]
            # Require every one-minute bar in the opening range. Missing bars
            # are not forward-filled or fabricated.
            if any(idx is None for idx in range_local_indices):
                continue
            range_idx = np.asarray(range_local_indices, dtype=np.int64)
            range_high = float(np.max(high_values[range_idx]))
            range_low = float(np.min(low_values[range_idx]))
            if not (math.isfinite(range_high) and math.isfinite(range_low) and range_high > range_low):
                continue

            latest_signal_minute = min(
                range_end + variant.entry_window_minutes,
                session_end - 1,
            )
            chosen: tuple[int, int, float, float] | None = None
            # Search only after the full opening range has closed. Signal is
            # confirmed at the bar close; entry is shifted to the next bar.
            for signal_local_idx, signal_minute in enumerate(minute_values):
                signal_minute = int(signal_minute)
                if signal_minute < range_end or signal_minute > latest_signal_minute:
                    continue
                if signal_local_idx >= final_local_idx:
                    continue
                if not math.isfinite(atr_values[signal_local_idx]) or atr_values[signal_local_idx] <= 0:
                    continue

                threshold = variant.buffer_atr * atr_values[signal_local_idx]
                long_break = close_values[signal_local_idx] > range_high + threshold
                short_break = close_values[signal_local_idx] < range_low - threshold
                if long_break and short_break:
                    continue
                if not long_break and not short_break:
                    continue

                entry_local_idx = signal_local_idx + 1
                # A signal may only be entered if the immediately following
                # one-minute bar exists; do not jump across missing intervals.
                signal_time = pd.Timestamp(timestamp_values[signal_local_idx])
                next_time = pd.Timestamp(timestamp_values[entry_local_idx])
                if next_time - signal_time != pd.Timedelta(minutes=1):
                    continue
                # Enter at the next bar's open. The signal was only known
                # after the previous bar closed, so this is the first causal
                # fill price available in this one-minute OHLC model.
                entry_price = float(open_values[entry_local_idx])

                if long_break:
                    stop_price = (
                        range_low
                        if variant.stop_mode == "opposite_range"
                        else float(low_values[signal_local_idx])
                    )
                    risk = entry_price - stop_price
                    if risk <= 0:
                        continue
                    side = 1
                else:
                    stop_price = (
                        range_high
                        if variant.stop_mode == "opposite_range"
                        else float(high_values[signal_local_idx])
                    )
                    risk = stop_price - entry_price
                    if risk <= 0:
                        continue
                    side = -1

                chosen = (entry_local_idx, side, entry_price, float(risk))
                break

            if chosen is None:
                continue

            entry_local_idx, side, entry_price, risk = chosen
            entry_global_idx = int(session_pos[entry_local_idx])
            if entry_global_idx >= final_global_idx:
                continue

            risk_pct = risk / entry_price
            if not math.isfinite(risk_pct) or risk_pct <= 0:
                continue

            if side > 0:
                long_entries[entry_global_idx, col] = True
                long_exits[final_global_idx, col] = True
            else:
                short_entries[entry_global_idx, col] = True
                short_exits[final_global_idx, col] = True

            # Stops are defined from the actual next-bar entry price. They stay
            # constant until the end-of-session exit; VectorBT checks OHLC.
            sl_stop[entry_global_idx:final_global_idx + 1, col] = risk_pct
            tp_stop[entry_global_idx:final_global_idx + 1, col] = (
                risk_pct * variant.target_r
            )
            risk_distance[variant.variant_id][entry_global_idx] = risk
            signal_records[variant.variant_id][entry_global_idx] = risk_pct

    arrays = {
        "entries": long_entries,
        "exits": long_exits,
        "short_entries": short_entries,
        "short_exits": short_exits,
        "sl_stop": sl_stop,
        "tp_stop": tp_stop,
    }
    return arrays, risk_distance, signal_records


def calculate_trade_metrics(
    records: pd.DataFrame,
    variant: Variant,
    risks_by_entry: dict[int, float],
    index: pd.DatetimeIndex,
    months_covered: int,
    risk_fraction: float,
) -> dict[str, Any]:
    if records.empty:
        return {
            **asdict(variant),
            "trades": 0,
            "trades_per_month": 0.0,
            "win_rate": np.nan,
            "expectancy_R": np.nan,
            "profit_factor": np.nan,
            "avg_realized_RR": np.nan,
            "max_drawdown_at_risk": np.nan,
            "net_R_total": 0.0,
        }

    r_values: list[float] = []
    for _, record in records.iterrows():
        entry_timestamp = pd.Timestamp(record["Entry Timestamp"])
        entry_idx = int(index.get_indexer([entry_timestamp])[0])
        if entry_idx < 0:
            continue
        risk_per_unit = risks_by_entry.get(entry_idx)
        if risk_per_unit is None or risk_per_unit <= 0:
            continue
        size = abs(float(record["Size"]))
        pnl = float(record["PnL"])
        denominator = risk_per_unit * size
        if denominator > 0 and math.isfinite(pnl):
            r_values.append(pnl / denominator)

    if not r_values:
        return {
            **asdict(variant),
            "trades": 0,
            "trades_per_month": 0.0,
            "win_rate": np.nan,
            "expectancy_R": np.nan,
            "profit_factor": np.nan,
            "avg_realized_RR": np.nan,
            "max_drawdown_at_risk": np.nan,
            "net_R_total": 0.0,
        }

    r = np.asarray(r_values, dtype=float)
    wins = r[r > 0]
    losses = r[r < 0]
    gross_win = float(wins.sum()) if len(wins) else 0.0
    gross_loss = abs(float(losses.sum())) if len(losses) else 0.0
    profit_factor = gross_win / gross_loss if gross_loss > 0 else (
        float("inf") if gross_win > 0 else np.nan
    )
    avg_realized_rr = (
        float(wins.mean() / abs(losses.mean()))
        if len(wins) and len(losses) else np.nan
    )

    equity = np.ones(len(r) + 1, dtype=float)
    for i, value in enumerate(r, start=1):
        equity[i] = equity[i - 1] * max(0.0, 1.0 + risk_fraction * value)
    running_peak = np.maximum.accumulate(equity)
    drawdown = equity / np.maximum(running_peak, 1e-12) - 1.0

    return {
        **asdict(variant),
        "trades": int(len(r)),
        "trades_per_month": float(len(r) / max(months_covered, 1)),
        "win_rate": float(np.mean(r > 0)),
        "expectancy_R": float(np.mean(r)),
        "profit_factor": float(profit_factor),
        "avg_realized_RR": float(avg_realized_rr),
        "avg_winner_R": float(wins.mean()) if len(wins) else np.nan,
        "avg_loser_R": float(losses.mean()) if len(losses) else np.nan,
        "max_drawdown_at_risk": float(np.min(drawdown)),
        "net_R_total": float(np.sum(r)),
        "worst_trade_R": float(np.min(r)),
        "best_trade_R": float(np.max(r)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="One-minute OHLC .parquet or .csv")
    parser.add_argument("--timestamp-col", default="ts_event")
    parser.add_argument("--timezone", required=True, help="IANA session timezone, e.g. America/New_York")
    parser.add_argument("--session-start", required=True, type=parse_hhmm, help="Local session start HH:MM")
    parser.add_argument("--session-end", required=True, type=parse_hhmm, help="Local session end HH:MM, exclusive")
    parser.add_argument("--dev-end", required=True, help="Exclusive UTC cutoff, e.g. 2025-01-01")
    parser.add_argument("--fees-bps", type=float, default=4.0, help="Fee per side in basis points")
    parser.add_argument("--slippage-bps", type=float, default=2.0, help="Slippage per side in basis points")
    parser.add_argument("--min-trades", type=int, default=30)
    parser.add_argument("--risk-fraction", type=float, default=0.01)
    parser.add_argument("--batch-size", type=int, default=8, help="Number of variants simulated at once")
    parser.add_argument("--output", default="output/strategy_lab/orb")
    args = parser.parse_args()

    if args.session_end <= args.session_start:
        parser.error("--session-end must be later than --session-start")
    if args.batch_size < 1 or args.batch_size > 32:
        parser.error("--batch-size must be between 1 and 32")
    if args.fees_bps < 0 or args.slippage_bps < 0:
        parser.error("Fees and slippage cannot be negative")
    if not (0 < args.risk_fraction <= 0.05):
        parser.error("--risk-fraction must be in (0, 0.05]")

    source = Path(args.input)
    frame, data_meta = load_data(
        source, args.timestamp_col, args.timezone, args.dev_end
    )
    if frame["timestamp_utc"].diff().dropna().median() != pd.Timedelta(minutes=1):
        raise ValueError(
            "Input does not appear to be 1-minute OHLC data. Resample raw ticks to "
            "1-minute bars without filling missing intervals before running ORB screening."
        )

    all_variants = make_variants()
    month_count = max(
        1,
        frame["local_timestamp"].dt.to_period("M").nunique(),
    )
    index = pd.DatetimeIndex(frame["timestamp_utc"])
    close = pd.Series(frame["close"].to_numpy(dtype=float), index=index, name="close")
    open_ = pd.Series(frame["open"].to_numpy(dtype=float), index=index, name="open")
    high = pd.Series(frame["high"].to_numpy(dtype=float), index=index, name="high")
    low = pd.Series(frame["low"].to_numpy(dtype=float), index=index, name="low")

    # Large initial cash and one unit per test isolate per-unit R results from
    # capital sizing. This is not a portfolio-margin or contract-multiplier model.
    initial_cash = max(1e7, float(frame["close"].max()) * 100.0)
    fees = args.fees_bps / 10000.0
    slippage = args.slippage_bps / 10000.0
    result_rows: list[dict[str, Any]] = []

    for start in range(0, len(all_variants), args.batch_size):
        batch = all_variants[start:start + args.batch_size]
        arrays, risk_maps, _ = create_signals_for_batch(
            frame, batch, args.session_start, args.session_end
        )
        columns = [variant.variant_id for variant in batch]
        entries = pd.DataFrame(arrays["entries"], index=index, columns=columns)
        exits = pd.DataFrame(arrays["exits"], index=index, columns=columns)
        short_entries = pd.DataFrame(arrays["short_entries"], index=index, columns=columns)
        short_exits = pd.DataFrame(arrays["short_exits"], index=index, columns=columns)
        sl_stop = pd.DataFrame(arrays["sl_stop"], index=index, columns=columns)
        tp_stop = pd.DataFrame(arrays["tp_stop"], index=index, columns=columns)

        portfolio = vbt.Portfolio.from_signals(
            close,
            entries=entries,
            exits=exits,
            short_entries=short_entries,
            short_exits=short_exits,
            price=open_,
            open=open_,
            high=high,
            low=low,
            sl_stop=sl_stop,
            tp_stop=tp_stop,
            stop_entry_price="price",
            size=1.0,
            fees=fees,
            slippage=slippage,
            init_cash=initial_cash,
            cash_sharing=False,
            lock_cash=False,
            freq="1min",
        )
        readable = portfolio.trades.records_readable
        for variant in batch:
            if readable.empty:
                trades_for_variant = readable
            else:
                trades_for_variant = readable.loc[
                    readable["Column"].astype(str) == variant.variant_id
                ]
            result_rows.append(
                calculate_trade_metrics(
                    trades_for_variant,
                    variant,
                    risk_maps[variant.variant_id],
                    index,
                    month_count,
                    args.risk_fraction,
                )
            )
        del portfolio, entries, exits, short_entries, short_exits, sl_stop, tp_stop

    results = pd.DataFrame(result_rows)
    results["eligible_minimum_trades"] = results["trades"] >= args.min_trades
    results["development_only_rank"] = np.nan
    eligible = results[
        results["eligible_minimum_trades"]
        & results["expectancy_R"].notna()
    ].copy()
    eligible = eligible.sort_values(
        ["expectancy_R", "max_drawdown_at_risk", "profit_factor"],
        ascending=[False, False, False],
        na_position="last",
    )
    ranks = {row.variant_id: i + 1 for i, row in enumerate(eligible.itertuples())}
    results["development_only_rank"] = results["variant_id"].map(ranks)
    results = results.sort_values(
        ["development_only_rank", "variant_id"],
        ascending=[True, True],
        na_position="last",
    )

    output_dir = Path(args.output)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "orb_240_variant_development_screen.csv"
    json_path = output_dir / "orb_240_variant_manifest.json"
    results.to_csv(csv_path, index=False)

    manifest = {
        "experiment": "ORB controlled 240-variant development screen",
        "software": {
            "vectorbt": "1.2.1",
            "optuna_installed_for_later_refinement": "5.0.0",
        },
        "data": data_meta,
        "session": {
            "timezone": args.timezone,
            "start": f"{args.session_start // 60:02d}:{args.session_start % 60:02d}",
            "end_exclusive": f"{args.session_end // 60:02d}:{args.session_end % 60:02d}",
            "bar_interval": "1min",
        },
        "execution_assumptions": {
            "signal": "breakout confirmed at candle close",
            "entry": "next available one-minute candle open after breakout confirmation at prior close",
            "stop_and_target": "VectorBT OHLC stop simulation using one-minute high/low; order price is next bar open",
            "target_collision": "same-bar stop/target ordering follows VectorBT's OHLC stop engine; inspect ambiguous bars before promotion",
            "fees_bps_per_side": args.fees_bps,
            "slippage_bps_per_side": args.slippage_bps,
            "risk_fraction_for_drawdown_illustration": args.risk_fraction,
            "position_size": "one unit per variant; R metrics normalized by initial stop distance",
            "not_modelled": [
                "broker-specific contract multiplier, lot size and margin",
                "queue position and partial fills",
                "spread path beyond the supplied OHLC bars",
                "funding/overnight financing",
                "exchange outages and live order rejection",
            ],
        },
        "search": {
            "variant_count": int(len(all_variants)),
            "minimum_trades_for_eligibility": args.min_trades,
            "eligible_variants": int(len(eligible)),
            "parameters": {
                "range_minutes": list(RANGE_MINUTES),
                "breakout_buffer_atr": list(BREAKOUT_BUFFER_ATR),
                "stop_mode": list(STOP_MODES),
                "target_r": list(TARGET_R),
                "entry_window_minutes": list(ENTRY_WINDOWS),
            },
            "selection_rule": "development-only descriptive ranking; do not deploy or select from this screen alone",
        },
        "outputs": {
            "results_csv": str(csv_path.relative_to(ROOT)),
        },
        "warning": (
            "This is a development screen. The runner excluded all rows at/after "
            "--dev-end and did not calculate holdout results. Freeze one simple "
            "candidate or a small stable cluster before opening a later untouched period."
        ),
    }
    json_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(json.dumps({
        "variants_tested": len(all_variants),
        "eligible_variants": len(eligible),
        "results_csv": str(csv_path),
        "manifest": str(json_path),
        "development_start": data_meta["development_start_utc"],
        "development_end_exclusive": data_meta["development_end_utc_exclusive"],
        "warning": "Development screen only. No holdout rows were scored.",
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
