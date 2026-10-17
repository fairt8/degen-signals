"""Shared 5R pipeline: DexScreener candidates, filters, holders (rugcheck), clusters (InsightX/Bubblemaps/RPC funders)."""
import json, math, os, re, time, urllib.request, concurrent.futures as cf
DS = "https://api.dexscreener.com"
RPC = os.environ.get("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_cache = {}  # key -> (ts, value)

def get(url, headers=None, data=None, timeout=15):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})}, data=data)
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())

def cached(key, ttl, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl: return hit[1]
    v = fn(); _cache[key] = (time.time(), v); return v

def load_config(path=os.path.join(os.path.dirname(__file__), "config.js")):
    """Reads the filters block from config.js (JS object literal -> JSON)."""
    src = open(path).read()
    m = re.search(r"filters\s*=\s*(\{.*?\});", src, re.S)
    body = re.sub(r"//[^\n]*", "", m.group(1))
    body = re.sub(r"(\w+)\s*:", r'"\1":', body)
    body = re.sub(r",\s*}", "}", body)
    return json.loads(body)

# ---------- RPC funder clustering ----------
def rpc(method, params):
    for attempt in range(4):
        try:
            r = get(RPC, {"Content-Type": "application/json"},
                    json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode())
            if "error" in r: raise RuntimeError(r["error"])
            return r["result"]
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return None

def first_funder(wallet):
    return wallet_info(wallet)["funder"]

def wallet_info(wallet):
    """{funder, txCount, firstTs, maxTxDay}: earliest SOL inflow source (or first fee payer); scans up to 3k signatures.
    maxTxDay = most signatures in any single UTC day among the scanned ones (bot heuristic, no extra RPC calls)."""
    def f():
        before, oldest, n, ts, days = None, None, 0, None, {}
        for _ in range(3):
            sigs = rpc("getSignaturesForAddress", [wallet, {"limit": 1000, **({"before": before} if before else {})}])
            if not sigs: break
            for s in sigs:
                if s.get("blockTime"): days[s["blockTime"] // 86400] = days.get(s["blockTime"] // 86400, 0) + 1
            oldest = sigs[-1]["signature"]; before = oldest; n += len(sigs); ts = sigs[-1].get("blockTime")
            if len(sigs) < 1000: break
        else:
            return {"funder": None, "txCount": n, "firstTs": None, "maxTxDay": max(days.values()) if days else None}
        return {"funder": _funder(wallet, oldest), "txCount": n, "firstTs": ts, "maxTxDay": max(days.values()) if days else None}
    return cached("winfo2:" + wallet, 86400, f)

def _funder(wallet, oldest):
        if not oldest: return None
        tx = rpc("getTransaction", [oldest, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
        if not tx: return None
        msg = tx["transaction"]["message"]
        for ins in msg.get("instructions", []) + [i for g in (tx.get("meta") or {}).get("innerInstructions", []) for i in g["instructions"]]:
            p = ins.get("parsed")
            if isinstance(p, dict) and p.get("type") in ("transfer", "createAccount") and p["info"].get("destination", p["info"].get("newAccount")) == wallet:
                return p["info"].get("source")
        payer = msg["accountKeys"][0]["pubkey"]
        return payer if payer != wallet else None

def holders_and_clusters(mint, cfg=None):
    """Returns {top10Pct, clusterPct, clusterSource, clusters, ...}. Cached 15 min."""
    def f():
        out = {"mint": mint}
        d = get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report")
        pools = set((d.get("knownAccounts") or {}).keys())
        for m in d.get("markets") or []:
            pools.update([m.get("pubkey"), m.get("liquidityA"), m.get("liquidityB"), (m.get("lp") or {}).get("lpMint")])
        hs = [h for h in (d.get("topHolders") or []) if h.get("owner") not in pools and h.get("address") not in pools]
        top = hs[:10]
        out.update(top5=[round(h.get("pct", 0), 1) for h in hs[:5]], top5Pct=round(sum(h.get("pct", 0) for h in hs[:5]), 1),
                   whalePct=round(sum(h.get("pct", 0) for h in hs if h.get("pct", 0) >= 2), 1),  # non-pool wallets >=2% (rugcheck top holders)
                   insiderPctRugcheck=round(sum(h.get("pct", 0) for h in hs if h.get("insider")), 1))
        out.update(top10Pct=round(sum(h.get("pct", 0) for h in top), 2), totalHolders=d.get("totalHolders"),
                   excludedPools=len(d.get("topHolders") or []) - len(hs))
        sources = {}
        # 1) InsightX (needs INSIGHTX_API_KEY)
        k = os.environ.get("INSIGHTX_API_KEY")
        if k:
            try:
                r = get(f"https://api.insightx.network/dex-metrics/v1/sol/{mint}/clusters", {"X-API-Key": k})
                pct = r.get("total_cluster_percentage") or r.get("totalClusterPercentage")
                if pct is None:
                    pct = sum(c.get("percentage", 0) for c in r.get("clusters", []) if not set(c.get("tags") or []) & {"liquidity_pool", "exchange"})
                sources["insightx"] = round(float(pct), 2)
            except Exception as e: out["insightxError"] = str(e)[:120]
        # 2) Bubblemaps (needs BUBBLEMAPS_API_KEY)
        k = os.environ.get("BUBBLEMAPS_API_KEY")
        if k:
            try:
                r = get(f"https://api.bubblemaps.io/v0/tokens/map/solana/{mint}?return_clusters=true", {"X-ApiKey": k})
                cl = [c for c in r.get("clusters", []) if len(c.get("holders", [])) >= 2]
                sources["bubblemaps"] = round(sum(c.get("share", 0) for c in cl) * (100 if all(c.get("share", 0) <= 1 for c in cl) else 1), 2)
            except Exception as e: out["bubblemapsError"] = str(e)[:120]
        # 3) rugcheck insider graph
        ins = sum(h.get("pct", 0) for h in hs if h.get("insider"))
        sources["rugcheck_insiders"] = round(ins, 2)
        supply = float((d.get("token") or {}).get("supply") or 0)
        if supply:
            sources["rugcheck_insider_networks"] = round(sum(n.get("currentHolding", 0) for n in d.get("insiderNetworks") or []) / supply * 100, 2)
        out["insiderNetworks"] = [{"id": n.get("id"), "size": n.get("size"), "type": n.get("type")} for n in d.get("insiderNetworks") or []]
        out["maxSingleHolderPct"] = round(max([h.get("pct", 0) for h in top] or [0]), 2)
        out["dev"] = dev_info(d, supply)
        out["rugcheckInsiderGraph"] = bool(d.get("graphInsidersDetected"))
        # 4) free fallback: common first-funder of top-10 holders via public RPC
        with cf.ThreadPoolExecutor(3) as ex:
            infos = list(ex.map(lambda h: wallet_info(h.get("owner")), top))
        funders = [i["funder"] for i in infos]
        out["holderWallets"] = [{"owner": h.get("owner"), "pct": round(h.get("pct", 0), 2), "firstTs": i.get("firstTs"),
                                 "txCount": i.get("txCount"), "maxTxDay": i.get("maxTxDay"), "old": i.get("firstTs") is None and (i.get("txCount") or 0) >= 3000}
                                for h, i in zip(top, infos)]
        out["freshWallets"] = sum(1 for i in infos if i["txCount"] and i["txCount"] < 15)  # top-10 holders with <15 txs ever
        dv = out["dev"]
        if dv.get("wallet"):
            dv.update({k: v for k, v in wallet_info(dv["wallet"]).items() if k != "txCount"}, devTxCount=wallet_info(dv["wallet"])["txCount"])
            dv["funderSharedWithTopHolders"] = bool(dv.get("funder")) and (dv["funder"] in funders or dv["wallet"] in funders)
        groups = {}
        for h, fu in zip(top, funders):
            if fu: groups.setdefault(fu, []).append(h)
        clusters = [{"funder": fu, "wallets": [h["owner"] for h in g], "pct": round(sum(h["pct"] for h in g), 2)}
                    for fu, g in groups.items() if len(g) >= 2]
        sources["rpc_common_funder"] = round(sum(c["pct"] for c in clusters), 2)
        out["funderResolved"] = sum(1 for x in funders if x)
        out["clusters"] = clusters
        out["clusterSources"] = sources
        best = max(sources, key=sources.get)
        out["clusterPct"], out["clusterSource"] = sources[best], best
        return out
    return cached("hc:" + mint, 900, f)

# ---------- dev (creator) lookup ----------
def dev_info(d, supply):
    """Creator wallet stats from the rugcheck report (free). Migration/rug are heuristics on current market cap."""
    w = d.get("creator")
    toks = d.get("creatorTokens") or []
    prior = [t for t in toks if t.get("mint") != d.get("mint")]
    mcs = [t.get("marketCap") or 0 for t in prior]
    bal = float(d.get("creatorBalance") or 0)
    risks = [r.get("name") for r in d.get("risks") or []]
    return {"wallet": w, "holdPct": round(bal / supply * 100, 2) if supply else None, "sold": bal == 0 or (supply and bal / supply < 1e-4),
            "priorTokens": len(prior), "priorMigrated": sum(1 for m in mcs if m >= 69000),
            "priorDead": sum(1 for m in mcs if m < 5000), "bestPriorMcap": round(max(mcs), 0) if mcs else None,
            "rugHistory": any("rugged" in (r or "").lower() for r in risks),
            "launchpad": (d.get("launchpad") or {}).get("name"), "riskNames": risks,
            "links": {"solscan": f"https://solscan.io/account/{w}" if w else None,
                      "pumpfun": f"https://pump.fun/profile/{w}" if w else None}}

def dev_score(dev, W):
    """Optional bonus/penalty (not a 5R filter). W = config devScore weights."""
    if not dev or not dev.get("wallet"): return 0, []
    pts, why = 0, []
    def add(p, msg): nonlocal pts; pts += p; why.append(f"{p:+d} {msg}")
    if dev.get("rugHistory"): add(W["rugHistory"], "dev rug history")
    if dev.get("priorMigrated"): add(W["migratedBonus"], f"dev migrated {dev['priorMigrated']} prior")
    if dev.get("priorTokens", 0) >= W["serialLauncherMin"] and dev.get("priorDead", 0) / max(1, dev["priorTokens"]) > 0.8:
        add(W["serialLauncher"], f"serial launcher ({dev['priorDead']}/{dev['priorTokens']} dead)")
    if (dev.get("holdPct") or 0) > W["holdPctMax"]: add(W["highHold"], f"dev holds {dev['holdPct']}%")
    if dev.get("funderSharedWithTopHolders"): add(W["sharedFunder"], "dev funder linked to top holders")
    return pts, why

# ---------- behaviour metrics, score, findings ----------
def behaviour(r, h, B):
    """Bot / serial-flipper / fresh-wallet shares of sampled top-10 holders. GMGN wallet activity when a key is set,
    else Solana RPC signatures (bots + fresh only; flippers n/a). Shares are % of sampled wallets."""
    ws = (h or {}).get("holderWallets") or []
    if not ws: return {"sampled": 0, "source": "n/a", "botPct": None, "flipperPct": None, "freshPct": None}
    import gmgn
    launch = time.time() - r["ageH"] * 3600 if r.get("ageH") is not None else None
    gw = gmgn.wallet_behaviour([w["owner"] for w in ws], r["mint"]) if os.environ.get("GMGN_API_KEY") else {}
    bots = flips = fresh = 0; nb = nf = nfr = 0
    for w in ws:
        g = gw.get(w["owner"])
        if g:  # GMGN: 15+ distinct tokens or 100+ txns in a day; flipper: 10+ tokens bought on entry day
            nb += 1; bots += (g["maxTokensDay"] >= B["botTokensDay"] or g["maxTxDay"] >= B["botTxDay"])
            if g.get("entryDayTokens") is not None: nf += 1; flips += g["entryDayTokens"] >= B["flipperTokens"]
        elif w.get("maxTxDay") is not None:
            nb += 1; bots += w["maxTxDay"] >= B["botTxDay"]
        if launch:
            if w.get("firstTs"): nfr += 1; fresh += w["firstTs"] >= launch - 7 * 86400
            elif w.get("old"): nfr += 1  # 3000+ txs history -> not fresh
    pc = lambda a, b: round(a / b * 100) if b else None
    return {"sampled": len(ws), "source": "gmgn" if gw else "rpc", "botPct": pc(bots, nb), "botN": f"{bots}/{nb}",
            "flipperPct": pc(flips, nf), "flipperN": f"{flips}/{nf}", "freshPct": pc(fresh, nfr), "freshN": f"{fresh}/{nfr}"}

def base_score(p, narr_count, F):
    """Same 0-100 heuristic as the web UI (app.js build())."""
    cl = lambda x, a, b: max(a, min(b, x))
    liq = (p.get("liquidity") or {}).get("usd", 0); v = p.get("volume") or {}; pc = p.get("priceChange") or {}
    tx = (p.get("txns") or {}).get("h1") or {"buys": 0, "sells": 0}; ratio = (tx["buys"] + 1) / (tx["sells"] + 1)
    mc = p.get("marketCap") or p.get("fdv") or 0
    ageH = (time.time() * 1000 - p["pairCreatedAt"]) / 36e5 if p.get("pairCreatedAt") else None
    s = cl(math.log10(liq + 1) / 6 * 20, 0, 20) + cl(math.log10(v.get("h1", 0) + 1) / 6 * 12, 0, 12) + cl(math.log10(v.get("m5", 0) + 1) / 5 * 6, 0, 6)
    s += cl(((pc.get("h1") or 0) + 20) / 60 * 8, 0, 8) + cl(((pc.get("m5") or 0) + 10) / 30 * 6, 0, 6) + cl((ratio - 0.5) / 1.5 * 14, 0, 14)
    s += 3 if ageH is None else 2 if ageH < 0.5 else 8 if ageH < 6 else 6 if ageH < 72 else 3
    s += 2 if mc < 1e4 else 8 if mc < 1e6 else 6 if mc < 2e7 else 3
    s += cl(((p.get("boosts") or {}).get("active") or 0) / 50 * 6, 0, 6) + cl(narr_count * 6, 0, 12)
    if liq < 5000: s -= 15
    if ratio < 0.8: s -= 10
    return round(cl(s, 0, 100))

def findings(r, B):
    """[(severity, text)] red first. Only from real data present on r."""
    f = []
    def add(sev, msg): f.append((sev, msg))
    bh, d, h, g = r.get("behaviour") or {}, r.get("dev") or {}, r.get("holders") or {}, (r.get("gmgn") or {}).get("pct") or {}
    for key, name, red, amb in (("botPct", "bot-like holders", B["botPctRed"], B["botPctAmber"]),
                                ("flipperPct", "serial flippers among holders", B["flipperPctRed"], B["flipperPctAmber"]),
                                ("freshPct", "fresh wallets (first tx ≤7d before launch)", B["freshPctRed"], B["freshPctAmber"])):
        v = bh.get(key)
        if v is not None and v >= amb: add("red" if v >= red else "amber", f"{v}% {name} ({bh.get(key[:-3] + 'N')} of top holders)")
    vl = r.get("volLiq")
    if vl is not None and vl >= B["volLiqAmber"]: add("red" if vl >= B["volLiqRed"] else "amber", f"volume {vl}x liquidity, possibly inflated")
    if d.get("rugHistory"): add("red", "dev has rug history")
    if d.get("priorTokens", 0) >= 3 and d.get("priorDead", 0) / max(1, d["priorTokens"]) > 0.8:
        add("red", f"dev launched {d['priorTokens']} tokens, {d['priorDead']} dead")
    if (d.get("holdPct") or 0) > 5: add("amber", f"dev still holds {d['holdPct']}%")
    if (r.get("clusterPct") or 0) > 15: add("amber", f"{r['clusterPct']}% supply clustered")
    if (r.get("liqPctMc") or 100) < 10: add("amber", f"liquidity only {r['liqPctMc']}% of MC")
    if (h.get("top5Pct") or 0) > 30: add("amber", f"top 5 hold {h['top5Pct']}%")
    if (g.get("bundler") or 0) > 15: add("red" if g["bundler"] > 25 else "amber", f"bundlers hold {g['bundler']}%")
    return sorted(f, key=lambda x: x[0] != "red")

def final_score(r, B):
    """Base + dev + GMGN adj; capped when behaviour alarms fire. Sets r['score'], r['scoreUncapped'], r['scoreCapped']."""
    raw = max(0, min(100, (r.get("baseScore") or 0) + (r.get("devScore") or 0) + (r.get("gmgnScore") or 0)))
    bh, d = r.get("behaviour") or {}, r.get("dev") or {}
    alarm = ((bh.get("botPct") or 0) >= B["botPctRed"] or (bh.get("flipperPct") or 0) >= B["flipperPctRed"]
             or (d.get("priorTokens", 0) >= 3 and d.get("priorDead", 0) / max(1, d.get("priorTokens") or 1) > 0.8) or d.get("rugHistory"))
    r["scoreUncapped"] = raw
    r["scoreCapped"] = bool(alarm and raw > B["scoreCap"])
    r["score"] = B["scoreCap"] if r["scoreCapped"] else raw

# ---------- DexScreener orders (Dex Paid / CTO) & narratives ----------
def dex_orders(chain, mint):
    """{dexPaid, ctoOrder, boosts} from /orders/v1. None values if the call fails (never guessed)."""
    try:
        d = get(f"{DS}/orders/v1/{chain}/{mint}")
        orders = d.get("orders", d if isinstance(d, list) else [])
        ok = [o for o in orders if o.get("status") == "approved"]
        return {"dexPaid": any(o.get("type") == "tokenProfile" for o in ok),
                "ctoOrder": any(o.get("type") == "communityTakeover" for o in ok),
                "boosts": len(d.get("boosts") or []) if isinstance(d, dict) else 0}
    except Exception:
        return {"dexPaid": None, "ctoOrder": None, "boosts": None}

_NARR = None
def narratives(text):
    """Keyword match against SIGNAL_CONFIG.narratives in config.js (same lists as the web UI)."""
    global _NARR
    if _NARR is None:
        try:
            src = open(os.path.join(os.path.dirname(__file__), "config.js")).read()
            body = re.search(r"narratives:\s*(\{.*?\})\s*,\s*\n", src, re.S).group(1)
            _NARR = json.loads(body)
        except Exception:
            _NARR = {}
    t = (text or "").lower()
    return [n for n, kws in _NARR.items() if any(re.search(r"\b" + re.escape(k), t) for k in kws)]

# ---------- candidates & filters ----------
SOCIAL_RE = re.compile(r"twitter|telegram|discord|x\.com|t\.me|community", re.I)

def candidates():
    meta = {}
    def safe(u, d):
        try: return get(u)
        except Exception: return d
    for p in safe(DS + "/token-profiles/latest/v1", []) + safe(DS + "/token-boosts/latest/v1", []) + safe(DS + "/token-boosts/top/v1", []):
        k = p["chainId"] + ":" + p["tokenAddress"]; m = meta.setdefault(k, {"links": [], "description": ""})
        m["description"] = m["description"] or (p.get("description") or "").strip(); m["links"] += p.get("links") or []
        if p.get("cto"): m["cto"] = True
    for p in safe(DS + "/community-takeovers/latest/v1", []):
        k = p["chainId"] + ":" + p["tokenAddress"]; m = meta.setdefault(k, {"links": [], "description": ""})
        m["cto"] = True; m["links"] += p.get("links") or []
        m["description"] = m["description"] or (p.get("description") or "").strip()
    pairs = []
    for q in ["pumpfun", "pumpswap", "pump", "solana", "meme", "ai"]:
        pairs += safe(f"{DS}/latest/dex/search?q={q}", {}).get("pairs") or []
    by = {}
    for k in meta: c, a = k.split(":"); by.setdefault(c, []).append(a)
    for c, lst in by.items():
        for i in range(0, len(lst), 30): pairs += safe(f"{DS}/tokens/v1/{c}/{','.join(lst[i:i+30])}", [])
    best = {}
    for p in pairs:
        k = p["chainId"] + ":" + p["baseToken"]["address"]
        if k not in best or (p.get("liquidity") or {}).get("usd", 0) > (best[k].get("liquidity") or {}).get("usd", 0): best[k] = p
    return [(p, meta.get(k, {"links": [], "description": ""})) for k, p in best.items()]

def evaluate(p, m, F, now=None):
    now = now or time.time() * 1000
    socials = [s.get("url") + " " + s.get("type", "") for s in (p.get("info") or {}).get("socials") or []]
    socials += [(l.get("url") or "") + " " + (l.get("type") or l.get("label") or "") for l in m["links"] if SOCIAL_RE.search((l.get("url") or "") + (l.get("type") or "") + (l.get("label") or ""))]
    webs = [w["url"] for w in (p.get("info") or {}).get("websites") or []] + [l["url"] for l in m["links"] if not SOCIAL_RE.search((l.get("url") or "") + (l.get("type") or "") + (l.get("label") or ""))]
    w = F["window"]; tx = (p.get("txns") or {}).get(w) or {"buys": 0, "sells": 0}
    vol = (p.get("volume") or {}).get(w, 0); mc = p.get("marketCap") or p.get("fdv") or 0
    liq = (p.get("liquidity") or {}).get("usd", 0); pc = p.get("priceChange") or {}
    c5, c1 = pc.get("m5", 0) or 0, pc.get("h1", 0) or 0
    ageH = (now - p["pairCreatedAt"]) / 36e5 if p.get("pairCreatedAt") else None
    st = " ".join(socials).lower()
    hasX, hasTg = bool(re.search(r"twitter|x\.com", st)), bool(re.search(r"telegram|t\.me", st))
    ratio = F.get("sellBuyRatioMin", 0.6)
    pu, pn = float(p.get("priceUsd") or 0), float(p.get("priceNative") or 0)
    solUsd = pu / pn if pn and (p.get("quoteToken") or {}).get("symbol") in ("SOL", "WSOL") else None
    estFeesSol = round(((p.get("volume") or {}).get("h24", 0) * F.get("feeRate", 0.0125)) / solUsd, 2) if solUsd else None
    checks = {
        "mcap": F["mcapMin"] <= mc <= F["mcapMax"],
        "liq": liq >= F["liqMin"] and mc > 0 and liq / mc * 100 >= F["liqPctMcapMin"],
        "age": ageH is not None and ageH * 60 >= F["ageMinMin"] and ageH <= F["ageMaxH"],
        "volMcap": mc > 0 and vol >= F["volToMcapMin"] * mc,
        "txns": tx["buys"] + tx["sells"] >= F["txnsMin"],
        "sellsVsBuys": (not F["requireMoreSellers"]) or tx["sells"] >= ratio * tx["buys"],
        "ch5": F["ch5Min"] < c5 < F["ch5Max"], "ch1": c1 < F["ch1Max"],
        "socials": bool(socials) and (not F["requireX"] or hasX) and (not F["requireTgOrWeb"] or hasTg or bool(webs)),
        "description": (not F["requireDescription"]) or bool(m["description"]),
    }
    a = p["baseToken"]["address"]
    return {"symbol": p["baseToken"]["symbol"], "name": p["baseToken"]["name"], "chain": p["chainId"], "mint": a,
            "dex": p.get("dexId"), "mcap": mc, "liq": liq, "vol": vol, "window": w, "buys": tx["buys"], "sells": tx["sells"],
            "ch5m": c5, "ch1h": c1, "ageH": round(ageH, 2) if ageH else None, "description": m["description"][:200],
            "ctoProfile": bool(m.get("cto")), "volLiq": round((p.get("volume") or {}).get("h24", 0) / liq, 1) if liq else None,
            "baseScore": base_score(p, len(narratives(f"{p['baseToken']['name']} {p['baseToken']['symbol']} {m['description']}")), F), "liqPctMc": round(liq / mc * 100, 1) if mc else None,
            "ch24h": pc.get("h24"), "narratives": narratives(f"{p['baseToken']['name']} {p['baseToken']['symbol']} {m['description']}"),
            "estFeesSol": estFeesSol, "priceUsd": pu or None, "socials": list(dict.fromkeys(s.split(" ")[0] for s in socials)), "websites": list(dict.fromkeys(webs)), "checks": checks, "cheapPass": all(checks.values()),
            "links": links(p["chainId"], a, p.get("url"), p["baseToken"]["symbol"])}

def links(chain, a, ds_url, sym):
    c = "solana" if chain == "solana" else chain
    return {"dexscreener": ds_url, "pumpfun": f"https://pump.fun/coin/{a}" if chain == "solana" else None,
            "bubblemaps": f"https://v2.bubblemaps.io/map?address={a}&chain={c}",
            "insightx": f"https://app.insightx.network/bubblemaps/{'solana' if chain=='solana' else chain}/{a}",
            "x_search": f"https://x.com/search?q=%24{sym}&f=live", "tiktok": f"https://www.tiktok.com/search?q={sym}"}
