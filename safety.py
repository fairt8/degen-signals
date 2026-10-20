"""Combined free safety check (replaces the GMGN line when no GMGN_API_KEY).
Sources: rugcheck report (authorities, transfer fee, danger risks, rugged flag, insiders), LP status,
Solana RPC holder/dev analysis, InsightX DEX metrics (snipers/bundlers/insiders/clusters) when INSIGHTX_API_KEY is set,
GMGN pct when GMGN_API_KEY is set. Never invents values: a check without data is skipped."""

def check(r, C):
    """C = config.safety. Returns {status PASS/WARN/FAIL, pass, fails, warns, oks, sources, pct, scoreAdj}."""
    fails, warns, oks, src = [], [], [], []
    rc = r.get("rugcheck") or {}
    if rc:
        src.append("rugcheck")
        if rc.get("mintAuth"): fails.append("mint authority not revoked")
        if rc.get("freezeAuth"): fails.append("freeze authority not revoked")
        if not rc.get("mintAuth") and not rc.get("freezeAuth"): oks.append("mint+freeze revoked")
        if rc.get("rugged"): fails.append("rugcheck: rugged")
        if (rc.get("transferFeePct") or 0) > 0: fails.append(f"transfer tax {rc['transferFeePct']}%")
        for n in (rc.get("danger") or [])[:2]: warns.append(f"rugcheck: {n}")
        if (rc.get("graphInsiders") or 0) >= C["graphInsidersWarn"]: warns.append(f"{rc['graphInsiders']} insider wallets (rugcheck graph)")
    lp = (r.get("lp") or {}).get("status")
    if lp:
        src.append("LP")
        if lp in ("burned", "locked", "burned+locked"): oks.append(f"LP {lp}")
        elif lp == "unlocked": fails.append("LP not locked/burned")
        elif lp == "partial": warns.append((r.get("lp") or {}).get("label", "LP partial").replace("⚠️ ", ""))
    d = r.get("dev") or {}
    if d.get("wallet"):
        src.append("RPC dev")
        if d.get("rugHistory"): fails.append("dev rug history")
        if (d.get("holdPct") or 0) > C["maxDevPct"]: warns.append(f"dev holds {d['holdPct']}%")
        if d.get("funderSharedWithTopHolders"): warns.append("dev funder linked to top holders")
    # holder-composition % : InsightX > GMGN > rugcheck/RPC
    ix = r.get("insightx") or {}
    g = (r.get("gmgn") or {}).get("pct") or {} if (r.get("gmgn") or {}).get("status") in ("PASS", "FAIL") else {}
    H = r.get("holders") or {}
    pct = {}
    if ix and not ix.get("error"):
        src.append("InsightX"); pct.update({k: ix[k] for k in ("sniper", "bundler", "insider", "dev", "cluster") if k in ix})
    for k in ("sniper", "bundler", "insider", "fresh"):
        if k not in pct and g.get(k) is not None: pct[k] = g[k]
    if g: src.append("GMGN")
    if "insider" not in pct and H.get("insiderPct") is not None: pct["insider"] = H["insiderPct"]
    if "cluster" not in pct and r.get("clusterPct") is not None: pct["cluster"] = r["clusterPct"]; src.append("RPC funders")
    for k, cap, name in (("sniper", C["maxSniperPct"], "snipers"), ("bundler", C["maxBundlerPct"], "bundlers"),
                         ("insider", C["maxInsiderPct"], "insiders"), ("cluster", C["maxClusterPct"], "clustered")):
        v = pct.get(k)
        if v is None: continue
        if v > cap: fails.append(f"{name} {v:.1f}% > {cap}%")
        elif v > cap * 0.6: warns.append(f"{name} {v:.1f}%")
    combo = sum(pct.get(k) or 0 for k in ("sniper", "bundler", "insider"))
    if combo > C["maxComboPct"]: fails.append(f"sniper+bundler+insider {combo:.1f}% > {C['maxComboPct']}%")
    bh = r.get("behaviour") or {}
    if (bh.get("botPct") or 0) >= C["botPctFail"]: fails.append(f"{bh['botPct']}% bot-like top holders")
    if not src: return {"status": "n/a", "pass": None, "fails": [], "warns": [], "oks": [], "sources": [], "pct": {}, "scoreAdj": 0}
    st = "FAIL" if fails else "WARN" if warns else "PASS"
    adj = C["failPenalty"] if fails else C["warnPenalty"] if warns else 0
    return {"status": st, "pass": not fails, "fails": fails, "warns": warns, "oks": oks,
            "sources": list(dict.fromkeys(src)), "pct": {k: round(v, 1) for k, v in pct.items()}, "scoreAdj": adj}

def line(s):
    if not s or s.get("status") in (None, "n/a"): return "Safety check: n/a"
    icon = {"PASS": "✅", "WARN": "🟠", "FAIL": "❌"}[s["status"]]
    why = s["fails"] if s["status"] == "FAIL" else s["warns"] if s["status"] == "WARN" else s["oks"]
    return f"Safety check: {s['status']} {icon} — " + ("; ".join(why[:3]) or "no red flags") + f" [{' · '.join(s['sources'])}]"

def reasons(s):
    if not s: return []
    return (s.get("fails") or []) + (s.get("warns") or []) + (s.get("oks") or [])
