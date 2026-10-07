import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data
from engine import scan_symbol, market_bias, TradeManager, ORB_MINUTES

st.set_page_config(page_title="Before the Noise", layout="wide")
DEFAULT = ("RELIANCE,TCS,HDFCBANK,ICICIBANK,INFY,SBIN,AXISBANK,ITC,LT,BAJFINANCE,"
           "MARUTI,SUNPHARMA,ADANIENT,KOTAKBANK,BHARTIARTL,TATASTEEL,JSWSTEEL,"
           "HINDALCO,ONGC,TITAN,M&M")

st.session_state.setdefault("trades", {})
st.session_state.setdefault("log", [])

with st.sidebar:
    st.title("Before the Noise")
    mode = st.radio("Data", ["Live (Angel One)", "Live (yfinance, delayed)", "Demo"], index=2)
    syms = [s.strip().upper() for s in st.text_area("Universe (comma separated)", DEFAULT).split(",") if s.strip()]
    vol_min = st.slider("Volume surge (x avg)", 1.0, 3.0, 1.5, 0.1)
    buf = st.slider("Breakout buffer %", 0.0, 0.5, 0.1, 0.05) / 100
    auto = st.checkbox("Auto-refresh every 60s", value=False)
    st.caption("Signals only - not investment advice.")


@st.cache_data(ttl=60, show_spinner="Scanning universe...")
def load(mode, symbols):
    if mode.startswith("Live (Angel"):
        import angel
        return angel.fetch_live(list(symbols), st.secrets)
    if mode.startswith("Live (yf"):
        return data.fetch_live(list(symbols))
    return data.demo_data(list(symbols))


def chart(sig, df):
    snap = sig.proof.get("chart_snapshot")
    if snap:
        df = pd.DataFrame(snap).rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "t": "time"}).set_index("time")
    fig = go.Figure(go.Candlestick(x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"]))
    for name, val, col in [("ORH", sig.proof.get("orh"), "gray"), ("ORL", sig.proof.get("orl"), "gray"),
                           ("Entry", sig.entry, "blue"), ("SL", sig.sl, "red"),
                           ("T1", sig.t1, "green"), ("T2", sig.t2, "green")]:
        if val:
            fig.add_hline(y=val, line_dash="dot", line_color=col, annotation_text=name)
    fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), xaxis_rangeslider_visible=False)
    return fig


def card(sig, df):
    with st.container(border=True):
        a, b = st.columns([1, 2])
        with a:
            st.subheader(f"{sig.symbol} - {sig.direction}")
            if sig.status == "CONFIRMED":
                st.write(f"Entry **{sig.entry}** | SL **{sig.sl}**  \nT1 {sig.t1} | T2 {sig.t2}")
                if st.button("Track trade", key=f"t_{sig.symbol}"):
                    st.session_state.trades[sig.symbol] = TradeManager(sig)
            else:
                st.caption("Waiting for ORB breakout + retest" if len(df) > ORB_MINUTES
                           else "Opening range still forming")
            with st.expander("Detect-time proof"):
                st.json({k: v for k, v in sig.proof.items() if k != "chart_snapshot"})
        with b:
            st.plotly_chart(chart(sig, df), use_container_width=True, key=f"c_{sig.symbol}")


def body():
    try:
        d = load(mode, tuple(syms))
    except Exception as e:
        st.error(f"Data fetch failed: {e}. Check secrets / try Demo mode.")
        return
    if "^NSEI" not in d:
        st.warning("No index data (market closed or feed issue).")
        return
    stocks = {s: v for s, v in d.items() if s != "^NSEI"}
    adv = sum(1 for df, _ in stocks.values() if df["close"].iloc[-1] > df["open"].iloc[0])
    dec = sum(1 for df, _ in stocks.values() if df["close"].iloc[-1] < df["open"].iloc[0])
    ic, ema, vwap = data.index_stats(d["^NSEI"][0])
    bias = market_bias(adv, dec, ic, ema, vwap)

    # Market breadth on top, before any signal
    m = st.columns(5)
    m[0].metric("Advance", adv); m[1].metric("Decline", dec)
    m[2].metric("NIFTY", f"{ic:,.0f}"); m[3].metric("EMA20 / VWAP", f"{ema:,.0f} / {vwap:,.0f}")
    m[4].metric("Bias", bias)
    last = d["^NSEI"][0].index[-1]
    st.caption(f"Last candle {last:%d %b %H:%M} IST - " + {"Live (Angel One)": "Angel One 1-min candles", "Live (yfinance, delayed)": "delayed data"}.get(mode, "demo data"))

    sigs = {s: scan_symbol(s, df, bias, avg, vol_ratio_min=vol_min, buffer=buf) for s, (df, avg) in stocks.items()}
    groups = {k: [s for s in sigs.values() if s.status == k] for k in ("CONFIRMED", "WATCH", "FAILED")}
    tabs = st.tabs([f"Confirmed ({len(groups['CONFIRMED'])})", f"Watch ({len(groups['WATCH'])})",
                    f"Failed ({len(groups['FAILED'])})", f"Trades ({len(st.session_state.trades)})"])
    for tab, key in zip(tabs[:3], groups):
        with tab:
            if bias == "NEUTRAL":
                st.info("Breadth/trend neutral - no trades taken (Layer 1 gate).")
            for s in groups[key]:
                card(s, stocks[s.symbol][0])
    with tabs[3]:
        rows = []
        for sym, tm in st.session_state.trades.items():
            if sym in stocks:
                for ev in tm.update(float(stocks[sym][0]["close"].iloc[-1])):
                    st.session_state.log.append(f"{pd.Timestamp.now():%H:%M:%S} {sym} {ev}")
            rows.append({"Symbol": sym, "Entry": tm.entry, "SL (trailing)": tm.sl, "T1": tm.t1, "T2": tm.t2,
                         "Stage": tm.stage, "Closed": tm.closed})
        st.dataframe(pd.DataFrame(rows), use_container_width=True) if rows else st.write("No tracked trades.")
        st.caption("Tracking runs only while this page is open; a 24x7 backend worker is needed for unattended trailing.")
        for line in st.session_state.log[-15:][::-1]:
            st.text(line)


(st.fragment(run_every=60)(body) if auto else body)()
