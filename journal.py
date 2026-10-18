"""Signal journal + watch mode. Stored inside docs/signals.json ("journal" key) so the existing workflow commits it.
Each entry: entry price/mcap/time/score/devScore; outcomes at 1h & 24h; max-seen price; 2x/5x hits;
watch: trend state for WATCH_HOURS after alert (Telegram notice only when state changes)."""
import time, pipeline

WATCH_HOURS, MAX_SAMPLES = 6, 48

def add(journal, r, t0=None):
    if any(e["mint"] == r["mint"] for e in journal): return
    journal.insert(0, {"mint": r["mint"], "symbol": r["symbol"], "chain": r["chain"], "t0": int(t0 or time.time()),
        "price0": r.get("priceUsd"), "mcap0": r["mcap"], "score": r.get("score"), "devScore": r.get("devScore", 0),
        "link": r["links"]["dexscreener"], "maxPrice": r.get("priceUsd"), "samples": [], "trend": None,
        "h1": None, "h24": None, "hit2x": False, "hit5x": False, "msgId": None,
        "athMc": (r.get("chartAth") or {}).get("mc"), "athT": (r.get("chartAth") or {}).get("t"),
        "lp": ({k: (r.get("lp") or {}).get(k) for k in ("status", "label", "pct", "unlock")}
               | {"t": int(time.time()), "pctMax": (r.get("lp") or {}).get("pct"), "liq": r.get("liq"), "liqMax": r.get("liq")}) if r.get("lp") else None})

def prices(mints):
    """Best-liquidity pair price per mint via /tokens/v1 (30 per call). Errors -> missing."""
    out = {}
    for i in range(0, len(mints), 30):
        try:
            for p in pipeline.get(f"{pipeline.DS}/tokens/v1/solana/{','.join(mints[i:i+30])}"):
                m = p["baseToken"]["address"]
                if m not in out or (p.get("liquidity") or {}).get("usd", 0) > out[m][1]:
                    out[m] = (p, (p.get("liquidity") or {}).get("usd", 0))
        except Exception as e:
            print("journal price fetch error:", e)
    return {m: v[0] for m, v in out.items()}

def trend_state(e, p):
    """'up' / 'fading' / None. Uses sampled prices across runs (fast=last 3, slow=last 9) when available,
    else DexScreener m5/h1 change signs."""
    s = [x[1] for x in e["samples"]]
    pc = p.get("priceChange") or {}
    if len(s) >= 9:
        fast, slow = sum(s[-3:]) / 3, sum(s[-9:]) / 9
        if fast > slow * 1.02 and (pc.get("m5") or 0) >= 0: return "up"
        if fast < slow * 0.97: return "fading"
        return e["trend"]
    m5, h1 = pc.get("m5") or 0, pc.get("h1") or 0
    if m5 > 0 and h1 > 0: return "up"
    if m5 < -5 and h1 < 0: return "fading"
    return e["trend"]

MILESTONES, MILESTONE_STEP = [2, 5, 10, 15, 20, 30, 50, 60, 70, 80, 90, 100], 50

def milestone_list(mult):
    """Milestones <= mult: configured list, then every MILESTONE_STEP beyond its last value."""
    out = [m for m in MILESTONES if m <= mult]
    if MILESTONES and mult >= MILESTONES[-1] + MILESTONE_STEP:
        x = MILESTONES[-1] + MILESTONE_STEP
        while x <= mult: out.append(x); x += MILESTONE_STEP
    return out

def chart_max(e, p, now, until=None):
    """Raise e['maxPrice'] to the chart high since the alert; refresh all-time chart ATH MC. Returns True if this was
    the first chart pass for an entry older than 2h (milestones found then are recorded without a reply)."""
    import chart
    first = not e.get("chartT")
    pool = p.get("pairAddress")
    h = chart.ath(e["mint"], since=e["t0"], until=until, pool=pool) if pool else None
    if h and h["price"] > (e.get("maxPrice") or 0):
        e["maxPrice"], e["maxSrc"] = h["price"], "chart"
    mc, pr = p.get("marketCap") or p.get("fdv"), float(p.get("priceUsd") or 0)
    a = chart.ath(e["mint"], mc, pr, fallback_pool=pool)
    if a and a.get("mc"): e["athMc"], e["athT"], e["athSrc"] = max(a["mc"], e.get("athMc") or 0), a["t"], "chart"
    e["chartT"] = int(now)
    return first and (now - e["t0"]) > 2 * 3600

def backfill_chart(journal, n=4, now=None):
    """Entries already past 24h without a chart pass: chart high within the 24h window + ATH MC (silent; no replies)."""
    now = now or time.time()
    todo = [e for e in journal if e.get("h24") and not e.get("chartT") and e.get("chain") == "solana" and e.get("price0")][:n]
    if not todo: return
    px = prices([e["mint"] for e in todo])
    for e in todo:
        if px.get(e["mint"]):
            chart_max(e, px[e["mint"]], now, until=e["t0"] + 24 * 3600)
            mult = e["maxPrice"] / e["price0"]
            hits = e.setdefault("milestones", {})
            for x in milestone_list(mult):
                hits.setdefault(f"{x:g}", None)
                if x == 2: e["hit2x"] = True
                if x == 5: e["hit5x"] = True
            if hits:
                top = max(hits, key=float); e["topMilestone"], e["topMilestoneT"] = float(top), hits[top]

def update(journal, now=None):
    """Update outcomes + trend. Returns list of (kind, entry, text) notifications."""
    now = now or time.time()
    todo = [e for e in journal if e["h24"] is None and e["chain"] == "solana"]
    px = prices([e["mint"] for e in todo]) if todo else {}
    notes = []
    for e in todo:
        p = px.get(e["mint"])
        if not p: continue
        price = float(p.get("priceUsd") or 0)
        if not price: continue
        if not e.get("price0"):  # backfilled entry: derive entry price from mcap ratio
            mc = p.get("marketCap") or p.get("fdv")
            if not mc or not e.get("mcap0"): continue
            e["price0"] = price * e["mcap0"] / mc; e["maxPrice"] = max(e["price0"], price)
        age = (now - e["t0"]) / 3600
        e["last"], e["lastT"] = price, int(now)
        e["maxPrice"] = max(e.get("maxPrice") or 0, price)
        silent = chart_max(e, p, now)  # real chart high since alert (GeckoTerminal); first pass on older entries is silent
        e["minPrice"] = min(e.get("minPrice") or price, price)  # for optional TP stop-loss sim
        e["lastPct"] = round((price / e["price0"] - 1) * 100, 1)
        mult = e["maxPrice"] / e["price0"]
        # multiplier milestones (config milestones + every milestoneStep beyond the last); one reply per milestone
        first_init = "milestones" not in e
        hits = e.setdefault("milestones", {})
        for x in milestone_list(mult):
            k = f"{x:g}"
            if k in hits: continue
            if first_init or silent or (x == 2 and e.get("hit2x")) or (x == 5 and e.get("hit5x")):
                hits[k] = None  # reached before milestone tracking existed: record, no new message
            else:
                hits[k] = int(now)
                el = (now - e["t0"]) / 3600
                src = "chart high" if e.get("maxSrc") == "chart" else "max seen"
                notes.append(("hit", e, f"🚀 ${e['symbol']} hit {k}x from alert ({src} {mult:.2f}x, {el:.1f}h after alert)"))
            if x == 2: e["hit2x"] = True
            if x == 5: e["hit5x"] = True
        if hits:
            top = max(hits, key=float); e["topMilestone"], e["topMilestoneT"] = float(top), hits[top]
        chg = lambda: round((price / e["price0"] - 1) * 100, 1)
        if e["h1"] is None and age >= 1:
            e["h1"] = {"price": price, "pct": chg(), "maxX": round(mult, 2)}
            notes.append(("h1", e, f"⏱ 1h result ${e['symbol']}: PnL {chg():+}% · max gain {(mult-1)*100:+.0f}% ({mult:.2f}x)"))
        if e["h24"] is None and age >= 24:
            e["h24"] = {"price": price, "pct": chg(), "maxX": round(mult, 2)}
            notes.append(("h24", e, f"📅 24h result ${e['symbol']}: PnL {chg():+}% · max gain {(mult-1)*100:+.0f}% ({mult:.2f}x)"))
        if age <= WATCH_HOURS:
            e["samples"] = (e["samples"] + [[int(now), price]])[-MAX_SAMPLES:]
            st = trend_state(e, p)
            if st and st != e["trend"]:
                if e["trend"] is not None or st == "fading":  # skip the initial 'up' (alert already implies it)
                    msg = (f"📈 ${e['symbol']} trend turned up ({chg():+}% vs alert)" if st == "up"
                           else f"⚠️ ${e['symbol']} momentum fading ({chg():+}% vs alert), consider exit")
                    notes.append(("trend", e, msg))
                e["trend"] = st
        elif e["samples"]:
            e["samples"] = []  # stop watching; keep file small
    return notes

def stats(journal):
    def agg(k):
        r = [e[k]["pct"] for e in journal if e.get(k)]
        if not r: return {"n": 0}
        return {"n": len(r), "winRate": round(sum(x > 0 for x in r) / len(r) * 100, 1), "avg": round(sum(r) / len(r), 1),
                "best": max(r), "worst": min(r)}
    n = len(journal)
    return {"signals": n, "h1": agg("h1"), "h24": agg("h24"),
            "hit2x": sum(e["hit2x"] for e in journal), "hit5x": sum(e["hit5x"] for e in journal)}


# ---------- period PnL / win rate (WAT = UTC+1) ----------
import datetime as _dt
WAT = _dt.timezone(_dt.timedelta(hours=1))

def ret(e):
    """(pct, basis): 24h result if available, else latest live % (falls back to 1h)."""
    if e.get("h24"): return e["h24"]["pct"], "24h"
    if e.get("lastPct") is not None: return e["lastPct"], "live"
    if e.get("h1"): return e["h1"]["pct"], "live"
    return None, None

def period_bounds(now=None):
    n = _dt.datetime.fromtimestamp(now or time.time(), WAT)
    day = n.replace(hour=0, minute=0, second=0, microsecond=0)
    return {"today": day.timestamp(), "week": (day - _dt.timedelta(days=day.weekday())).timestamp(),
            "month": day.replace(day=1).timestamp(), "all": 0}

TP_DEFAULT = {"atPct": 100, "sellFrac": 0.5, "stopLossPct": None}

def tp_ret(e, hold, tp=None):
    """Simulated TP strategy %: sell sellFrac at +atPct if max gain seen reached it; rest exits at the hold basis.
    Optional stopLossPct (e.g. -50): if TP never hit and min price seen fell to it, exit all at stopLossPct."""
    tp = {**TP_DEFAULT, **(tp or {})}
    if hold is None or not e.get("price0"): return hold
    max_gain = ((e.get("maxPrice") or e["price0"]) / e["price0"] - 1) * 100
    if max_gain >= tp["atPct"]:
        return round(tp["sellFrac"] * tp["atPct"] + (1 - tp["sellFrac"]) * hold, 1)
    sl = tp.get("stopLossPct")
    if sl is not None and e.get("minPrice") and (e["minPrice"] / e["price0"] - 1) * 100 <= sl:
        return float(sl)
    return hold

def _ms_counts(es):
    c = {"2": 0, "5": 0}
    for e in es:
        hs = e.get("milestones") or ({"2": None} if e.get("hit2x") else {})
        if e.get("hit5x"): hs = {**hs, "5": None}
        for k in hs: c[k] = c.get(k, 0) + 1
    return dict(sorted(c.items(), key=lambda kv: float(kv[0])))

def period_stats(journal, win_pct=0, now=None, tp=None):
    """Per period (WAT boundaries, by alert time): signals, wins, win rate, total & avg PnL %, best/worst, 2x/5x, basis counts."""
    out = {}
    for p, start in period_bounds(now).items():
        es = [e for e in journal if e["t0"] >= start]
        rs = [(e,) + ret(e) for e in es]
        rs = [x for x in rs if x[1] is not None]
        pcts = [x[1] for x in rs]
        wins = sum(x > win_pct for x in pcts)
        b, w = (max(rs, key=lambda x: x[1]), min(rs, key=lambda x: x[1])) if rs else (None, None)
        out[p] = {"signals": len(es), "n": len(pcts), "wins": wins,
                  "winRate": round(wins / len(pcts) * 100, 1) if pcts else None,
                  "totalPnl": round(sum(pcts), 1) if pcts else None,
                  "avgPnl": round(sum(pcts) / len(pcts), 1) if pcts else None,
                  "best": f"{b[0]['symbol']} {b[1]:+.0f}%" if b else None,
                  "worst": f"{w[0]['symbol']} {w[1]:+.0f}%" if w else None,
                  "basis": {"24h": sum(x[2] == "24h" for x in rs), "live": sum(x[2] == "live" for x in rs)},
                  "hit2x": sum(e["hit2x"] for e in es), "hit5x": sum(e["hit5x"] for e in es),
                  "milestones": _ms_counts(es)}
        tps = [tp_ret(x[0], x[1], tp) for x in rs]
        tw = sum(x > win_pct for x in tps)
        out[p].update(tpWins=tw, tpWinRate=round(tw / len(tps) * 100, 1) if tps else None,
                      tpTotalPnl=round(sum(tps), 1) if tps else None, tpAvgPnl=round(sum(tps) / len(tps), 1) if tps else None)
    return out


def odds(journal, exclude=None, rug_pct=-90):
    """Historical outcomes of OUR past signals (>=1h old): share that hit 2x, share that dropped >90% (rug)."""
    es = [e for e in journal if e.get("mint") != exclude and e.get("h1") and e.get("price0")]
    if not es: return {"n": 0}
    def worst(e):
        v = [x for x in [e.get("lastPct"), (e.get("h1") or {}).get("pct"), (e.get("h24") or {}).get("pct")] if x is not None]
        if e.get("minPrice"): v.append((e["minPrice"] / e["price0"] - 1) * 100)
        return min(v) if v else 0
    n = len(es)
    return {"n": n, "x2": round(sum(bool(e.get("hit2x")) for e in es) / n * 100), "rug": round(sum(worst(e) <= rug_pct for e in es) / n * 100)}
