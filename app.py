import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data
import modules as mod
from engine import scan_symbol, market_bias, TradeManager

st.set_page_config(page_title="Before the Noise", layout="wide")
DEFAULT = ("RELIANCE,TCS,HDFCBANK,ICICIBANK,INFY,SBIN,AXISBANK,ITC,LT,BAJFINANCE,MARUTI,SUNPHARMA,ADANIENT,"
           "KOTAKBANK,BHARTIARTL,TATASTEEL,JSWSTEEL,HINDALCO,ONGC,TITAN,M&M")
ss = st.session_state
ss.setdefault("trades", {}); ss.setdefault("log", []); ss.setdefault("seen", set()); ss.setdefault("wr", None)

with st.sidebar:
    st.title("Before the Noise")
    mode = st.radio("Data", ["Live (Angel One)", "Live (yfinance, delayed)"], index=0)
    syms = [s.strip().upper() for s in st.text_area("Universe (comma separated)", DEFAULT).split(",") if s.strip()]
    vol_min = st.slider("Volume surge (x avg)", 1.0, 3.0, 1.5, 0.1)
    min_liq = st.number_input("Min avg 1-min volume (liquidity)", 0, 100000, 500, 100)
    buf = st.slider("Breakout buffer %", 0.0, 0.5, 0.1, 0.05) / 100
    auto = st.checkbox("Auto-refresh every 60s", value=False)
    st.caption("Signals only - not investment advice.")


@st.cache_data(ttl=60, show_spinner="Scanning universe...")
def load(mode, symbols):
    if mode.startswith("Live (Angel"):
        import angel
        return angel.fetch_live(list(symbols), st.secrets)
    return data.fetch_live(list(symbols))


def war_room(sym, df, sig):
    fig = go.Figure(go.Candlestick(x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"]))
    for n, v in [("ORH", sig.proof.get("orh")), ("ORL", sig.proof.get("orl")), ("Entry", sig.entry),
                 ("SL", sig.sl), ("T1", sig.t1), ("T2", sig.t2)]:
        if v:
            fig.add_hline(y=v, line_dash="dot", annotation_text=n,
                          line_color={"SL": "red", "T1": "green", "T2": "green", "Entry": "blue"}.get(n, "gray"))
    if sig.status == "CONFIRMED":
        t0, trail, ex = mod.replay(sig, df)
        up = sig.direction == "LONG"
        fig.add_trace(go.Scatter(x=[t0], y=[sig.entry], mode="markers+text", text=["BUY" if up else "SELL"],
                                 textposition="bottom center" if up else "top center",
                                 marker=dict(symbol="triangle-up" if up else "triangle-down", size=16, color="green" if up else "red")))
        if trail:
            fig.add_trace(go.Scatter(x=[t for t, _ in trail], y=[v for _, v in trail], mode="lines",
                                     line=dict(color="orange", shape="hv"), name="Trailing SL"))
        if ex:
            fig.add_trace(go.Scatter(x=[ex[0]], y=[ex[1]], mode="markers+text", text=["EXIT"], textposition="top center",
                                     marker=dict(symbol="x", size=14, color="black")))
    fig.update_layout(height=520, margin=dict(l=0, r=0, t=10, b=0), xaxis_rangeslider_visible=False, showlegend=False)
    return fig


def body():
    try:
        d = load(mode, tuple(syms))
    except Exception as e:
        st.error(f"Data fetch failed: {e}. Check Angel One secrets or switch to yfinance.")
        return
    stocks = {s: v for s, v in d.items() if not s.startswith("^")}
    if "^NSEI" not in d or not stocks:
        st.warning("No data (market closed or feed issue).")
        return
    # ---- header: indices + breadth + bias
    cols = st.columns(6)
    for c, (name, k) in zip(cols[:3], [("NIFTY", "^NSEI"), ("BANKNIFTY", "^NSEBANK"), ("SENSEX", "^BSESN")]):
        if k in d:
            df = d[k][0]; pc = df.attrs.get("prev_close"); p = float(df["close"].iloc[-1])
            c.metric(name, f"{p:,.0f}", f"{(p / pc - 1) * 100:+.2f}%" if pc else None)
    adv = sum(1 for df, _ in stocks.values() if df["close"].iloc[-1] > df["open"].iloc[0])
    dec = sum(1 for df, _ in stocks.values() if df["close"].iloc[-1] < df["open"].iloc[0])
    ic, ema, vwap = data.index_stats(d["^NSEI"][0])
    bias = market_bias(adv, dec, ic, ema, vwap)
    cols[3].metric("Advance / Decline", f"{adv} / {dec}"); cols[4].metric("Bias", bias)
    cols[5].metric("Last candle", f"{d['^NSEI'][0].index[-1]:%H:%M}")
    sigs = {s: scan_symbol(s, df, bias, avg, vol_ratio_min=vol_min, buffer=buf) for s, (df, avg) in stocks.items()}
    lead = mod.leaders(stocks, bias, sigs, min_liq, vol_min)
    for r in lead:   # alert on fresh EXPLOSIVE leader
        if r["tier"] == "EXPLOSIVE" and r["symbol"] not in ss.seen:
            ss.seen.add(r["symbol"]); st.toast(f"EXPLOSIVE leader: {r['symbol']} ({r['dir']})", icon="💥")

    t = st.tabs(["💥 Leaders", "⚡ Trend Ignition", "🌅 Pre-Open Gaps", "⚔️ War Room", "Trades"])
    with t[0]:
        if bias == "NEUTRAL":
            st.info("Breadth/trend neutral - no leaders taken (Layer 1 gate).")
        icon = {"EXPLOSIVE": "💥", "STRONG": "🔥", "SPURT": "⚡"}
        for r in lead:
            with st.container(border=True):
                a, b, c2, e = st.columns([2, 2, 3, 1])
                a.markdown(f"**{icon[r['tier']]} {r['symbol']}** {r['dir']}  \n{r['tier']} - score {r['score']}")
                b.write(f"Vol x{r['vol_ratio']} | {r['move']:+.2f}%  \nLTP {r['ltp']} | detect {r['detect']:%H:%M}")
                c2.write(f"Option: **{r['strike']}** (ATM)  \nORB trigger {r['orb_level']} | SL area {r['sl_area']}"
                         + ("  \nORB breakout: yes" if r["brk"] else ""))
                if e.button("War Room", key=f"wr_{r['symbol']}"):
                    ss.wr = r["symbol"]; st.toast("Open the War Room tab")
        if not lead and bias != "NEUTRAL":
            st.write("No leaders right now.")
        st.caption("Premium zone needs an option-chain feed - not wired yet; strike is ATM from spot.")
    with t[1]:
        ig = mod.ignition(stocks)
        st.dataframe(pd.DataFrame(ig), use_container_width=True) if ig else st.write("No fresh ignitions.")
    with t[2]:
        g = mod.gaps(stocks)
        if g:
            gdf = pd.DataFrame(g)
            x, y = st.columns(2)
            x.subheader("Gap-up"); x.dataframe(gdf[gdf.gap > 0.3].sort_values("gap", ascending=False), use_container_width=True)
            y.subheader("Gap-down"); y.dataframe(gdf[gdf.gap < -0.3].sort_values("gap"), use_container_width=True)
        st.caption("Gap = 9:15 open vs previous close, frozen at the bell. Trap = gap reversed since open. "
                   "Exchange pre-open (IEP) data is not used.")
    with t[3]:
        names = list(stocks)
        sym = st.selectbox("Symbol", names, index=names.index(ss.wr) if ss.wr in names else 0)
        sig = sigs[sym]
        st.plotly_chart(war_room(sym, stocks[sym][0], sig), use_container_width=True, key="warroom")
        if sig.status == "CONFIRMED":
            st.write(f"**{sig.direction}** entry {sig.entry} | SL {sig.sl} | T1 {sig.t1} | T2 {sig.t2}")
            if st.button("Track trade"):
                ss.trades[sym] = TradeManager(sig)
        else:
            st.caption(f"Status: {sig.status} - arrows and trailing SL appear once the ORB signal confirms.")
    with t[4]:
        rows = []
        for sym, tm in ss.trades.items():
            if sym in stocks:
                for ev in tm.update(float(stocks[sym][0]["close"].iloc[-1])):
                    ss.log.append(f"{pd.Timestamp.now():%H:%M:%S} {sym} {ev}")
            rows.append({"Symbol": sym, "Entry": tm.entry, "SL (trailing)": tm.sl, "T1": tm.t1, "T2": tm.t2,
                         "Stage": tm.stage, "Closed": tm.closed})
        st.dataframe(pd.DataFrame(rows), use_container_width=True) if rows else st.write("No tracked trades.")
        st.caption("Tracking runs only while the page is open.")
        for line in ss.log[-15:][::-1]:
            st.text(line)


(st.fragment(run_every=60)(body) if auto else body)()
