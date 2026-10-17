"""GMGN official OpenAPI (https://openapi.gmgn.ai) - optional smart-money / sniper / bundler layer.
Needs GMGN_API_KEY (free key from https://gmgn.ai/ai). No key -> status SKIPPED. Read-only routes only.
Auth: header X-APIKEY + query timestamp + client_id (uuid). Free plan ~5 req/s -> we pace calls."""
import json, os, time, uuid, urllib.error, urllib.parse, urllib.request
HOST = os.environ.get("GMGN_HOST", "https://openapi.gmgn.ai")
TAGS = ["smart_degen", "renowned", "sniper", "bundler", "fresh_wallet", "rat_trader"]
_cache = {}

def _get(path, **q):
    key = os.environ.get("GMGN_API_KEY")
    q.update(timestamp=int(time.time()), client_id=str(uuid.uuid4()))
    req = urllib.request.Request(f"{HOST}{path}?{urllib.parse.urlencode(q)}",
                                 headers={"X-APIKEY": key, "User-Agent": "degen-signals/1.0", "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            d = json.loads(urllib.request.urlopen(req, timeout=15).read())
            if d.get("code") not in (0, None): raise RuntimeError(f"gmgn code {d.get('code')}: {d.get('message')}")
            return (d.get("data") or {}).get("list") or []
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2: time.sleep(2); continue
            raise RuntimeError(f"HTTP {e.code} {e.read()[:120]!r}")

def analyze(mint, C, chain="sol"):
    """Returns {status: PASS/FAIL/SKIPPED/ERROR, pass, reasons, scoreAdj, counts, pct}. Cached 10 min."""
    if not os.environ.get("GMGN_API_KEY"):
        return {"status": "SKIPPED", "pass": None, "reasons": ["no GMGN_API_KEY"], "scoreAdj": 0}
    hit = _cache.get(mint)
    if hit and time.time() - hit[0] < 600: return hit[1]
    try:
        lists = {}
        for t in TAGS:
            lists[t] = [h for h in _get("/v1/market/token_top_holders", chain=chain, address=mint, limit=100, tag=t)
                        if h.get("addr_type") != 2]  # 2 = pool / AMM account
            time.sleep(0.3)
    except Exception as e:
        return {"status": "ERROR", "pass": None, "reasons": [str(e)[:150]], "scoreAdj": 0}
    held = lambda L: [h for h in L if (h.get("amount_percentage") or 0) > 0]
    pct = lambda L: round(sum(h.get("amount_percentage") or 0 for h in held(L)) * 100, 2)
    counts = {t: {"holding": len(held(L)), "seen": len(L)} for t, L in lists.items()}
    combo = {}
    for t in ("sniper", "bundler", "fresh_wallet"):
        for h in held(lists[t]): combo[h["address"]] = h.get("amount_percentage") or 0
    p = {"sniper": pct(lists["sniper"]), "bundler": pct(lists["bundler"]), "fresh": pct(lists["fresh_wallet"]),
         "rat": pct(lists["rat_trader"]), "smart": pct(lists["smart_degen"]), "kol": pct(lists["renowned"]), "combo": round(sum(combo.values()) * 100, 2)}
    smartkol = counts["smart_degen"]["holding"] + counts["renowned"]["holding"]
    reasons, ok = [], True
    def chk(cond, good, bad):
        nonlocal ok
        reasons.append(good if cond else bad); ok = ok and cond
    chk(smartkol >= C["minSmartKol"], f"{smartkol} smart/KOL holding", f"only {smartkol} smart/KOL holding (<{C['minSmartKol']})")
    chk(p["combo"] <= C["maxComboPct"], f"sniper+bundler+fresh {p['combo']}%", f"sniper+bundler+fresh {p['combo']}% > {C['maxComboPct']}%")
    chk(p["sniper"] <= C["maxSniperPct"], f"snipers {p['sniper']}%", f"snipers {p['sniper']}% > {C['maxSniperPct']}%")
    chk(p["bundler"] <= C["maxBundlerPct"], f"bundlers {p['bundler']}%", f"bundlers {p['bundler']}% > {C['maxBundlerPct']}%")
    chk(p["rat"] <= C["maxRatPct"], f"rat traders {p['rat']}%", f"rat traders {p['rat']}% > {C['maxRatPct']}%")
    adj = min(C["smartKolBonusCap"], smartkol * C["smartKolBonusEach"])
    if p["combo"] > C["maxComboPct"]: adj += C["comboPenalty"]
    if p["rat"] > C["maxRatPct"]: adj += C["ratPenalty"]
    out = {"status": "PASS" if ok else "FAIL", "pass": ok, "reasons": reasons, "scoreAdj": adj, "counts": counts, "pct": p,
           "link": f"https://gmgn.ai/sol/token/{mint}"}
    _cache[mint] = (time.time(), out)
    return out

def line(g):
    if not g: return "GMGN: SKIPPED"
    if g["status"] in ("SKIPPED", "ERROR"): return f"GMGN: {g['status']} ({g['reasons'][0]})"
    bad = [r for r in g["reasons"] if ">" in r or "only" in r]
    return f"GMGN: {g['status']} — " + "; ".join(bad if g["status"] == "FAIL" else g["reasons"][:2]) + f" (score {g['scoreAdj']:+d})"

def ath_mc(mint, chain="sol"):
    """ATH market cap = ath_price * circulating_supply from /v1/token/info. None if no key / error."""
    if not os.environ.get("GMGN_API_KEY"): return None
    try:
        q = dict(chain=chain, address=mint, timestamp=int(time.time()), client_id=str(uuid.uuid4()))
        req = urllib.request.Request(f"{HOST}/v1/token/info?{urllib.parse.urlencode(q)}",
                                     headers={"X-APIKEY": os.environ["GMGN_API_KEY"], "User-Agent": "degen-signals/1.0"})
        d = json.loads(urllib.request.urlopen(req, timeout=15).read()).get("data") or {}
        ath, sup = float(d.get("ath_price") or 0), float(d.get("circulating_supply") or d.get("total_supply") or 0)
        return ath * sup if ath and sup else None
    except Exception:
        return None


def wallet_behaviour(wallets, mint, limit=100):
    """Per wallet from /v1/user/wallet_activity (last `limit` events): maxTokensDay (distinct tokens traded in one UTC day),
    maxTxDay, entryDayTokens (distinct tokens bought on the day it first bought `mint`). Cached 1h. Errors -> omitted."""
    out = {}
    for w in wallets:
        if not w: continue
        hit = _cache.get("wb:" + w)
        if hit and time.time() - hit[0] < 3600:
            out[w] = hit[1]; continue
        try:
            q = dict(chain="sol", wallet_address=w, limit=limit, timestamp=int(time.time()), client_id=str(uuid.uuid4()))
            req = urllib.request.Request(f"{HOST}/v1/user/wallet_activity?{urllib.parse.urlencode(q)}",
                                         headers={"X-APIKEY": os.environ["GMGN_API_KEY"], "User-Agent": "degen-signals/1.0"})
            acts = (json.loads(urllib.request.urlopen(req, timeout=15).read()).get("data") or {}).get("activities") or []
        except Exception:
            continue
        finally:
            time.sleep(0.3)
        days, tx, buys = {}, {}, {}
        for a in acts:
            d = int(a.get("timestamp") or 0) // 86400; t = (a.get("token") or {}).get("address")
            tx[d] = tx.get(d, 0) + 1; days.setdefault(d, set()).add(t)
            if a.get("event_type") == "buy": buys.setdefault(d, set()).add(t)
        entry = [int(a["timestamp"]) // 86400 for a in acts if a.get("event_type") == "buy" and (a.get("token") or {}).get("address") == mint]
        v = {"maxTokensDay": max((len(s) for s in days.values()), default=0), "maxTxDay": max(tx.values(), default=0),
             "entryDayTokens": len(buys.get(min(entry), set())) if entry else None, "events": len(acts)}
        _cache["wb:" + w] = (time.time(), v); out[w] = v
    return out
