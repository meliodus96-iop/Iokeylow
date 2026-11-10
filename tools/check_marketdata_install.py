#!/usr/bin/env python3
"""Verify the pinned multi-asset market-data runtime imports cleanly."""

from __future__ import annotations

import importlib.metadata
import sys

EXPECTED = {
    "nautilus_trader": "1.231.0",
    "databento": "0.90.0",
}


def main() -> int:
    if sys.version_info < (3, 12) or sys.version_info >= (3, 15):
        print(
            "ERROR: use Python 3.12, 3.13 or 3.14 for this pinned runtime.",
            file=sys.stderr,
        )
        return 2

    try:
        import nautilus_trader  # noqa: F401
        import databento  # noqa: F401
        from nautilus_trader.adapters.databento import (
            DatabentoDataClientConfig,
            DatabentoDataLoader,
        )
    except Exception as exc:  # import-time native dependency failures matter here
        print(f"ERROR: market-data runtime import failed: {exc!r}", file=sys.stderr)
        return 1

    actual: dict[str, str] = {}
    for distribution, expected in EXPECTED.items():
        try:
            version = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            print(f"ERROR: missing distribution {distribution}", file=sys.stderr)
            return 1
        actual[distribution] = version
        if version != expected:
            print(
                f"ERROR: {distribution} version {version}; expected {expected}",
                file=sys.stderr,
            )
            return 1

    # Verify the built-in Nautilus adapter surface is present, without making
    # any network request or requiring a Databento API key.
    if not callable(DatabentoDataClientConfig) or not callable(DatabentoDataLoader):
        print("ERROR: Databento adapter exports are unavailable.", file=sys.stderr)
        return 1

    print("OK: market-data runtime installed and importable")
    for package, version in actual.items():
        print(f"  {package}=={version}")
    print("OK: NautilusTrader built-in Databento adapter exports are present")
    print("NOTE: this is an import smoke test; no exchange feed or API key was used")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
