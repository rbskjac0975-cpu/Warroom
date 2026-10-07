import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data
import journal as jr
import modules as mod
import ui
from engine import scan_symbol, market_bias, TradeManager

st.set_page_config(page_title="Before the Noise", layout="wide")
DEFAULT = ("RELIANCE,TCS,HDFCBANK,ICICIBANK,INFY,SBIN,AXISBANK,ITC,LT,BAJFINANCE,MARUTI,SUNPHARMA,ADANIENT,"
           "KOTAKBANK,BHARTIARTL,TATASTEEL,JSWSTEEL,HINDALCO,ONGC,TITAN,M&M")
ss = st.session_state
ss.setdefault("trades", {}); ss.setdefault("log", []); ss.setdefault("seen", set())
ss.setdefault("journal", [])

with st.sidebar:
    st.title("Before the Noise")
    mode = st.radio("Data", ["Live (Angel One)", "Live (yfinance, delayed)"], index=0)
    syms = [s.strip().upper() for s in st.text_area("Universe (comma separated)", DEFAULT).split(",") if s.strip()]
    vol_min = st.slider("Volume surge (x avg)", 1.0, 3.0, 1.5, 0.1)
    min_liq = st.number_input("Min avg 1-min volume (liquidity)", 0, 100000, 500, 100)
    buf = st.slider("Breakout buffer %", 0.0, 0.5, 0.1, 0.05) / 100
    auto = st.checkbox("Auto-refresh every 60s", value=False)
    st.caption("Education & research only - not investment advice.")


@st.cache_data(ttl=60, show_spinner="Scanning universe...")
def load(mode, symbols):
    if mode.startswith("Live (Angel"):
        import angel
        return angel.fetch_live(list(symbols), st.secrets)
    return data.fetch_live(list(symbols))


def war_room(df, sig):
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
                                     line=dict(color="orange", shape="hv")))
        if ex:
            fig.add_trace(go.Scatter(x=[ex[0]], y=[ex[1]], mode="markers+text", text=["EXIT"], textposition="top center",
                                     marker=dict(symbol="x", size=14, color="black")))
    fig.update_layout(height=520, margin=dict(l=0, r=0, t=10, b=0), xaxis_rangeslider_visible=False, showlegend=False)
    return fig


def leaders_at(stocks, idx_df, n=None):
    """Breadth + bias + leaders on candles up to n (None = latest)."""
    cut = (lambda df: df) if n is None else (lambda df: df.iloc[:n])
    st_ = {s: (cut(df), a) for s, (df, a) in stocks.items()}
    adv = sum(1 for df, _ in st_.values() if df["close"].iloc[-1] > df["open"].iloc[0])
    dec = sum(1 for df, _ in st_.values() if df["close"].iloc[-1] < df["open"].iloc[0])
    ic, ema, vw = data.index_stats(cut(idx_df))
    bias = market_bias(adv, dec, ic, ema, vw)
    sigs = {s: scan_symbol(s, df, bias, a, vol_ratio_min=vol_min, buffer=buf) for s, (df, a) in st_.items()}
    return st_, adv, dec, bias, sigs, mod.leaders(st_, bias, sigs, min_liq, vol_min)


def journal_tab():
    with st.expander("➕ Add Trade"):
        with st.form("add_trade", clear_on_submit=True):
            c = st.columns(5)
            d = c[0].date_input("Date", dt.date.today()); sym = c[1].text_input("Symbol")
            side = c[2].selectbox("Side", ["BUY", "SELL"]); qty = c[3].number_input("Qty", 1, 1000000, 1)
            setup = c[4].selectbox("Setup", ["War Room", "Trend Ign.", "Leaders", "Own"])
            c = st.columns(4)
            en, sl, t1, ex = (c[i].number_input(n, 0.0, 1e7, 0.0, 0.05) for i, n in enumerate(["Entry", "SL", "T1", "Exit"]))
            if st.form_submit_button("Save") and sym:
                ss.journal.append(dict(zip(jr.COLS, [d, sym.upper(), side, en, sl, t1, ex, qty, setup])))
    up = st.file_uploader("Import CSV", type="csv")
    if up is not None and not ss.get("imported") == up.name:
        ss.journal += pd.read_csv(up)[jr.COLS].to_dict("records"); ss.imported = up.name
    df = jr.enrich(ss.journal)
    if df.empty:
        st.info("No trades yet. Journal lives in this session - export CSV to keep it.")
        return
    st.markdown(ui.CSS + '<div class="row">' + "".join(f'<div class="stat" style="color:{c}"><b>{v}</b>{l}</div>' for v, l, c in jr.stats(df)) + "</div>", unsafe_allow_html=True)
    a, b = st.columns([2, 1])
    daily = df.groupby("Date").PnL.sum().sort_index().cumsum()
    fig = go.Figure(go.Scatter(x=daily.index, y=daily.values, fill="tozeroy", line=dict(color="#16a34a")))
    fig.update_layout(height=260, margin=dict(l=0, r=0, t=20, b=0), title="Equity Curve")
    a.plotly_chart(fig, use_container_width=True, key="eq")
    b.markdown(jr.calendar_html(df, dt.date.today().replace(day=1)), unsafe_allow_html=True)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button("Export CSV", df.to_csv(index=False), "journal.csv")


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
    idx = d["^NSEI"][0]
    cols = st.columns(4)
    for c, (name, k) in zip(cols, [("NIFTY", "^NSEI"), ("BANKNIFTY", "^NSEBANK"), ("SENSEX", "^BSESN")]):
        if k in d:
            df = d[k][0]; pc = df.attrs.get("prev_close"); p = float(df["close"].iloc[-1])
            c.metric(name, f"{p:,.0f}", f"{(p / pc - 1) * 100:+.2f}%" if pc else None)
    cols[3].metric("Last candle", f"{idx.index[-1]:%d %b %H:%M}")

    _, adv, dec, bias, sigs, lead = leaders_at(stocks, idx)
    unch = len(stocks) - adv - dec
    st.markdown(ui.CSS + ui.breadth(adv, unch, dec, len(stocks)), unsafe_allow_html=True)
    for r in lead:
        if r["tier"] == "EXPLOSIVE" and r["symbol"] not in ss.seen:
            ss.seen.add(r["symbol"]); st.toast(f"EXPLOSIVE leader: {r['symbol']} ({r['dir']})", icon="💥")

    cnt = {t: sum(r["tier"] == t for r in lead) for t in ui.TIER}
    sig_n = sum(1 for df, a in stocks.values() if a > 0 and df["volume"].mean() / a >= vol_min)
    st.markdown(f'<div class="bx"><b>⚡ Breakout Leaders</b> &nbsp; <span class="bg" style="background:#16a34a">BULL ({adv})</span> '
                f'<span class="bg" style="background:#dc2626">BEAR ({dec})</span> &nbsp; 💥 {cnt["EXPLOSIVE"]} - 🔥 {cnt["STRONG"]} - ⚡ {cnt["SPURT"]} '
                f'- total {len(lead)}<div class="mut" style="margin-top:6px">UNIVERSE {len(syms)} → SCAN OK {len(stocks)} → SIGNAL {sig_n} '
                f'(≥{vol_min}x) → CLEAN {len(lead)} - illiquid / late / against-bias names removed'
                + (" - bias NEUTRAL: no leaders taken" if bias == "NEUTRAL" else "") + '</div></div>', unsafe_allow_html=True)
    c = st.columns(4)
    for col, t in zip(c[:3], ui.TIER):
        col.markdown(ui.tier_col(t, [r for r in lead if r["tier"] == t]), unsafe_allow_html=True)
    c[3].markdown(ui.ignition_col(mod.ignition(stocks)), unsafe_allow_html=True)

    g = mod.gaps(stocks)
    st.markdown('<div class="hd" style="background:#dc2626;border-radius:12px">🌅 PRE-OPEN GAPS <span style="font-size:11px">gap = 9:15 open vs prev close, frozen at the bell - information only</span></div>', unsafe_allow_html=True)
    L, R = st.columns(2)
    up_ = sorted([r for r in g if r["gap"] > 0.3], key=lambda r: -r["gap"])
    dn_ = sorted([r for r in g if r["gap"] < -0.3], key=lambda r: r["gap"])
    L.markdown(ui.gap_box("▲ GAP UP", "#16a34a", up_) + ui.gap_box("▼ GAP DOWN", "#dc2626", dn_), unsafe_allow_html=True)
    R.markdown(ui.gap_box("LONG-TRAP", "#d97706", [r for r in g if r["trap"] == "LONG TRAP"], False)
               + ui.gap_box("SHORT-TRAP", "#d97706", [r for r in g if r["trap"] == "SHORT TRAP"], False), unsafe_allow_html=True)

    t = st.tabs(["⚔️ War Room", "📓 Journal", "▶ Day Replay", "Trades"])
    with t[0]:
        names = list(stocks)
        pick = [r["symbol"] for r in lead] + [n for n in names if n not in [r["symbol"] for r in lead]]
        sym = st.selectbox("Symbol (leaders first)", pick)
        sig = sigs[sym]
        st.plotly_chart(war_room(stocks[sym][0], sig), use_container_width=True, key="warroom")
        if sig.status == "CONFIRMED":
            st.write(f"**{sig.direction}** entry {sig.entry} | SL {sig.sl} | T1 {sig.t1} | T2 {sig.t2}")
            if st.button("Track trade"):
                ss.trades[sym] = TradeManager(sig)
        else:
            st.caption(f"Status: {sig.status} - arrows and trailing SL appear once the ORB signal confirms.")
    with t[1]:
        journal_tab()
    with t[2]:
        n = st.slider("Replay minute", 2, len(idx), len(idx), format="%d min")
        st.caption(f"Day as it ran live - {idx.index[n - 1]:%H:%M}")
        _, a2, d2, b2, _, l2 = leaders_at(stocks, idx, n)
        st.write(f"Breadth {a2}/{d2} - bias {b2}")
        rc = st.columns(3)
        for col, tr in zip(rc, ui.TIER):
            col.markdown(ui.tier_col(tr, [r for r in l2 if r["tier"] == tr]), unsafe_allow_html=True)
    with t[3]:
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
