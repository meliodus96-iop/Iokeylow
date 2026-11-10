#!/usr/bin/env python3
"""Verify the free market-data Python runtime imports cleanly."""

from __future__ import annotations

import importlib.metadata
import sys


EXPECTED = {
    "nautilus_trader": "1.231.0",
    "ccxt": "4.5.92",
}


def main() -> int:
    if sys.version_info < (3, 12) or sys.version_info >= (3, 15):
        print("ERROR: use Python 3.12, 3.13 or 3.14.", file=sys.stderr)
        return 2

    try:
        import ccxt  # noqa: F401
        import nautilus_trader  # noqa: F401
    except Exception as exc:
        print(f"ERROR: market-data runtime import failed: {exc!r}", file=sys.stderr)
        return 1

    for distribution, expected in EXPECTED.items():
        try:
            actual = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            print(f"ERROR: missing distribution {distribution}", file=sys.stderr)
            return 1
        if actual != expected:
            print(
                f"ERROR: {distribution} version {actual}; expected {expected}",
                file=sys.stderr,
            )
            return 1

    print("OK: free market-data Python runtime installed and importable")
    for package, version in EXPECTED.items():
        print(f"  {package}=={version}")
    print("OK: CCXT public market-data client is available; no API key was used")
    print("NOTE: this is an import smoke test; it does not prove a live feed or history download")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
