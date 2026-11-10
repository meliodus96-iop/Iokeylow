from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUEST = Path(os.getenv("RUN_REQUEST", ROOT / "requests/current_run.json"))
request = json.loads(REQUEST.read_text(encoding="utf-8"))

subprocess.run(
    [sys.executable, str(Path(__file__).with_name("run_nautilus_backtest.py")), "--request", str(REQUEST)],
    cwd=ROOT,
    check=True,
)

request = json.loads(REQUEST.read_text(encoding="utf-8"))
profile = request["profile_path"]
if not profile:
    raise SystemExit("profile_path is required")
trade_log = request.get("trade_log")
equity_events = request.get("equity_events")
if not trade_log or not equity_events:
    raise SystemExit("Nautilus adapter did not return trade_log and equity_events")

subprocess.run(
    [
        sys.executable, "-m", "propfirm_lab.pipeline",
        "--profile", str(profile),
        "--trade-log", str(trade_log),
        "--equity-events", str(equity_events),
        "--output-dir", str(request.get("output_dir", "prop_firm_lab/outputs")),
    ],
    cwd=ROOT,
    env={**os.environ, "PYTHONPATH": str(ROOT / "prop_firm_lab/src")},
    check=True,
)
