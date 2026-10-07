"""Leaders (3 tiers + option strike), Trend Ignition, Pre-Open Gaps, War Room replay."""
import pandas as pd
from engine import ORB_MINUTES, TradeManager

TIER_RANK = {"EXPLOSIVE": 0, "STRONG": 1, "SPURT": 2}


def _step(p):
    return 5 if p < 250 else 10 if p < 1000 else 20 if p < 2000 else 50 if p < 5000 else 100


def leaders(stocks, bias, sigs, min_avg_vol=500, vol_min=1.5, t_exp=60, t_str=40, t_spu=25):
    rows = []
    for s, (df, avg) in stocks.items():
        if avg < min_avg_vol or len(df) < 2:      # illiquid -> removed
            continue
        o, ltp = float(df["open"].iloc[0]), float(df["close"].iloc[-1])
        mv, vr = (ltp / o - 1) * 100, float(df["volume"].mean() / avg)
        d = 1 if mv >= 0 else -1
        if (bias == "BULL" and d < 0) or (bias == "BEAR" and d > 0) or bias == "NEUTRAL":
            continue
        if vr < vol_min or abs(mv) > 4:           # junk / late entry -> removed
            continue
        orh, orl = float(df["high"].iloc[:ORB_MINUTES].max()), float(df["low"].iloc[:ORB_MINUTES].min())
        brk = sigs[s].status == "CONFIRMED" or (len(df) > ORB_MINUTES and (ltp > orh if d > 0 else ltp < orl))
        score = round(vr * 10 + abs(mv) * 15 + (15 if brk else 0), 1)
        tier = "EXPLOSIVE" if score >= t_exp else "STRONG" if score >= t_str else "SPURT" if score >= t_spu else None
        if not tier:
            continue
        m = (df["volume"] >= vol_min * avg) & ((df["close"] - o) * d > 0)
        det = df.index[m.values][0] if m.any() else df.index[-1]
        st = _step(ltp)
        c0, pc = df.iloc[0], df.attrs.get("prev_close")
        bd, rg = abs(float(c0["close"] - c0["open"])), (float(c0["high"] - c0["low"]) or 1e-9)
        rows.append(dict(symbol=s, tier=tier, score=score, dir="LONG" if d > 0 else "SHORT", vol_ratio=round(vr, 2),
                         move=round(mv, 2), ltp=round(ltp, 2), detect=det, orb_level=round(orh if d > 0 else orl, 2),
                         sl_area=round(orl if d > 0 else orh, 2),
                         strike=f"{round(ltp / st) * st:g} {'CE' if d > 0 else 'PE'}", brk=brk,
                         gap=round((o / pc - 1) * 100, 2) if pc else 0.0, body=round(bd / o * 100, 2),
                         cand="Strong" if bd / rg > 0.7 else "Moderate" if bd / rg > 0.4 else "Weak",
                         from_low=round((ltp / float(df["low"].min()) - 1) * 100, 2),
                         from_high=round((ltp / float(df["high"].max()) - 1) * 100, 2)))
    return sorted(rows, key=lambda r: (TIER_RANK[r["tier"]], -r["score"]))


def ignition(stocks, flat_pct=0.4):
    """Opens at day's low (high) and never looks back. Entry = candle right after the extreme."""
    rows = []
    for s, (df, avg) in stocks.items():
        if len(df) < 5:
            continue
        o, ltp = float(df["open"].iloc[0]), float(df["close"].iloc[-1])
        lo, hi = int(df["low"].values.argmin()), int(df["high"].values.argmax())
        for d, ext in ((1, lo), (-1, hi)):
            if ext <= 2 and (ltp / o - 1) * 100 * d >= flat_pct:
                i = min(ext + 1, len(df) - 1)
                rows.append(dict(symbol=s, dir="LONG" if d > 0 else "SHORT", time=df.index[i],
                                 entry=round(float(df["close"].iloc[i]), 2), ltp=round(ltp, 2),
                                 move=round((ltp / o - 1) * 100, 2)))
    return sorted(rows, key=lambda r: r["time"], reverse=True)   # newest on top


def gaps(stocks):
    """Gap frozen at the 09:15 bell (first candle open vs previous close) + trap flags."""
    rows = []
    for s, (df, _) in stocks.items():
        pc = df.attrs.get("prev_close")
        if not pc:
            continue
        o, ltp = float(df["open"].iloc[0]), float(df["close"].iloc[-1])
        g = (o / pc - 1) * 100
        trap = "LONG TRAP" if g > 0.3 and ltp < o else "SHORT TRAP" if g < -0.3 and ltp > o else ""
        rows.append(dict(symbol=s, gap=round(g, 2), open=round(o, 2), ltp=round(ltp, 2),
                         now=round((ltp / pc - 1) * 100, 2), trap=trap))
    return rows


def replay(sig, df):
    """Walk candles after entry: trailing SL line + exit point (for War Room arrows)."""
    t0 = pd.Timestamp(sig.proof["confirm_time"])
    pos = df.index.get_loc(t0)
    tm, trail, exit_pt = TradeManager(sig), [], None
    for ts, c in df.iloc[pos + 1:].iterrows():
        worst, best = (c["low"], c["high"]) if sig.direction == "LONG" else (c["high"], c["low"])
        ev = tm.update(float(worst)) + (tm.update(float(best)) if not tm.closed else [])
        trail.append((ts, tm.sl))
        if tm.closed:
            exit_pt = (ts, tm.sl)
            break
    return t0, trail, exit_pt
