import calendar as cal
import pandas as pd

COLS = ["Date", "Symbol", "Side", "Entry", "SL", "T1", "Exit", "Qty", "Setup"]


def enrich(rows):
    df = pd.DataFrame(rows, columns=COLS)
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"]).dt.date
    sgn = df["Side"].map({"BUY": 1, "SELL": -1})
    df["Pts"] = ((df["Exit"] - df["Entry"]) * sgn).round(2)
    df["PnL"] = (df["Pts"] * df["Qty"]).round(0)
    df["R"] = (df["Pts"] / (df["Entry"] - df["SL"]).abs().replace(0, float("nan"))).round(2)
    return df.sort_values("Date", ascending=False)


def stats(df):
    w, l = df[df.PnL > 0], df[df.PnL <= 0]
    gl, run, best = abs(l.PnL.sum()), 0, 0
    for p in df.sort_values("Date").PnL:
        run = run + 1 if p > 0 else 0
        best = max(best, run)
    return [(f"₹{df.PnL.sum():,.0f}", "NET P&L", "#15803d" if df.PnL.sum() >= 0 else "#b91c1c"),
            (f"{len(w) / len(df) * 100:.0f}%", "WIN RATE", "#15803d"),
            (f"{w.PnL.sum() / gl:.1f}" if gl else "inf", "PROFIT FACTOR", "#b45309"),
            (f"₹{w.PnL.mean():,.0f}" if len(w) else "-", "AVG WIN", "#15803d"),
            (f"₹{l.PnL.mean():,.0f}" if len(l) else "-", "AVG LOSS", "#b91c1c"),
            (str(best), "WIN STREAK", "#1d4ed8")]


def calendar_html(df, ref):
    daily = df.groupby("Date").PnL.sum()
    rows = ""
    for wk in cal.monthcalendar(ref.year, ref.month):
        tds = ""
        for d in wk:
            p = daily.get(ref.replace(day=d)) if d else None
            bg = "#fff" if d == 0 else "#f3f4f6" if p is None else "#bbf7d0" if p > 0 else "#fecaca"
            tds += f'<td style="background:{bg}">{d or ""}</td>'
        rows += f"<tr>{tds}</tr>"
    return f'<div class="bx"><b>{ref:%B %Y}</b><table class="cal"><tr>' + "".join(f"<td>{x}</td>" for x in "MTWTFSS") + f"</tr>{rows}</table></div>"
