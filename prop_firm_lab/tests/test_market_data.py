from types import SimpleNamespace

import pytest

from propfirm_lab.market_data.fetch import normalize_aggregate, normalize_aggregates


def sample_bar(**overrides):
    values = {
        "timestamp": 1794000000000,
        "open": 100.0,
        "high": 105.0,
        "low": 98.0,
        "close": 103.0,
        "volume": 1234.0,
        "vwap": 102.0,
        "transactions": 42,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_normalize_aggregate_converts_timestamp_to_utc():
    bar = normalize_aggregate(sample_bar())
    assert bar["timestamp"].endswith("+00:00")
    assert bar["timestamp_ms"] == 1794000000000
    assert bar["open"] == 100.0
    assert bar["close"] == 103.0


def test_normalize_aggregate_accepts_raw_api_field_names():
    bar = normalize_aggregate(
        {"t": 1794000000000, "o": 100, "h": 105, "l": 98, "c": 103, "v": 12}
    )
    assert bar["volume"] == 12.0
    assert bar["vwap"] == ""
    assert bar["transactions"] == ""


def test_rejects_invalid_ohlc():
    with pytest.raises(ValueError, match="high is inconsistent"):
        normalize_aggregate(sample_bar(high=99.0))


def test_rejects_duplicate_candle_timestamps():
    with pytest.raises(ValueError, match="Duplicate candle timestamps"):
        normalize_aggregates([sample_bar(), sample_bar()])


def test_rejects_empty_dataset():
    with pytest.raises(ValueError, match="zero aggregate bars"):
        normalize_aggregates([])
