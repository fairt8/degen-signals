"""InsightX DEX Metrics overview (free tier: 5 req/min, 1,000 req/month, key from https://hub.insightx.network).
One call per NEW alerted token only: GET /dex-metrics/v1/sol/{mint} -> cluster/sniper/bundler/dev/insider/top10 % of supply.
Dormant when INSIGHTX_API_KEY is unset."""
import os, time
import pipeline

_last = [0.0]

def overview(mint):
    k = os.environ.get("INSIGHTX_API_KEY")
    if not k: return None
    def f():
        wait = 12.5 - (time.time() - _last[0])  # stay under 5 req/min
        if wait > 0: time.sleep(wait)
        _last[0] = time.time()
        try:
            d = pipeline.get(f"https://api.insightx.network/dex-metrics/v1/sol/{mint}", {"X-API-Key": k}, timeout=20)
        except Exception as e:
            return {"error": str(e)[:100]}
        keys = {"cluster_pct": "cluster", "snipers_pct": "sniper", "bundlers_pct": "bundler",
                "dev_pct": "dev", "insiders_pct": "insider", "top10_pct": "top10"}
        return {v: round(float(d[k2]), 2) for k2, v in keys.items() if d.get(k2) is not None}
    return pipeline.cached("ix:" + mint, 3600, f)
