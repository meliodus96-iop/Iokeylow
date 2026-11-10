from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .rules import PropFirmRuleEngine, calculate_payout, load_profile, read_equity_events


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(args: argparse.Namespace) -> dict:
    profile_path = Path(args.profile).resolve()
    trades_path = Path(args.trade_log).resolve()
    events_path = Path(args.equity_events).resolve()
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)

    profile = load_profile(profile_path, require_verified=True)
    lux = profile.get("luxalgo", {})
    if lux.get("mode") not in {"directory", "inline"}:
        raise ValueError("luxalgo.mode must be 'directory' or 'inline'")

    events = read_equity_events(events_path)
    engine = PropFirmRuleEngine(profile)
    rule_summary = engine.run(events)

    ledger_path = output / "rule_engine_ledger.csv"
    if engine.ledger:
        import csv
        columns = list(engine.ledger[0].keys())
        with ledger_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(engine.ledger)

    (output / "rule_engine_summary.json").write_text(json.dumps(rule_summary, indent=2), encoding="utf-8")

    command = ["prop-firm-sim", "simulate"]
    if lux["mode"] == "directory":
        if not lux.get("firm") or not lux.get("challenge"):
            raise ValueError("LuxAlgo directory mode requires exact firm and challenge IDs")
        command += ["--firm", str(lux["firm"]), "--challenge", str(lux["challenge"])]
    else:
        if not lux.get("spec_path"):
            raise ValueError("LuxAlgo inline mode requires spec_path")
        spec_path = Path(lux["spec_path"])
        if not spec_path.is_absolute():
            spec_path = Path.cwd() / spec_path
        if not spec_path.exists():
            raise FileNotFoundError(f"LuxAlgo spec not found: {spec_path}")
        command += ["--spec", str(spec_path)]
    command += [
        "--trade-log", str(trades_path),
        "--risk", str(profile.get("monte_carlo", {}).get("risk", "0.5%")),
        "--paths", str(int(profile.get("monte_carlo", {}).get("paths", 10000))),
        "--seed", str(int(profile.get("monte_carlo", {}).get("seed", 42))),
        "--json",
    ]
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    (output / "luxalgo_monte_carlo.json").write_text(completed.stdout, encoding="utf-8")
    (output / "luxalgo_monte_carlo.stderr.txt").write_text(completed.stderr, encoding="utf-8")

    last = engine.ledger[-1] if engine.ledger else {}
    payout = {}
    if rule_summary["breach"] is None:
        payout = calculate_payout(
            profile,
            balance=rule_summary["final_balance"],
            equity=rule_summary["final_equity"],
            current_overall_floor=float(last.get("overall_floor") or 0),
            winning_days=rule_summary["winning_days"],
        )
    (output / "payout_estimate.json").write_text(json.dumps(payout, indent=2), encoding="utf-8")

    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "github_sha": os.getenv("GITHUB_SHA"),
        "github_run_id": os.getenv("GITHUB_RUN_ID"),
        "profile_path": str(profile_path),
        "profile_sha256": sha256(profile_path),
        "trade_log_path": str(trades_path),
        "trade_log_sha256": sha256(trades_path),
        "equity_events_path": str(events_path),
        "equity_events_sha256": sha256(events_path),
        "events_processed": len(events),
        "outputs": [
            "rule_engine_ledger.csv",
            "rule_engine_summary.json",
            "luxalgo_monte_carlo.json",
            "luxalgo_monte_carlo.stderr.txt",
            "payout_estimate.json",
        ],
        "warning": "Model outputs are conditional simulations, not predictions or guarantees.",
    }
    (output / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"rule_summary": rule_summary, "payout": payout, "output_dir": str(output)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the custom rule engine and LuxAlgo Monte Carlo.")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--trade-log", required=True)
    parser.add_argument("--equity-events", required=True)
    parser.add_argument("--output-dir", default="prop_firm_lab/outputs")
    args = parser.parse_args()
    result = run(args)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
