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
    """{funder, txCount, firstTs}: earliest SOL inflow source (or first fee payer); scans up to 3k signatures."""
    def f():
        before, oldest, n, ts = None, None, 0, None
        for _ in range(3):
            sigs = rpc("getSignaturesForAddress", [wallet, {"limit": 1000, **({"before": before} if before else {})}])
            if not sigs: break
            oldest = sigs[-1]["signature"]; before = oldest; n += len(sigs); ts = sigs[-1].get("blockTime")
            if len(sigs) < 1000: break
        else:
            return {"funder": None, "txCount": n, "firstTs": None}  # too old/active to resolve cheaply
        return {"funder": _funder(wallet, oldest), "txCount": n, "firstTs": ts}
    return cached("winfo:" + wallet, 86400, f)

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
            "estFeesSol": estFeesSol, "priceUsd": pu or None, "socials": list(dict.fromkeys(s.split(" ")[0] for s in socials)), "websites": list(dict.fromkeys(webs)), "checks": checks, "cheapPass": all(checks.values()),
            "links": links(p["chainId"], a, p.get("url"), p["baseToken"]["symbol"])}

def links(chain, a, ds_url, sym):
    c = "solana" if chain == "solana" else chain
    return {"dexscreener": ds_url, "pumpfun": f"https://pump.fun/coin/{a}" if chain == "solana" else None,
            "bubblemaps": f"https://v2.bubblemaps.io/map?address={a}&chain={c}",
            "insightx": f"https://app.insightx.network/bubblemaps/{'solana' if chain=='solana' else chain}/{a}",
            "x_search": f"https://x.com/search?q=%24{sym}&f=live", "tiktok": f"https://www.tiktok.com/search?q={sym}"}
