"""Angel One SmartAPI feed: 1-min candles with real volume. Same return shape as data.fetch_live.
Secrets needed: ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PIN, ANGEL_TOTP_SECRET."""
import datetime as dt
import time

import pandas as pd
import pyotp
import requests

from data import COLS, IST, split_today

SCRIP_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
INDEX_TOKEN = "99926000"  # NIFTY 50
_state = {"api": None, "day": None, "tokens": {}}


def _login(sec):
    from SmartApi import SmartConnect
    api = SmartConnect(api_key=sec["ANGEL_API_KEY"])
    r = api.generateSession(sec["ANGEL_CLIENT_CODE"], sec["ANGEL_PIN"],
                            pyotp.TOTP(sec["ANGEL_TOTP_SECRET"]).now())
    if not r or not r.get("status"):
        raise RuntimeError(f"Angel One login failed: {(r or {}).get('message')}")
    return api


def _api(sec, force=False):
    today = dt.date.today()
    if force or _state["api"] is None or _state["day"] != today:
        _state["api"], _state["day"] = _login(sec), today
    return _state["api"]


def _tokens(symbols):
    missing = [s for s in symbols if s not in _state["tokens"]]
    if missing:
        master = requests.get(SCRIP_URL, timeout=60).json()
        want = {s + "-EQ": s for s in missing}
        for m in master:
            if m.get("exch_seg") == "NSE" and m.get("symbol") in want:
                _state["tokens"][want[m["symbol"]]] = m["token"]
    return {s: _state["tokens"][s] for s in symbols if s in _state["tokens"]}


def _candles(sec, token, frm, to):
    for attempt in range(3):
        res = _api(sec, force=attempt == 1).getCandleData(
            {"exchange": "NSE", "symboltoken": token, "interval": "ONE_MINUTE",
             "fromdate": frm, "todate": to})
        if res and res.get("status") and res.get("data"):
            d = pd.DataFrame(res["data"], columns=["time"] + COLS)
            d["time"] = pd.to_datetime(d["time"])
            d = d.set_index("time")
            d.index = d.index.tz_convert(IST) if d.index.tz is not None else d.index.tz_localize(IST)
            return d.astype(float)
        time.sleep(1.0)  # rate limit / expired session: retry (2nd try re-logins)
    return None


def fetch_live(symbols, sec):
    now = pd.Timestamp.now(tz=IST)
    frm = (now - pd.Timedelta(days=7)).strftime("%Y-%m-%d 09:15")
    to = now.strftime("%Y-%m-%d %H:%M")
    toks = _tokens(symbols)
    toks["^NSEI"] = INDEX_TOKEN
    out = {}
    for sym, tok in toks.items():
        d = _candles(sec, tok, frm, to)
        if d is not None and not d.empty:
            out[sym] = split_today(d)
        time.sleep(0.4)  # stay under SmartAPI historical-data rate limit
    return out
