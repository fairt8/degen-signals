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
        "h1": None, "h24": None, "hit2x": False, "hit5x": False, "msgId": None})

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
        e["lastPct"] = round((price / e["price0"] - 1) * 100, 1)
        mult = e["maxPrice"] / e["price0"]
        for k, x in (("hit2x", 2), ("hit5x", 5)):
            if mult >= x and not e[k]:
                e[k] = True; notes.append(("hit", e, f"🚀 ${e['symbol']} hit {x}x from alert (max seen {mult:.2f}x)"))
        chg = lambda: round((price / e["price0"] - 1) * 100, 1)
        if e["h1"] is None and age >= 1:
            e["h1"] = {"price": price, "pct": chg(), "maxX": round(mult, 2)}
            notes.append(("h1", e, f"⏱ 1h result ${e['symbol']}: {chg():+}% (max seen {mult:.2f}x)"))
        if e["h24"] is None and age >= 24:
            e["h24"] = {"price": price, "pct": chg(), "maxX": round(mult, 2)}
            notes.append(("h24", e, f"📅 24h result ${e['symbol']}: {chg():+}% (max seen {mult:.2f}x)"))
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
