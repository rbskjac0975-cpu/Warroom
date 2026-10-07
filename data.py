"""Data layer: live (yfinance, delayed) and demo. Swap fetch_live for a broker feed later."""
import numpy as np
import pandas as pd

IST = "Asia/Kolkata"
COLS = ["open", "high", "low", "close", "volume"]
INDEX_KEYS = ["^NSEI", "^NSEBANK", "^BSESN"]  # NIFTY, BANKNIFTY, SENSEX


def fetch_live(symbols):
    """Returns {symbol: (today_1min_df, avg_1m_vol)} incl. '^NSEI'. yfinance is delayed."""
    import yfinance as yf
    tick = [s + ".NS" for s in symbols] + INDEX_KEYS
    raw = yf.download(tick, period="5d", interval="1m", group_by="ticker",
                      progress=False, threads=True)
    out = {}
    for t in tick:
        try:
            d = raw[t].dropna(how="all")
        except KeyError:
            continue
        d = d.rename(columns=str.lower)[COLS].dropna(subset=["close"])
        if d.empty:
            continue
        d.index = (d.index.tz_convert(IST) if d.index.tz is not None
                   else d.index.tz_localize("UTC").tz_convert(IST))
        out[t.replace(".NS", "")] = split_today(d)
    return out


def split_today(d):
    """Split multi-day 1-min candles into (latest session df, avg 1-min volume of earlier sessions
    over the same elapsed minutes)."""
    last_day = d.index.date.max()
    td, prev = d[d.index.date == last_day], d[d.index.date < last_day]
    n = len(td)
    avg = float(prev.groupby(prev.index.date).head(n)["volume"].mean()) if len(prev) else 0.0
    td = td.copy()
    td.attrs["prev_close"] = float(prev["close"].iloc[-1]) if len(prev) else None
    return td, (avg if avg == avg else 0.0)


def index_stats(df):
    c = df["close"]
    ema = float(c.ewm(span=20).mean().iloc[-1])
    tp = (df["high"] + df["low"] + df["close"]) / 3
    v = df["volume"]
    vwap = float((tp * v).sum() / v.sum()) if v.sum() > 0 else float(tp.mean())
    return float(c.iloc[-1]), ema, vwap


def demo_data(symbols, minutes=45):
    rng = np.random.default_rng(7)
    start = pd.Timestamp.now(tz=IST).normalize() + pd.Timedelta(hours=9, minutes=15)
    idx = pd.date_range(start, periods=minutes, freq="1min")
    long_p = [(101, 101.3, 100.9, 101.2, 2500), (101.2, 101.3, 101.0, 101.05, 1500),
              (101.05, 101.5, 101.0, 101.4, 2200)]
    short_p = [(100, 100.1, 99.7, 99.8, 2500), (99.8, 100.0, 99.7, 99.95, 1500),
               (99.95, 100.0, 99.5, 99.6, 2200)]
    watch_p = [(101, 101.3, 100.9, 101.2, 2500)] + [(101.3, 101.4, 101.25, 101.3, 1500)] * 4

    def walk(price, n, drift):
        rows = []
        for _ in range(n):
            c = price * (1 + rng.normal(drift, 0.0005))
            rows.append((price, max(price, c) * 1.0003, min(price, c) * 0.9997, c,
                         int(rng.integers(1200, 2000))))
            price = c
        return rows

    out = {}
    for k, s in enumerate(symbols):
        p = (100 + k * 37.0) / 100
        kind = k % 4
        rows = [(100.5, 101, 100, 100.6, 2000)] * 15
        pat, drift = [(long_p, 0.0006), (long_p, 0.0003), (watch_p, 0.0), (short_p, -0.0005)][kind]
        rows += pat
        rows = [(o * p, h * p, l * p, c * p, v) for o, h, l, c, v in rows]
        rows += walk(rows[-1][3], minutes - len(rows), drift)
        df = pd.DataFrame(rows, index=idx[:len(rows)], columns=COLS)
        df.attrs["prev_close"] = rows[0][0] / (1 + [0.012, -0.01, 0.004, -0.015][kind])
        out[s] = (df, 1000.0)
    for key, base in zip(INDEX_KEYS, (24800, 52000, 81000)):
        ic = base * (1 + np.cumsum(np.full(minutes, 0.0002)))
        df = pd.DataFrame({"open": ic, "high": ic * 1.0002, "low": ic * 0.9998, "close": ic,
                           "volume": 1000}, index=idx)
        df.attrs["prev_close"] = base * 0.995
        out[key] = (df, 1000.0)
    return out
