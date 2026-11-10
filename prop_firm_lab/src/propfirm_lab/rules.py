from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


class ProfileError(ValueError):
    """Raised when a prop-firm rules profile is incomplete or unverified."""


def _as_float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ProfileError(f"{field} must be numeric; got {value!r}") from exc
    if number < 0:
        raise ProfileError(f"{field} must be non-negative")
    return number


def _limit_amount(rule: dict[str, Any], initial_balance: float, anchor: float | None = None) -> float:
    value = _as_float(rule.get("amount"), "loss-rule amount")
    amount_type = rule.get("amount_type", "fixed")
    if amount_type == "fixed":
        return value
    if amount_type == "pct_of_initial":
        return initial_balance * value / 100.0
    if amount_type == "pct_of_anchor":
        if anchor is None:
            raise ProfileError("pct_of_anchor requires an anchor")
        return anchor * value / 100.0
    raise ProfileError(f"Unsupported amount_type: {amount_type}")


@dataclass(frozen=True)
class EquityEvent:
    timestamp: datetime
    balance: float
    equity: float
    event_type: str

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "EquityEvent":
        raw_ts = str(row.get("timestamp", "")).strip()
        if not raw_ts:
            raise ValueError("equity_events.csv has an empty timestamp")
        ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            raise ValueError(f"Timestamp must include a UTC offset: {raw_ts}")
        balance = float(row["balance"])
        equity = float(row["equity"])
        if not math.isfinite(balance) or not math.isfinite(equity):
            raise ValueError("balance and equity must be finite numbers")
        kind = str(row.get("event_type", "mark")).strip().lower()
        if kind not in {"mark", "trade_close", "day_end"}:
            raise ValueError(f"Unsupported event_type: {kind}")
        return cls(ts, balance, equity, kind)


class PropFirmRuleEngine:
    """Replay timestamped account equity against an explicitly configured rule profile.

    The engine is intentionally event-driven. It does not invent intratrade equity
    marks from OHLC bars. The fidelity of the result is bounded by the input series.
    """

    def __init__(self, profile: dict[str, Any]) -> None:
        self.profile = profile
        self.account = profile["account"]
        self.initial = _as_float(self.account.get("initial_balance"), "account.initial_balance")
        if self.initial <= 0:
            raise ProfileError("account.initial_balance must be greater than zero")
        self.currency = self.account.get("currency", "USD")
        self.session = profile["session"]
        timezone_name = self.session.get("timezone")
        if not timezone_name:
            raise ProfileError("session.timezone is required")
        self.timezone = ZoneInfo(timezone_name)
        self.reset_time = time.fromisoformat(self.session.get("reset_time", "00:00"))
        self.overall = profile["overall_loss"]
        self.daily = profile.get("daily_loss")
        self._validate_rules()

        self.balance = self.initial
        self.equity = self.initial
        self.peak_intraday_equity = self.initial
        self.peak_eod_balance = self.initial
        self.day_anchor_balance = self.initial
        self.day_anchor_equity = self.initial
        self.session_day: str | None = None
        self.day_profit = 0.0
        self.best_day_profit = 0.0
        self.trading_days: set[str] = set()
        self.winning_days: set[str] = set()
        self.breach: dict[str, Any] | None = None
        self.ledger: list[dict[str, Any]] = []

    def _validate_rules(self) -> None:
        valid_modes = {
            "static_initial",
            "trailing_eod_balance",
            "trailing_intraday_equity",
            "trailing_intraday_equity_lock_initial",
        }
        if self.overall.get("mode") not in valid_modes:
            raise ProfileError(f"overall_loss.mode must be one of {sorted(valid_modes)}")
        overall_amount_type = self.overall.get("amount_type", "fixed")
        if overall_amount_type not in {"fixed", "pct_of_initial"}:
            raise ProfileError("overall_loss.amount_type must be fixed or pct_of_initial")
        _limit_amount(self.overall, self.initial)
        overall_metric = self.overall.get("metric", "equity")
        if overall_metric not in {"equity", "balance"}:
            raise ProfileError("overall_loss.metric must be equity or balance")
        if self.overall["mode"] in {"trailing_intraday_equity", "trailing_intraday_equity_lock_initial"} and overall_metric != "equity":
            raise ProfileError("Intraday equity-trailing modes require overall_loss.metric='equity'")
        if self.overall["mode"] == "trailing_eod_balance" and overall_metric != "balance":
            raise ProfileError("trailing_eod_balance requires overall_loss.metric='balance'")
        if self.overall.get("evaluation", "intraday") not in {"intraday", "end_of_day"}:
            raise ProfileError("overall_loss.evaluation must be intraday or end_of_day")
        if self.daily is not None:
            if self.daily.get("anchor") not in {"prior_day_balance", "prior_day_equity"}:
                raise ProfileError("daily_loss.anchor must be prior_day_balance or prior_day_equity")
            if self.daily.get("evaluation") not in {"intraday", "end_of_day"}:
                raise ProfileError("daily_loss.evaluation must be intraday or end_of_day")
            if self.daily.get("amount_type") not in {"fixed", "pct_of_initial", "pct_of_anchor"}:
                raise ProfileError("Unsupported daily_loss.amount_type")
            _limit_amount(self.daily, self.initial, self.initial)

    def _session_key(self, timestamp: datetime) -> str:
        local = timestamp.astimezone(self.timezone)
        if local.timetz().replace(tzinfo=None) < self.reset_time:
            local = local - timedelta(days=1)
        return local.date().isoformat()

    def _overall_floor(self) -> float:
        amount = _limit_amount(self.overall, self.initial)
        mode = self.overall["mode"]
        if mode == "static_initial":
            return self.initial - amount
        if mode == "trailing_eod_balance":
            return self.peak_eod_balance - amount
        floor = self.peak_intraday_equity - amount
        if mode == "trailing_intraday_equity_lock_initial":
            return min(floor, self.initial)
        return floor

    def _daily_floor(self) -> float | None:
        if self.daily is None:
            return None
        anchor_name = self.daily["anchor"]
        anchor = self.day_anchor_balance if anchor_name == "prior_day_balance" else self.day_anchor_equity
        amount = _limit_amount(self.daily, self.initial, anchor)
        if self.daily["amount_type"] == "pct_of_initial":
            amount = self.initial * float(self.daily["amount"]) / 100.0
        return anchor - amount

    def _finalize_day(self) -> None:
        self.day_profit = self.balance - self.day_anchor_balance
        self.best_day_profit = max(self.best_day_profit, self.day_profit)
        if self.session_day is not None and self.day_profit > 0:
            self.winning_days.add(self.session_day)
        if self.overall["mode"] == "trailing_eod_balance":
            self.peak_eod_balance = max(self.peak_eod_balance, self.balance)

    def process(self, event: EquityEvent) -> dict[str, Any]:
        if self.breach is not None:
            return self._record(event, None, None, "already_breached")

        key = self._session_key(event.timestamp)
        if self.session_day is None:
            self.session_day = key
        elif key != self.session_day:
            self._finalize_day()
            self.day_anchor_balance = self.balance
            self.day_anchor_equity = self.equity
            self.day_profit = 0.0
            self.session_day = key

        self.balance = event.balance
        self.equity = event.equity
        if event.event_type == "trade_close":
            self.trading_days.add(key)
        if self.overall["mode"] in {"trailing_intraday_equity", "trailing_intraday_equity_lock_initial"}:
            self.peak_intraday_equity = max(self.peak_intraday_equity, self.equity)

        overall_floor = self._overall_floor()
        daily_floor = self._daily_floor()
        overall_value = self.equity if self.overall.get("metric", "equity") == "equity" else self.balance
        overall_check_due = (
            self.overall.get("evaluation", "intraday") == "intraday"
            or event.event_type == "day_end"
        )
        daily_check_due = (
            self.daily is not None
            and (self.daily["evaluation"] == "intraday" or event.event_type == "day_end")
        )
        daily_value = self.equity if self.daily and self.daily.get("includes_open_pnl", True) else self.balance

        reason = None
        if overall_check_due and overall_value <= overall_floor:
            reason = "overall_loss"
        if reason is None and daily_check_due and daily_floor is not None and daily_value <= daily_floor:
            reason = "daily_loss"

        if reason:
            self.breach = {
                "reason": reason,
                "timestamp": event.timestamp.isoformat(),
                "balance": self.balance,
                "equity": self.equity,
                "overall_floor": overall_floor,
                "daily_floor": daily_floor,
            }

        result = self._record(event, overall_floor, daily_floor, reason)
        if event.event_type == "day_end":
            self._finalize_day()
        return result

    def _record(
        self,
        event: EquityEvent,
        overall_floor: float | None,
        daily_floor: float | None,
        status: str | None,
    ) -> dict[str, Any]:
        row = {
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type,
            "balance": event.balance,
            "equity": event.equity,
            "overall_floor": overall_floor,
            "daily_floor": daily_floor,
            "status": status or "ok",
        }
        self.ledger.append(row)
        return row

    def run(self, events: list[EquityEvent]) -> dict[str, Any]:
        if not events:
            raise ValueError("No equity events supplied")
        ordered = sorted(events, key=lambda item: item.timestamp)
        if ordered != events:
            raise ValueError("Equity events must be sorted chronologically")
        for event in ordered:
            self.process(event)
            if self.breach is not None:
                break

        if self.session_day is not None and (not self.ledger or self.ledger[-1]["event_type"] != "day_end"):
            self._finalize_day()
        target_pct = self.profile.get("target", {}).get("profit_target_pct")
        min_days = int(self.profile.get("target", {}).get("minimum_trading_days", 0) or 0)
        consistency = self.profile.get("target", {}).get("consistency_max_best_day_pct")
        profit = self.balance - self.initial
        target_hit = target_pct is not None and self.balance >= self.initial * (1 + float(target_pct) / 100)
        consistency_ok = True
        if consistency is not None and profit > 0:
            consistency_ok = (self.best_day_profit / profit * 100) <= float(consistency)
        pass_ready = (
            self.breach is None
            and bool(target_hit)
            and len(self.trading_days) >= min_days
            and consistency_ok
        )
        return {
            "profile_id": self.profile.get("profile_id"),
            "initial_balance": self.initial,
            "final_balance": self.balance,
            "final_equity": self.equity,
            "net_profit": profit,
            "trading_days": len(self.trading_days),
            "winning_days": len(self.winning_days),
            "best_day_profit": self.best_day_profit,
            "target_hit": bool(target_hit),
            "minimum_days_met": len(self.trading_days) >= min_days,
            "consistency_ok": consistency_ok,
            "pass_ready": pass_ready,
            "breach": self.breach,
            "events_processed": len(self.ledger),
            "overall_loss_mode": self.overall["mode"],
            "evidence_granularity_warning": (
                "Rule checks are only as precise as the supplied equity_events timestamps. "
                "Bar marks cannot establish true tick-level intratrade breaches."
            ),
        }


def load_profile(path: str | Path, *, require_verified: bool = True) -> dict[str, Any]:
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    verification = profile.get("verification", {})
    if require_verified:
        if verification.get("status") != "verified":
            raise ProfileError("Research mode requires verification.status='verified'")
        if not verification.get("last_verified_utc") or not verification.get("official_source_urls"):
            raise ProfileError("Verified profiles require last_verified_utc and official_source_urls")
    return profile


def read_equity_events(path: str | Path) -> list[EquityEvent]:
    with Path(path).open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"timestamp", "balance", "equity", "event_type"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"equity_events.csv missing columns: {sorted(missing)}")
        return [EquityEvent.from_mapping(row) for row in reader]


def calculate_payout(
    profile: dict[str, Any],
    *,
    balance: float,
    equity: float,
    current_overall_floor: float,
    winning_days: int = 0,
) -> dict[str, Any]:
    """Estimate a permitted gross withdrawal and trader reward under configured payout limits.

    This is a transparent calculator, not a substitute for the firm's payout contract.
    """
    payout = profile.get("payout", {})
    split = payout.get("profit_split_pct")
    if split is None:
        raise ProfileError("payout.profit_split_pct is required for payout calculation")
    split = float(split)
    if not 0 <= split <= 100:
        raise ProfileError("payout.profit_split_pct must be between 0 and 100")
    minimum_winning_days = int(payout.get("minimum_winning_days", 0) or 0)
    if winning_days < minimum_winning_days:
        return {
            "eligible": False,
            "reason": "minimum_winning_days_not_met",
            "winning_days": winning_days,
            "required_winning_days": minimum_winning_days,
            "gross_withdrawal": 0.0,
            "trader_reward": 0.0,
        }
    initial = float(profile["account"]["initial_balance"])
    buffer = float(payout.get("profit_buffer", 0) or 0)
    if balance <= initial + buffer:
        return {"eligible": False, "reason": "profit_buffer_not_met", "gross_withdrawal": 0.0, "trader_reward": 0.0}
    if equity <= current_overall_floor:
        return {"eligible": False, "reason": "account_at_or_below_loss_floor", "gross_withdrawal": 0.0, "trader_reward": 0.0}

    available = max(0.0, min(balance, equity) - initial - buffer)
    cap_pct = payout.get("withdrawal_cap_pct_of_profit")
    if cap_pct is not None:
        available = min(available, max(0.0, balance - initial) * float(cap_pct) / 100.0)
    hard_cap = payout.get("maximum_gross_payout")
    if hard_cap is not None:
        available = min(available, float(hard_cap))
    safe_withdrawal = max(0.0, min(available, min(balance, equity) - current_overall_floor))
    return {
        "eligible": safe_withdrawal > 0,
        "gross_withdrawal": safe_withdrawal,
        "profit_split_pct": split,
        "trader_reward": safe_withdrawal * split / 100.0,
        "firm_share": safe_withdrawal * (100.0 - split) / 100.0,
        "post_withdrawal_balance_estimate": balance - safe_withdrawal,
        "post_withdrawal_equity_estimate": equity - safe_withdrawal,
        "floor_after_withdrawal_estimate": current_overall_floor,
        "note": "Verify whether the firm recalculates its drawdown anchor after withdrawals.",
    }
