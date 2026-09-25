from collections import deque
from statistics import median
from bhav.engine.strategy import Context, Strategy

class NiftyPhase1Public(Strategy):
    name = "nifty_phase1_public_proxy"

    def __init__(self):
        self.bars = deque(maxlen=120)
        self.day_high = None
        self.day_low = None
        self.prev_day_high = None
        self.prev_day_low = None
        self.opening_high = None
        self.opening_low = None
        self.opening_done = False
        self.traded_today = False
        self.position_key = None
        self.entry_premium = None
        self.stop_premium = None
        self.target_premium = None
        self.entry_time = None

    def on_day_start(self, ctx: Context) -> None:
        if self.day_high is not None and self.day_low is not None:
            self.prev_day_high = self.day_high
            self.prev_day_low = self.day_low
        self.day_high = None
        self.day_low = None
        self.opening_high = None
        self.opening_low = None
        self.opening_done = False
        self.traded_today = False
        self.position_key = None
        self.entry_premium = None
        self.stop_premium = None
        self.target_premium = None
        self.entry_time = None
        self.bars.clear()

    def _hhmm(self, ctx):
        return f"{ctx.bar.timestamp.hour:02d}:{ctx.bar.timestamp.minute:02d}"

    def _range_median(self):
        rs = [float(b.high - b.low) for b in list(self.bars)[-30:]]
        rs = [x for x in rs if x > 0]
        return median(rs) if rs else None

    def _current_option_price(self, ctx):
        if not self.position_key:
            return None
        rows = ctx.reader.option_bars(self.position_key, ctx.date)
        row = rows.filter(rows["timestamp"] == ctx.bar.timestamp)
        if row.is_empty():
            return None
        return float(row["close"][0])

    def _enter(self, ctx, side):
        if self.position_key or self.traded_today:
            return
        opt = "CE" if side == "LONG" else "PE"
        key = ctx.buy_option(option_type=opt, strike_offset=0, lots=1)
        if not key:
            return
        pos = ctx.portfolio.positions.get(key)
        if not pos:
            return
        self.position_key = key
        self.entry_premium = float(pos.avg_price)
        self.stop_premium = self.entry_premium * 0.6666666667
        self.target_premium = self.entry_premium * 3.0
        self.entry_time = ctx.bar.timestamp
        self.traded_today = True

    def on_bar(self, ctx: Context) -> None:
        ts = ctx.bar.timestamp
        p = float(ctx.bar.close)
        self.bars.append(ctx.bar)

        self.day_high = p if self.day_high is None else max(self.day_high, float(ctx.bar.high))
        self.day_low = p if self.day_low is None else min(self.day_low, float(ctx.bar.low))

        hhmm = self._hhmm(ctx)

        if "09:15" <= hhmm <= "09:29":
            self.opening_high = float(ctx.bar.high) if self.opening_high is None else max(self.opening_high, float(ctx.bar.high))
            self.opening_low = float(ctx.bar.low) if self.opening_low is None else min(self.opening_low, float(ctx.bar.low))
            return

        if hhmm >= "09:30":
            self.opening_done = True

        # Manage existing option position using only the option bar available
        # at this same timestamp.
        if self.position_key:
            rows = ctx.reader.option_bars(self.position_key, ctx.date)
            row = rows.filter(rows["timestamp"] == ts)
            if not row.is_empty():
                hi = float(row["high"][0])
                lo = float(row["low"][0])
                # Worst-case ordering when both occur in one minute.
                if lo <= self.stop_premium:
                    ctx.close(self.position_key, reason="premium_sl")
                    self.position_key = None
                    return
                if hi >= self.target_premium:
                    ctx.close(self.position_key, reason="premium_3r")
                    self.position_key = None
                    return
            if hhmm >= "15:20":
                ctx.close(self.position_key, reason="time_exit")
                self.position_key = None
            return

        if not self.opening_done or self.traded_today or hhmm < "09:30" or hhmm > "14:45":
            return

        if len(self.bars) < 25 or self.prev_day_high is None or self.prev_day_low is None:
            return

        med = self._range_median()
        if not med or med <= 0:
            return

        b = list(self.bars)
        last = b[-1]
        prev = b[-2]

        last_range = float(last.high - last.low)
        if last_range <= 0:
            return

        body = abs(float(last.close - last.open))
        body_frac = body / last_range

        # Development-only price/volume proxy for participation:
        # abnormal range + strong directional body. This is NOT true order flow.
        strong_bull = last.close > last.open and last_range >= 1.30 * med and body_frac >= 0.60
        strong_bear = last.close < last.open and last_range >= 1.30 * med and body_frac >= 0.60

        # Failed-auction / absorption-style reversal at prior-day extremes.
        near_prev_low = float(last.low) <= self.prev_day_low + 0.35 * med
        near_prev_high = float(last.high) >= self.prev_day_high - 0.35 * med

        # Reclaim after an excursion beyond the prior-day extreme.
        bull_reclaim = (
            near_prev_low
            and float(last.close) > self.prev_day_low
            and float(prev.low) <= self.prev_day_low
        )
        bear_reclaim = (
            near_prev_high
            and float(last.close) < self.prev_day_high
            and float(prev.high) >= self.prev_day_high
        )

        # Opening-range continuation.
        bull_break = (
            self.opening_high is not None
            and last.close > self.opening_high
            and strong_bull
        )
        bear_break = (
            self.opening_low is not None
            and last.close < self.opening_low
            and strong_bear
        )

        # Require natural room for >= 2.5R to the opposite prior-day extreme.
        if bull_reclaim:
            risk = max(0.75 * med, float(last.close) - float(last.low))
            room = float(self.prev_day_high) - float(last.close)
            if room >= 2.5 * risk:
                self._enter(ctx, "LONG")
                return

        if bear_reclaim:
            risk = max(0.75 * med, float(last.high) - float(last.close))
            room = float(last.close) - float(self.prev_day_low)
            if room >= 2.5 * risk:
                self._enter(ctx, "SHORT")
                return

        if bull_break:
            risk = max(0.75 * med, float(last.close) - float(last.low))
            room = float(self.prev_day_high) - float(last.close)
            if room >= 2.5 * risk:
                self._enter(ctx, "LONG")
                return

        if bear_break:
            risk = max(0.75 * med, float(last.high) - float(last.close))
            room = float(last.close) - float(self.prev_day_low)
            if room >= 2.5 * risk:
                self._enter(ctx, "SHORT")

strategy = NiftyPhase1Public()
