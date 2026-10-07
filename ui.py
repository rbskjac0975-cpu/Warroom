"""HTML/CSS renderers for the card-style layout (breadth, leader columns, ignition, gaps)."""
CSS = """<style>
.bx,.col,.cd,.stat{color:#111}
.bx{background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:14px;margin-bottom:12px}
.col{max-height:640px;overflow-y:auto;border:1px solid #e5e7eb;border-radius:14px;background:#fff;padding-bottom:8px}
.hd{color:#fff;font-weight:800;padding:10px 14px;border-radius:14px 14px 0 0;display:flex;justify-content:space-between}
.sub{font-size:11px;font-weight:700;padding:6px 14px}
.cd{margin:8px;padding:10px 12px;border-radius:12px;border:1px solid}
.buy{background:#f0fdf4;border-color:#bbf7d0}.sell{background:#fef2f2;border-color:#fecaca}
.r1{display:flex;justify-content:space-between;align-items:center;font-weight:800}
.bg{color:#fff;border-radius:6px;padding:2px 8px;font-size:12px;font-weight:800}
.up{color:#15803d}.dn{color:#b91c1c}.mut{color:#6b7280;font-size:11px}
.vd{display:inline-block;color:#fff;border-radius:6px;padding:2px 8px;font-size:12px;font-weight:800;margin-top:6px}
.op{border:1px solid #d1d5db;border-radius:8px;padding:4px 8px;margin-top:6px;font-size:12px;background:#fff}
.row{display:flex;gap:10px;margin-bottom:10px}
.stat{flex:1;text-align:center;background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:10px;font-size:12px}
.stat b{font-size:26px;display:block}
.gp{display:flex;justify-content:space-between;font-size:13px;padding:3px 10px;font-weight:700;color:#111}
.cal td{width:34px;height:30px;text-align:center;border-radius:6px;font-size:12px;color:#111}
</style>"""

TIER = {"EXPLOSIVE": ("#dc2626", "💥", "BIG PLAYER ENTRY - institutional dhamaka", "#b91c1c"),
        "STRONG": ("#7c3aed", "🔥", "SMART MONEY MOVE - bade log active", "#6d28d9"),
        "SPURT": ("#f59e0b", "⚡", "VOLUME BUILDUP - interest ban rahi", "#b45309")}


def _cls(x):
    return "up" if x >= 0 else "dn"


def breadth(adv, unch, dec, n):
    tot = max(adv + unch + dec, 1)
    mood = "BULLISH breadth" if adv > 1.3 * max(dec, 1) else "BEARISH breadth" if dec > 1.3 * max(adv, 1) else "MIXED breadth"
    box = lambda v, lab, c: f'<div class="stat" style="color:{c}"><b>{v}</b>{lab}</div>'
    return (f'<div class="bx"><div style="display:flex;justify-content:space-between"><b>Market Breadth - Advance / Decline</b>'
            f'<span class="bg" style="background:#16a34a">{mood}</span></div><div class="row" style="margin-top:10px">'
            + box(adv, "ADVANCES", "#15803d") + box(unch, "UNCHANGED", "#6b7280") + box(dec, "DECLINES", "#b91c1c")
            + box(f"{adv / max(dec, 1):.2f}", "A / D RATIO", "#1d4ed8") + '</div>'
            f'<div style="display:flex;height:8px;border-radius:6px;overflow:hidden"><div style="width:{adv / tot * 100}%;background:#16a34a"></div>'
            f'<div style="width:{unch / tot * 100}%;background:#9ca3af"></div><div style="width:{dec / tot * 100}%;background:#dc2626"></div></div>'
            f'<div class="mut" style="margin-top:6px">{n} stocks me {adv} upar - {dec} neeche - {unch} flat - {adv / tot * 100:.0f}% universe green</div></div>')


def leader_card(r):
    buy = r["dir"] == "LONG"
    c = TIER[r["tier"]][0]
    star = "★★★ STRONG" if r["tier"] != "SPURT" else "★★ Moderate"
    return (f'<div class="cd {"buy" if buy else "sell"}"><div class="r1"><span>{r["symbol"]}</span><span>'
            f'<span class="bg" style="background:{c}">{r["vol_ratio"]}x</span> <span class="mut">{r["score"]:.0f} | 🕐 {r["detect"]:%H:%M}</span></span></div>'
            f'<div class="r1" style="font-size:18px">{r["ltp"]:,.2f} <span class="{_cls(r["move"])}" style="font-size:12px;margin-left:6px">'
            f'{"▲" if r["move"] >= 0 else "▼"} {r["move"]:+.2f}%</span></div>'
            f'<div class="mut">gap {r["gap"]:+.1f}% - body {r["body"]}% - {r["cand"]} candle - low se <span class="up">▲{r["from_low"]}%</span> - high se <span class="dn">▼{abs(r["from_high"])}%</span></div>'
            f'<span class="vd" style="background:{"#16a34a" if buy else "#dc2626"}">{star} {"BUY" if buy else "SELL"} WATCH</span>'
            f'<div class="op">🎯 <b>{r["strike"]}</b> - ORB {r["orb_level"]} - SL area {r["sl_area"]}</div></div>')


def tier_col(tier, rows):
    c, ic, sub, tc = TIER[tier]
    body = "".join(leader_card(r) for r in rows) or '<div class="mut" style="padding:14px">No leaders</div>'
    return (f'<div class="col"><div class="hd" style="background:{c}"><span>{ic} {tier}</span><span>{len(rows)}</span></div>'
            f'<div class="sub" style="color:{tc}">{sub}</div>{body}</div>')


def ignition_col(rows):
    body = "".join(
        f'<div class="cd {"buy" if r["dir"] == "LONG" else "sell"}"><div class="r1"><span>{r["symbol"]}</span>'
        f'<span class="bg" style="background:#7c3aed">⚡</span><span class="mut">🕐 {r["time"]:%H:%M}</span></div>'
        f'<div class="r1">₹{r["ltp"]:,.1f} <span class="{_cls(r["move"])}" style="font-size:12px">{r["move"]:+.2f}%</span></div>'
        f'<div class="mut">TREND IGNITION - opened at day\'s {"low" if r["dir"] == "LONG" else "high"} - entry {r["entry"]}</div></div>'
        for r in rows) or '<div class="mut" style="padding:14px">No fresh ignitions</div>'
    return (f'<div class="col"><div class="hd" style="background:#d97706"><span>⚡ TREND IGNITION</span><span>{len(rows)}</span></div>{body}</div>')


def gap_box(title, color, rows, price=True):
    body = "".join(f'<div class="gp"><span>{r["symbol"]} <span class="{_cls(r["gap"])}">{r["gap"]:+.2f}%</span></span>'
                   f'<span class="mut">{"₹" + format(r["ltp"], ",.1f") if price else ""}</span></div>' for r in rows) \
        or '<div class="mut" style="padding:8px 10px">none</div>'
    return (f'<div class="bx" style="border-color:{color};padding:8px 0"><div class="gp" style="color:{color}"><b>{title}</b><b>{len(rows)}</b></div>{body}</div>')
