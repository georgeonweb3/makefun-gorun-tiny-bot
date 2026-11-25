"""Laggard ladder bot for agent-fun/bars-replay/v1.

What the data says (dev window, 136 hourly bars of 7 Solana assets):
  * Returns are NEGATIVELY autocorrelated at every horizon (corr -0.20 at
    12 bars, -0.50 at 24 bars): past winners keep falling, past losers
    bounce. Momentum and trend baselines all lose; the best house baseline
    (MACD-CCI, -$20) is near flat and buy-and-hold loses -$869.
  * Buying the biggest 12-bar losers once and holding beats buy-and-hold
    on down windows (+$161 mean margin) and captures most of its gain on
    up windows (bot3-ret12: +$204 vs buy-and-hold +$267 on reversed data).
  * Frequent trading loses to fees + 1-bar latency + noise, so this bot
    trades in tranches instead of rebalancing: scale INTO dips and scale
    OUT of bounces.

Rules, per symbol:
  * Tranche 1 (12.5% of equity): the symbol is among the 3 biggest
    12-bar losers and oversold vs its 24-bar mean (z <= -1), the universe
    is not crashing (equal-weight 24-bar return above -8%). In a rising
    universe (equal-weight 12-bar return above +1%) the z-gate is skipped
    — prices sit ~2 SD above their mean in a rally, so rank alone decides
    — and a 4th symbol is allowed (100% invested).
  * Tranche 2 (another 12.5%): the dip deepens (z <= -2) while only
    tranche 1 is held — average down where the bounce is strongest.
  * Sell half: reverted to the mean (z >= 0) — but NOT while the universe
    is rising (equal-weight 12-bar return above +1%): then winners ride
    under a trailing stop instead of being sold into strength.
  * Sell the rest: z >= +0.75, or +4% / -6% vs average entry, or 36 bars,
    or 5% below the peak since entry (trailing stop).
  * Crash brake: universe 24-bar return below -8% sells everything;
    portfolio drawdown guard (6% off peak) does the same.
  * Buys capped at 3% slippage, sells wide open.

Deterministic: pure float math in universe order, no clock, no
randomness, no environment, no network. Same bars -> same orders.
"""

LOOKBACK_RET = 12
LOOKBACK_Z = 24
Z1 = -1.0
Z2 = -2.0
Z_SELL_HALF = 0.0
Z_SELL_REST = 0.75
MAX_FALL_24 = -0.08
TAKE_PROFIT = 0.04
HARD_STOP = 0.06
TRAIL_STOP = 0.05
UP_UNI_12 = 0.01
TOP_N_UP = 4          # in a rising universe, hold a 4th symbol (100% invested)
MAX_HOLD_BARS = 36
TOP_N = 3
TRANCHE_BPS = 1250
COOLDOWN_BARS = 6
DD_GUARD = 0.06
DD_PAUSE_BARS = 12
BUY_SLIPPAGE_BPS = 300
SELL_SLIPPAGE_BPS = 10000


class Bot:
    def __init__(self, **overrides):
        for k in ("LOOKBACK_RET", "LOOKBACK_Z", "Z1", "Z2", "Z_SELL_HALF",
                  "Z_SELL_REST", "MAX_FALL_24", "TAKE_PROFIT", "HARD_STOP",
                  "TRAIL_STOP", "UP_UNI_12",
                  "MAX_HOLD_BARS", "TOP_N", "TOP_N_UP", "TRANCHE_BPS", "COOLDOWN_BARS",
                  "DD_GUARD", "DD_PAUSE_BARS", "BUY_SLIPPAGE_BPS",
                  "SELL_SLIPPAGE_BPS"):
            setattr(self, k, globals()[k])
        for k, v in overrides.items():
            setattr(self, k, v)
        self.closes = {}
        self.entry_close = {}   # symbol -> volume-weighted avg entry close
        self.peak = {}          # symbol -> highest close since entry
        self.entry_bar = {}
        self.tranches = {}      # symbol -> 1 or 2
        self.half_sold = {}     # symbol -> bool
        self.cooldown_until = {}
        self.equity_peak = 0
        self.pause_until = -1

    def _ret(self, symbol, n):
        hist = self.closes.get(symbol) or []
        if len(hist) <= n:
            return None
        then = hist[-1 - n]
        if then <= 0:
            return None
        return hist[-1] / then - 1.0

    def _z(self, symbol):
        hist = self.closes.get(symbol) or []
        if len(hist) < self.LOOKBACK_Z:
            return None
        w = hist[-self.LOOKBACK_Z:]
        mean = sum(w) / self.LOOKBACK_Z
        var = sum((x - mean) ** 2 for x in w) / self.LOOKBACK_Z
        sd = var ** 0.5
        if sd <= 0:
            return None
        return (w[-1] - mean) / sd

    def _uni_ret(self, n):
        rs = [self._ret(s, n) for s in self.closes]
        rs = [r for r in rs if r is not None]
        return sum(rs) / len(rs) if rs else None

    def _flatten(self, state, orders, seq):
        for s, h in dict(state.positions).items():
            orders.append({"side": "sell", "symbol": s, "qty": h.qty,
                           "max_slippage_bps": self.SELL_SLIPPAGE_BPS})
            self.cooldown_until[s] = seq + self.COOLDOWN_BARS
            self.entry_close.pop(s, None)
            self.entry_bar.pop(s, None)
            self.tranches.pop(s, None)
            self.half_sold.pop(s, None)
            self.peak.pop(s, None)

    def on_batch(self, state, batch):
        for sym in state.hello["symbols"]:
            s = sym["symbol"]
            c = state.close(s)
            hist = self.closes.setdefault(s, [])
            hist.append(float(c) if c is not None else None)
        if state.warming_up:
            return []
        seq = state.seq
        orders = []
        held = dict(state.positions)

        if state.equity > self.equity_peak:
            self.equity_peak = state.equity
        # guards: portfolio drawdown, or universe crash
        uni24 = self._uni_ret(self.LOOKBACK_Z)
        if (self.equity_peak > 0
                and state.equity <= self.equity_peak * (1.0 - self.DD_GUARD)) or (
                uni24 is not None and uni24 < self.MAX_FALL_24):
            self.pause_until = seq + self.DD_PAUSE_BARS
            self._flatten(state, orders, seq)
            return orders

        universe = [sym["symbol"] for sym in state.hello["symbols"]]
        # exits / scale-outs; in a rising universe winners ride (trailing
        # stop only), elsewhere take profits on reversion.
        uni12 = self._uni_ret(self.LOOKBACK_RET)
        up_regime = uni12 is not None and uni12 > self.UP_UNI_12
        for s, h in held.items():
            c = state.close(s)
            if c is None:
                continue
            if c > self.peak.get(s, 0):
                self.peak[s] = c
            z = self._z(s)
            sell_qty = 0
            reason = None
            if s in self.entry_close and c <= self.entry_close[s] * (1.0 - self.HARD_STOP):
                sell_qty = h.qty
                reason = "stop"
            elif s in self.entry_bar and seq - self.entry_bar[s] >= self.MAX_HOLD_BARS:
                sell_qty = h.qty
                reason = "time"
            elif (not up_regime and s in self.entry_close
                    and c >= self.entry_close[s] * (1.0 + self.TAKE_PROFIT)):
                sell_qty = h.qty
                reason = "tp"
            elif not up_regime and z is not None and z >= self.Z_SELL_REST:
                sell_qty = h.qty
                reason = "revert"
            elif (up_regime and self.peak.get(s) is not None
                    and c <= self.peak[s] * (1.0 - self.TRAIL_STOP)):
                sell_qty = h.qty
                reason = "trail"
            elif (not up_regime and z is not None and z >= self.Z_SELL_HALF
                    and not self.half_sold.get(s) and self.tranches.get(s, 0) >= 1):
                sell_qty = h.qty // 2
                reason = "half"
            if sell_qty > 0:
                orders.append({"side": "sell", "symbol": s, "qty": int(sell_qty),
                               "max_slippage_bps": self.SELL_SLIPPAGE_BPS})
                if reason == "half":
                    self.half_sold[s] = True
                else:
                    self.cooldown_until[s] = seq + self.COOLDOWN_BARS
                    self.entry_close.pop(s, None)
                    self.entry_bar.pop(s, None)
                    self.tranches.pop(s, None)
                    self.half_sold.pop(s, None)
                    self.peak.pop(s, None)

        # entries
        if seq < self.pause_until:
            return orders
        sold_now = {o["symbol"] for o in orders if o["side"] == "sell"}
        still_held = {s for s in held if s not in sold_now}
        up_now = uni12 is not None and uni12 > self.UP_UNI_12
        top_n = self.TOP_N_UP if up_now else self.TOP_N
        # rank by 12-bar return, worst first
        ranked = []
        for i, s in enumerate(universe):
            r = self._ret(s, self.LOOKBACK_RET)
            ranked.append(((r if r is not None else 9e9), i, s))
        ranked.sort()
        laggards = [s for _, _, s in ranked[:top_n]]
        cash_left = state.cash
        for s in universe:
            if s in held:
                # tranche 2: dip deepened while only tranche 1 held
                if (self.tranches.get(s) == 1 and not self.half_sold.get(s)
                        and s not in sold_now):
                    z = self._z(s)
                    if z is not None and z <= self.Z2:
                        amount = min(self.TRANCHE_BPS * state.equity // 10000, cash_left)
                        if amount >= int(state.hello["fees"]["min_notional_quote_units"]):
                            orders.append({"side": "buy", "symbol": s,
                                           "notional_quote_units": int(amount),
                                           "max_slippage_bps": self.BUY_SLIPPAGE_BPS})
                            cash_left -= int(amount)
                            c = state.close(s)
                            old = self.entry_close.get(s, float(c))
                            self.entry_close[s] = (old + float(c)) / 2.0
                            self.tranches[s] = 2
                continue
            # tranche 1: a laggard, oversold, slot free, not cooling down
            if len(still_held) >= top_n:
                continue
            if s not in laggards:
                continue
            if seq < self.cooldown_until.get(s, -1):
                continue
            # in a rising universe the z-gate never opens (prices sit ~2 SD
            # above their mean), so rank alone decides; otherwise require a dip.
            # Either way the 24-bar mean must exist (no entries before bar 24).
            z = self._z(s)
            if z is None:
                continue
            if not up_now and z > self.Z1:
                continue
            amount = min(self.TRANCHE_BPS * state.equity // 10000, cash_left)
            if amount < int(state.hello["fees"]["min_notional_quote_units"]):
                continue
            orders.append({"side": "buy", "symbol": s,
                           "notional_quote_units": int(amount),
                           "max_slippage_bps": self.BUY_SLIPPAGE_BPS})
            cash_left -= int(amount)
            c = state.close(s)
            self.entry_close[s] = float(c)
            self.entry_bar[s] = seq
            self.tranches[s] = 1
            self.half_sold[s] = False
            self.peak[s] = float(c)
            still_held.add(s)
        return orders
