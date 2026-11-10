#!/usr/bin/env python3
"""Validate the repository's market-data provider manifest (stdlib only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "market_data" / "providers.json"

FORBIDDEN_KEY_PARTS = (
    "api_key",
    "apikey",
    "secret",
    "password",
    "private_key",
    "access_token",
    "refresh_token",
)


def walk(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f"{path}[{index}]")
    else:
        yield path, value


def main() -> int:
    try:
        document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"ERROR: manifest not found: {MANIFEST}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}", file=sys.stderr)
        return 2

    errors: list[str] = []

    if document.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if document.get("mode") != "research_only":
        errors.append("mode must remain research_only until a separate live-execution review")
    if not isinstance(document.get("engine"), dict):
        errors.append("engine must be an object")
    else:
        engine = document["engine"]
        for field in ("name", "repository", "version", "python", "role"):
            if field not in engine:
                errors.append(f"engine.{field} is required")
        if engine.get("name") != "NautilusTrader":
            errors.append("NautilusTrader must remain the single canonical engine in this manifest")
    providers = document.get("providers")
    if not isinstance(providers, dict) or not providers:
        errors.append("providers must be a non-empty object")

    if not isinstance(document.get("analytics"), dict):
        errors.append("analytics must be an object")
    if document.get("security", {}).get("commit_credentials") is not False:
        errors.append("security.commit_credentials must be false")
    if document.get("security", {}).get("default_execution_enabled") is not False:
        errors.append("security.default_execution_enabled must be false")

    for path, value in walk(document):
        key = path.rsplit(".", 1)[-1].lower()
        if any(part in key for part in FORBIDDEN_KEY_PARTS):
            errors.append(f"possible credential field is forbidden in manifest: {path}")
        if isinstance(value, str) and value.strip().lower() in {"changeme", "your_api_key", "replace_me"}:
            errors.append(f"placeholder credential-like value is forbidden: {path}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    assets = ", ".join(providers.keys())
    print(f"OK: market-data manifest valid; provider families: {assets}")
    print("OK: research-only mode; no credentials; live execution disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
