"""Data layer: live yfinance (delayed). Swap fetch_live for a broker feed later."""
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
