"""LP status (burned / locked / unlocked) from the free rugcheck report + DexScreener, and unlock/pull monitoring.
Monitoring re-checks recent journal signals each run and returns one-time warnings (reply to the original alert)."""
import sys, time
import pipeline

CLMM = ("meteoraDlmm", "meteora_dlmm", "raydium_clmm", "orca_whirlpool", "orca", "meteoraDammV2")

def status(mint, pair=None, dex=None):
    """{'status','label','pct','unlock','lockedUsd','market','src'}; status in burned|locked|burned+locked|partial|unlocked|bonding|clmm|unknown."""
    if dex == "pumpfun":
        return {"status": "bonding", "label": "💊 Bonding curve (no LP yet)", "pct": None, "src": "dexscreener"}
    try:
        d = pipeline.cached("rc:" + mint, 120, lambda: pipeline.get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report"))
    except Exception as x:
        return {"status": "unknown", "label": "n/a (rugcheck unavailable)", "pct": None, "src": "rugcheck", "err": str(x)[:80]}
    ms = d.get("markets") or []
    m = next((x for x in ms if pair and (x.get("pubkey") or "").lower() == pair.lower()), None)
    if m is None:  # fall back to the market with most locked/total LP value
        ms2 = [x for x in ms if x.get("marketType") not in CLMM]
        m = max(ms2 or ms, key=lambda x: ((x.get("lp") or {}).get("quoteUSD") or 0) + ((x.get("lp") or {}).get("lpLockedUSD") or 0), default=None)
    if not m: return {"status": "unknown", "label": "n/a (no market in rugcheck)", "pct": None, "src": "rugcheck"}
    lp, mt = m.get("lp") or {}, m.get("marketType") or "?"
    if mt in CLMM:
        return {"status": "clmm", "label": "n/a: concentrated-liquidity pool (no LP token)", "pct": None, "market": mt, "src": "rugcheck"}
    pct = lp.get("lpLockedPct"); pct = round(pct, 1) if pct is not None else None
    lockers = [v for v in (d.get("lockers") or {}).values() if isinstance(v, dict)]
    now = time.time()
    unl = sorted(int(v["unlockDate"]) for v in lockers if v.get("unlockDate"))
    fut = [u for u in unl if u > now]
    lockedUsd = sum(float(v.get("usdcLocked") or 0) for v in lockers)
    base = {"pct": pct, "market": mt, "src": "rugcheck", "lockedUsd": round(lockedUsd) or None,
            "unlock": fut[0] if fut else (unl[-1] if unl else None), "lpUsd": round(lp.get("lpLockedUSD") or 0) or None}
    date = lambda t: time.strftime("%d %b %Y", time.gmtime(t))
    if pct is None: return {**base, "status": "unknown", "label": "n/a"}
    if lockers:
        lockPct = round(min(pct, lockedUsd / ((lp.get("quoteUSD") or 0) * 2) * 100), 1) if lp.get("quoteUSD") else None
        u = f" · unlock {date(base['unlock'])}" + (" (passed)" if base["unlock"] and base["unlock"] <= now else "") if base["unlock"] else ""
        if lockPct is not None and pct - lockPct >= 5:
            return {**base, "status": "burned+locked", "lockPct": lockPct, "label": f"🔥🔒 Burned+locked {pct}% (locker ~{lockPct}%{u})"}
        return {**base, "status": "locked", "lockPct": lockPct, "label": f"🔒 Locked {pct}%{u}"}
    if pct >= 95:
        note = " (PumpSwap migration burns LP)" if mt == "pump_fun_amm" else ""
        return {**base, "status": "burned", "label": f"🔥 Burned {pct}%{note}"}
    if pct >= 5: return {**base, "status": "partial", "label": f"⚠️ Only {pct}% burned/locked"}
    return {**base, "status": "unlocked", "label": f"❌ Not locked/burned ({pct}%)"}

def monitor(journal, days=7, per_run=15, now=None):
    """Re-check LP for signals from the last `days` (oldest-checked first, `per_run` per run).
    Events (once each, stored in e['lpEvents']): unlocked (burned/locked % drops >=20 pts from the max seen),
    pulled (DexScreener liquidity < 5% of the max seen), unlockPassed (a locker unlock date has passed)."""
    now = now or time.time()
    es = [e for e in journal if e.get("chain") == "solana" and now - e["t0"] < days * 86400]
    es.sort(key=lambda e: (e.get("lp") or {}).get("t", 0))
    es = es[:per_run]
    if not es: return []
    import journal as J
    px = J.prices([e["mint"] for e in es])
    notes = []
    for e in es:
        p = px.get(e["mint"]) or {}
        s = status(e["mint"], p.get("pairAddress"), p.get("dexId"))
        old = e.get("lp") or {}
        liq = (p.get("liquidity") or {}).get("usd")
        rec = {"status": s["status"], "label": s["label"], "pct": s.get("pct"), "unlock": s.get("unlock"), "t": int(now),
               "pctMax": max(filter(lambda v: v is not None, [old.get("pctMax"), s.get("pct")]), default=None),
               "liq": liq, "liqMax": max(filter(None, [old.get("liqMax"), liq]), default=None)}
        ev = e.setdefault("lpEvents", {})
        def fire(k, text):
            if k in ev: return
            ev[k] = int(now); notes.append(("lp", e, text))
        if old and s["status"] not in ("unknown",):  # need a previous reading to compare
            if rec["pctMax"] is not None and s.get("pct") is not None and rec["pctMax"] >= 50 and s["pct"] <= rec["pctMax"] - 20:
                fire("unlocked", f"⚠️ LIQUIDITY UNLOCKED: ${e['symbol']} LP burned/locked fell {rec['pctMax']}% → {s['pct']}%")
            if liq is not None and rec["liqMax"] and rec["liqMax"] >= 2000 and liq < 0.05 * rec["liqMax"]:
                fire("pulled", f"⚠️ LIQUIDITY PULLED: ${e['symbol']} liquidity ${pipeline_fmt(rec['liqMax'])} → ${pipeline_fmt(liq)}")
            if old.get("unlock") and old["unlock"] > (old.get("t") or 0) and old["unlock"] <= now:
                fire("unlockPassed", f"⚠️ LIQUIDITY UNLOCK DATE PASSED: ${e['symbol']} lock expired "
                                     f"{time.strftime('%d %b %H:%M', time.gmtime(old['unlock'] + 3600))} WAT; LP can now be withdrawn")
        e["lp"] = rec
        time.sleep(0.3)
    return notes

def pipeline_fmt(n):
    return f"{n/1e6:.2f}M" if n >= 1e6 else f"{n/1e3:.1f}K" if n >= 1e3 else f"{n:.0f}"
