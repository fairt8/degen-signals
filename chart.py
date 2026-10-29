"""Real all-time high from chart candles (GeckoTerminal public API, free, ~30 req/min).
ATH MC = ATH price (highest candle high, USD, base token) x circulating supply (DexScreener mcap / price)."""
import sys, time
import pipeline
GT = "https://api.geckoterminal.com/api/v2/networks/solana"
QUOTES = ("SOL", "WSOL", "USDC", "USDT")
import os
_last = [0.0]
# per-run budget so a slow/rate-limited GeckoTerminal can't stall the 8-min workflow; after a 429 we stop calling it this run
_state = {"deadline": time.time() + float(os.environ.get("CHART_BUDGET_S", "150")), "blocked": False, "calls": 0}
MAX_CALLS = int(os.environ.get("CHART_MAX_CALLS", "60"))

def _gt(path):
    """Rate-limited GeckoTerminal GET (>=2.1s apart). Raises when the run budget is spent or after a 429."""
    if _state["blocked"] or time.time() > _state["deadline"] or _state["calls"] >= MAX_CALLS:
        raise RuntimeError("chart budget exhausted / rate limited this run")
    wait = 2.1 - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    _last[0] = time.time(); _state["calls"] += 1
    try:
        return pipeline.get(GT + path, headers={"Accept": "application/json;version=20230302"}, timeout=10)
    except Exception as x:
        if "429" in str(x): _state["blocked"] = True
        raise

def reset_budget(seconds=30):
    """For long-running processes (command listener): fresh budget per request."""
    _state.update(deadline=time.time() + seconds, blocked=False, calls=0)

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

def candles(pool, need_from=0, token="base"):
    """[(ts, high, span_s, open, close)] newest first: 5-min candles (~83h); hourly ones added when history before
    that is needed. token=<mint> prices that token even when GeckoTerminal lists it as the pool's quote side
    (token=base on a STONK/X pool returns STONK's price, which produced fake 800x-5900x ATHs)."""
    def f(hourly):
        out = []
        for tf, agg, span in (("minute", 5, 300), ("hour", 1, 3600)):
            if tf == "hour" and not hourly: break
            d = _gt(f"/pools/{pool}/ohlcv/{tf}?aggregate={agg}&limit=1000&currency=usd&token={token}")
            rows = (d.get("data") or {}).get("attributes", {}).get("ohlcv_list") or []
            out += [(r[0], r[2], span, r[1], r[4]) for r in rows if r[2]]
            if tf == "minute" and len(rows) < 1000: break  # whole pool history fits in 5-min candles
        return out
    tk = "" if token == "base" else ":" + token
    c = pipeline.cached(f"gtc2:{pool}{tk}", 600, lambda: f(False))
    if len(c) >= 1000 and c[-1][0] > need_from:  # need older history
        c = pipeline.cached(f"gtch2:{pool}{tk}", 600, lambda: f(True))
    return c

WICK_X = 3.0  # a high more than WICK_X x the candle body top is a wick ...
def clean_highs(c):
    """Outlier filter: [(ts, high, span)] oldest first. A wick (high > WICK_X x max(open, close)) counts only when an
    adjacent candle confirms it (its high or body top >= high / WICK_X); otherwise the candle counts at its body top.
    Real pumps trade through several candles (bodies/neighbours follow), single-print spikes don't."""
    c = sorted(c)
    out = []
    for i, (ts, h, span, o, cl) in enumerate(c):
        body = max(o or 0, cl or 0)
        if body and h > WICK_X * body:
            nb = [max(c[j][1], c[j][3] or 0, c[j][4] or 0) for j in (i - 1, i + 1) if 0 <= j < len(c)]
            if not any(x >= h / WICK_X for x in nb): h = body
        out.append((ts, h, span))
    return out

def sane(c, ref):
    """Series price unit check: newest close must be within 3x of the DexScreener price (else wrong token/side)."""
    if not ref or not c: return True
    last = max(c)[4] or max(c)[1]
    return ref / 3 <= last <= ref * 3

def pool_high(pool, since=None, until=None, token="base", ref=None):
    best = (0.0, None)
    c = candles(pool, since or 0, token)
    if not sane(c, ref):
        print(f"chart: {pool[:8]} price series {max(c)[4]:.3g} vs live {ref:.3g}, ignored (wrong token side)", file=sys.stderr)
        return best
    for ts, h, span in clean_highs(c):
        if since and ts + span <= since: continue
        if until and ts > until: continue
        if h > best[0]: best = (h, ts)
    return best

def ath(mint, mcap=None, price=None, since=None, pool=None, fallback_pool=None, until=None, ref=None):
    """{'price','mc','t','src'} or None. since=unix ts limits to candles after it (e.g. since alert).
    pool: use just this pool (cheaper), else the token's top SOL/USD pools. Candles are always requested for the
    token itself (token=<mint>) and checked against the live price (ref, default price)."""
    try:
        ps = [pool] if pool else ([p["address"] for p in pools(mint)] or ([fallback_pool] if fallback_pool else []))
        ref = ref or (float(price) if price else None)
        best = (0.0, None)
        for a in ps:
            h = pool_high(a, since, until, token=mint, ref=ref)
            if h[0] > best[0]: best = h
        if not best[0]: return None
        supply = (mcap / price) if mcap and price else None
        return {"price": best[0], "mc": round(best[0] * supply) if supply else None, "t": best[1], "src": "chart"}
    except Exception as x:
        if "budget" not in str(x) or not _state.get("warned"):
            print("chart ath failed:", str(x)[:120], file=sys.stderr); _state["warned"] = "budget" in str(x)
        return None
