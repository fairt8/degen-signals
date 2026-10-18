"""Real all-time high from chart candles (GeckoTerminal public API, free, ~30 req/min).
ATH MC = ATH price (highest candle high, USD, base token) x circulating supply (DexScreener mcap / price)."""
import sys, time
import pipeline
GT = "https://api.geckoterminal.com/api/v2/networks/solana"
QUOTES = ("SOL", "WSOL", "USDC", "USDT")
_last = [0.0]

def _gt(path):
    """Rate-limited GeckoTerminal GET (>=2.1s apart), 1 retry on 429."""
    for attempt in range(2):
        wait = 2.1 - (time.time() - _last[0])
        if wait > 0: time.sleep(wait)
        _last[0] = time.time()
        try:
            return pipeline.get(GT + path, headers={"Accept": "application/json;version=20230302"})
        except Exception as x:
            if "429" in str(x) and attempt == 0: time.sleep(15); continue
            raise

def pools(mint):
    """Top pools where the token is the base and quote is SOL/USDC/USDT (avoids thin token/token pools with silly wicks)."""
    def f():
        d = _gt(f"/tokens/{mint}/pools?page=1")
        out = []
        for p in d.get("data") or []:
            a, rel = p["attributes"], p.get("relationships") or {}
            if (rel.get("base_token") or {}).get("data", {}).get("id") != f"solana_{mint}": continue
            if a.get("name", "").split(" / ")[-1].split(" ")[0].upper() not in QUOTES: continue
            if float(a.get("reserve_in_usd") or 0) < 300: continue
            out.append({"address": a["address"], "created": a.get("pool_created_at"), "reserve": float(a.get("reserve_in_usd") or 0)})
        return sorted(out, key=lambda x: -x["reserve"])[:3]
    return pipeline.cached("gtpools:" + mint, 6 * 3600, f)

def candles(pool, need_from=0):
    """[(ts, high, span_s)] newest first: 5-min candles (~83h); hourly ones added when history before that is needed."""
    def f(hourly):
        out = []
        for tf, agg, span in (("minute", 5, 300), ("hour", 1, 3600)):
            if tf == "hour" and not hourly: break
            d = _gt(f"/pools/{pool}/ohlcv/{tf}?aggregate={agg}&limit=1000&currency=usd&token=base")
            rows = (d.get("data") or {}).get("attributes", {}).get("ohlcv_list") or []
            out += [(r[0], r[2], span) for r in rows if r[2]]
            if tf == "minute" and len(rows) < 1000: break  # whole pool history fits in 5-min candles
        return out
    c = pipeline.cached(f"gtc:{pool}", 600, lambda: f(False))
    if len(c) >= 1000 and c[-1][0] > need_from:  # need older history
        c = pipeline.cached(f"gtch:{pool}", 600, lambda: f(True))
    return c

def pool_high(pool, since=None, until=None):
    best = (0.0, None)
    for ts, h, span in candles(pool, since or 0):
        if since and ts + span <= since: continue
        if until and ts > until: continue
        if h > best[0]: best = (h, ts)
    return best

def ath(mint, mcap=None, price=None, since=None, pool=None, fallback_pool=None, until=None):
    """{'price','mc','t','src'} or None. since=unix ts limits to candles after it (e.g. since alert).
    pool: use just this pool (cheaper), else the token's top SOL/USD pools."""
    try:
        ps = [pool] if pool else ([p["address"] for p in pools(mint)] or ([fallback_pool] if fallback_pool else []))
        best = (0.0, None)
        for a in ps:
            h = pool_high(a, since, until)
            if h[0] > best[0]: best = h
        if not best[0]: return None
        supply = (mcap / price) if mcap and price else None
        return {"price": best[0], "mc": round(best[0] * supply) if supply else None, "t": best[1], "src": "chart"}
    except Exception as x:
        print("chart ath failed:", str(x)[:120], file=sys.stderr); return None
