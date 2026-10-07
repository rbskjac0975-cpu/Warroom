"""
Before the Noise - core engine (data-source agnostic).

Input : 1-min candles DataFrame, DatetimeIndex (IST), columns open/high/low/close/volume,
        starting at 09:15.
Flow  : Layer1 (breadth + volume) -> Layer2 (ORB breakout, 1-min close) ->
        Layer3 (retest hold + re-expansion) -> CONFIRMED -> TradeManager trails SL.

Status values: NONE | WATCH | FAILED | CONFIRMED
 - WATCH     : Layer 1 passed, waiting for ORB / breakout / retest (use this at 9:16)
 - CONFIRMED : all 3 layers passed, entry/SL/targets filled, proof frozen
 - FAILED    : breakout closed back inside the range before confirmation
"""
from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd

ORB_MINUTES = 15  # 09:15-09:30 opening range


@dataclass(frozen=True)
class Signal:
    symbol: str
    status: str
    direction: str | None = None  # "LONG" / "SHORT"
    entry: float | None = None
    sl: float | None = None
    t1: float | None = None
    t2: float | None = None
    proof: dict = field(default_factory=dict)  # frozen at detect time


def market_bias(adv: int, dec: int, index_close: float, index_ema: float,
                index_vwap: float, min_ratio: float = 1.3) -> str:
    """Breadth + trend check. Returns BULL / BEAR / NEUTRAL."""
    if dec == 0 and adv == 0:
        return "NEUTRAL"
    if adv >= min_ratio * max(dec, 1) and index_close > index_ema and index_close > index_vwap:
        return "BULL"
    if dec >= min_ratio * max(adv, 1) and index_close < index_ema and index_close < index_vwap:
        return "BEAR"
    return "NEUTRAL"


def _mirror(df: pd.DataFrame) -> pd.DataFrame:
    """Flip prices so short logic can reuse the long logic."""
    m = df.copy()
    m["open"], m["close"] = -df["open"], -df["close"]
    m["high"], m["low"] = -df["low"], -df["high"]
    return m


def _long_scan(df: pd.DataFrame, avg_1m_vol: float, vol_min: float,
               buffer: float, retest_tol: float):
    """Layer 2 + 3 on long side. Returns (status, info dict in df's price space)."""
    orb = df.iloc[:ORB_MINUTES]
    level = float(orb["high"].max())
    orl = float(orb["low"].min())
    post = df.iloc[ORB_MINUTES:]
    info = {"orh": level, "orl": orl}

    # Layer 2: first 1-min close above ORH (+buffer) on healthy volume
    b = None
    for i in range(len(post)):
        c = post.iloc[i]
        if c["close"] > (level + abs(level) * buffer) and c["volume"] >= avg_1m_vol:
            b = i
            break
    if b is None:
        return "WATCH", info
    info["breakout_time"] = str(post.index[b])
    info["breakout_close"] = float(post.iloc[b]["close"])

    # Layer 3: pullback to level that holds (close >= level), then re-expansion
    r = None
    for i in range(b + 1, len(post)):
        c = post.iloc[i]
        if c["close"] < level:           # breakout failed
            return "FAILED", info
        if r is None:
            if c["low"] <= (level + abs(level) * retest_tol):
                r = i
                info["retest_time"] = str(post.index[i])
            continue
        if c["close"] > post.iloc[r]["high"]:
            info["confirm_time"] = str(post.index[i])
            info["entry"] = float(c["close"])
            info["swing_low"] = float(post.iloc[r:i + 1]["low"].min())
            info["confirm_pos"] = ORB_MINUTES + i
            return "CONFIRMED", info
    return "WATCH", info


def scan_symbol(symbol: str, df: pd.DataFrame, bias: str, avg_1m_vol: float,
                vol_ratio_min: float = 1.5, buffer: float = 0.001,
                retest_tol: float = 0.002, rr: tuple = (1.0, 2.0)) -> Signal:
    if df is None or len(df) == 0 or bias not in ("BULL", "BEAR") or avg_1m_vol <= 0:
        return Signal(symbol, "NONE")

    # Layer 1: breadth (bias) + volume surge on candles so far
    vol_ratio = float(df["volume"].mean() / avg_1m_vol)
    if vol_ratio < vol_ratio_min:
        return Signal(symbol, "NONE")

    direction = "LONG" if bias == "BULL" else "SHORT"
    proof = {"bias": bias, "vol_ratio": round(vol_ratio, 2),
             "layer1": True, "candles_seen": len(df)}

    if len(df) <= ORB_MINUTES:  # ORB not formed yet (e.g. 9:16 scan)
        return Signal(symbol, "WATCH", direction, proof=proof)

    work = df if direction == "LONG" else _mirror(df)
    status, info = _long_scan(work, avg_1m_vol, 1.0, buffer, retest_tol)
    sgn = 1 if direction == "LONG" else -1

    def back(x):  # convert price from work-space back to real price
        return round(sgn * x, 2)

    proof.update({k: v for k, v in info.items() if isinstance(v, str)})
    proof["orh"] = back(info["orh"]) if direction == "LONG" else back(info["orl"])
    proof["orl"] = back(info["orl"]) if direction == "LONG" else back(info["orh"])

    if status != "CONFIRMED":
        return Signal(symbol, status, direction, proof=proof)

    entry = back(info["entry"])
    sl = back(info["swing_low"]) - sgn * entry * 0.0005  # small cushion beyond swing
    risk = abs(entry - sl)
    t1, t2 = entry + sgn * rr[0] * risk, entry + sgn * rr[1] * risk
    snap = df.iloc[max(0, info["confirm_pos"] - 29): info["confirm_pos"] + 1]
    proof["layer2"] = True
    proof["layer3"] = True
    proof["chart_snapshot"] = [
        {"t": str(ts), "o": r.open, "h": r.high, "l": r.low, "c": r.close, "v": r.volume}
        for ts, r in snap.iterrows()
    ]
    return Signal(symbol, "CONFIRMED", direction, round(entry, 2), round(sl, 2),
                  round(t1, 2), round(t2, 2), proof)


class TradeManager:
    """Backend monitor: runs from entry until exit. Feed it every live price."""

    def __init__(self, sig: Signal):
        assert sig.status == "CONFIRMED"
        self.s = 1 if sig.direction == "LONG" else -1
        self.entry, self.sl, self.t1, self.t2 = sig.entry, sig.sl, sig.t1, sig.t2
        self.risk = abs(sig.entry - sig.sl)
        self.peak = self.s * sig.entry
        self.stage = 0
        self.closed = False

    def update(self, price: float) -> list[str]:
        if self.closed:
            return []
        ev, p = [], self.s * price
        self.peak = max(self.peak, p)
        if p <= self.s * self.sl:
            self.closed = True
            return ["EXIT_SL" if self.stage == 0 else "EXIT_TRAIL"]
        if self.stage < 1 and p >= self.s * self.t1:
            self.stage = 1
            ev.append("T1_HIT")
        if self.stage < 2 and p >= self.s * self.t2:
            self.stage = 2
            ev.append("T2_HIT")
        if self.stage >= 1:  # trail 1R behind peak, never worse than entry
            new_sl = max(self.s * self.entry, self.peak - self.risk)
            if new_sl > self.s * self.sl:
                self.sl = round(self.s * new_sl, 2)
                ev.append(f"SL_TRAIL:{self.sl}")
        return ev
