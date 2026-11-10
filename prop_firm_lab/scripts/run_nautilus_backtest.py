from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path


def resolve_callable(entrypoint: str):
    if ":" not in entrypoint:
        raise ValueError("strategy_entrypoint must look like 'package.module:function_name'")
    module_name, function_name = entrypoint.split(":", 1)
    module = importlib.import_module(module_name)
    function = getattr(module, function_name, None)
    if not callable(function):
        raise TypeError(f"{entrypoint} does not resolve to a callable")
    return function


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a user strategy adapter with NautilusTrader.")
    parser.add_argument("--request", default="prop_firm_lab/requests/current_run.json")
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))

    if not request.get("strategy_entrypoint"):
        raise SystemExit("No strategy_entrypoint configured. Create a strategy adapter before full research.")
    if not request.get("data_path"):
        raise SystemExit("No data_path configured.")

    import nautilus_trader
    version = getattr(nautilus_trader, "__version__", "unknown")
    if not str(version).startswith("2."):
        raise SystemExit(f"NautilusTrader 2.x required; installed version is {version}")

    config_path = Path(request["strategy_config_path"])
    if not config_path.exists():
        raise SystemExit(f"Strategy config not found: {config_path}")
    strategy_config = json.loads(config_path.read_text(encoding="utf-8"))
    output_dir = Path(request.get("output_dir", "prop_firm_lab/outputs")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    adapter = resolve_callable(request["strategy_entrypoint"])
    result = adapter(
        data_path=str(Path(request["data_path"]).resolve()),
        output_dir=str(output_dir),
        config=strategy_config,
    )
    if not isinstance(result, dict):
        raise TypeError("Strategy adapter must return a dict with trade_log, equity_events, and data_granularity")

    for key in ("trade_log", "equity_events", "data_granularity"):
        if key not in result:
            raise ValueError(f"Strategy adapter result missing {key!r}")
    for key in ("trade_log", "equity_events"):
        path = Path(result[key])
        if not path.is_absolute():
            path = output_dir / path
        if not path.exists():
            raise FileNotFoundError(f"Strategy adapter did not create {key}: {path}")
        request[key] = str(path)

    request["data_granularity"] = result["data_granularity"]
    (output_dir / "nautilus_backtest_manifest.json").write_text(
        json.dumps({
            "nautilus_version": version,
            "strategy_entrypoint": request["strategy_entrypoint"],
            "data_path": request["data_path"],
            "strategy_config_path": request["strategy_config_path"],
            "strategy_result": result,
            "note": "The adapter must construct and run NautilusTrader BacktestEngine or BacktestNode.",
        }, indent=2),
        encoding="utf-8",
    )
    Path(args.request).write_text(json.dumps(request, indent=2), encoding="utf-8")
    print(json.dumps({"nautilus_version": version, "result": result}, indent=2))


if __name__ == "__main__":
    main()
