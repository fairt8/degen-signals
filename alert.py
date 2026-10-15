#!/usr/bin/env python3
"""Headless 5R hunter. Prints JSON of NEW passing tokens; remembers seen mints in a state file.
Usage: python3 alert.py [--state seen.json] [--window h1|h24] [--all] [--debug]
Env (optional): INSIGHTX_API_KEY, BUBBLEMAPS_API_KEY, SOLANA_RPC"""
import argparse, json, os, sys, time
import pipeline
ap = argparse.ArgumentParser()
ap.add_argument("--state", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen.json"))
ap.add_argument("--window", choices=["h1", "h24"]); ap.add_argument("--all", action="store_true", help="ignore state (report seen too)")
ap.add_argument("--signals", help="append new signals to this JSON feed (e.g. docs/signals.json)")
ap.add_argument("--telegram", action="store_true", help="post new signals via TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID env")
ap.add_argument("--debug", action="store_true", help="print filter stats to stderr")
a = ap.parse_args()
F = pipeline.load_config()
if a.window: F["window"] = a.window
seen = set(json.load(open(a.state))) if os.path.exists(a.state) else set()
rows = [pipeline.evaluate(p, m, F) for p, m in pipeline.candidates()]
rows = [r for r in rows if r["socials"]]
cheap = [r for r in rows if r["cheapPass"] and r["chain"] == "solana"]
out, errors = [], []
for r in cheap[:F.get("holderLookupLimit", 15)]:
    try: h = pipeline.holders_and_clusters(r["mint"])
    except Exception as e:
        errors.append(f"holder lookup failed {r['symbol']}: {str(e)[:100]}"); print(errors[-1], file=sys.stderr); continue
    r["top10Pct"], r["clusterPct"], r["clusterSource"], r["clusters"] = h["top10Pct"], h["clusterPct"], h["clusterSource"], h["clusters"]
    import gmgn
    r["gmgn"] = gmgn.analyze(r["mint"], F["gmgn"]); r["gmgnScore"] = r["gmgn"]["scoreAdj"]
    r["dev"] = h.get("dev"); r["devScore"], r["devNotes"] = pipeline.dev_score(r["dev"], F["devScore"])
    r["extras"] = {"estFeesSol": r["estFeesSol"], "maxSingleHolderPct": h.get("maxSingleHolderPct"),
                   "freshWallets": h.get("freshWallets"), "insiderNetworks": h.get("insiderNetworks")}
    opt = [(not F.get("estFeesOn")) or (r["estFeesSol"] or 0) >= F["estFeesMinSol"],
           (not F.get("maxSingleHolderOn")) or (h.get("maxSingleHolderPct") or 0) <= F["maxSingleHolderPct"],
           (not F.get("freshWalletsOn")) or (h.get("freshWallets") or 0) <= F["freshWalletsMax"]]
    if h["top10Pct"] < F["top10MaxPct"] and h["clusterPct"] <= F["clusterMaxPct"] and all(opt) and (a.all or r["mint"] not in seen):
        del r["checks"]; out.append(r)
if a.debug:
    fails = {}
    for r in rows:
        for k, v in (r.get("checks") or {}).items(): fails[k] = fails.get(k, 0) + (not v)
    print(json.dumps({"candidates": len(rows), "cheapPass": len(cheap), "failCounts": fails}), file=sys.stderr)
import journal as J
feed = json.load(open(a.signals)) if a.signals and os.path.exists(a.signals) else {"tokens": []}
jr = feed.get("journal", [])
for t in reversed(feed.get("tokens", [])):  # backfill journal from earlier feed signals
    if t.get("signalAt") and t.get("links"): J.add(jr, t, t0=t["signalAt"])
jr.sort(key=lambda e: -e["t0"])
for r in out:
    r["priceUsd"] = r.get("priceUsd"); J.add(jr, r)
try: notes = J.update(jr)
except Exception as e: notes = []; errors.append(f"journal update failed: {str(e)[:100]}")
if a.signals:
    for r in out: r["signalAt"] = int(time.time())
    feed = {"updatedAt": int(time.time()), "window": F["window"], "lastRunErrors": errors,
            "candidates": len(rows), "cheapPass": len(cheap), "tokens": (out + feed["tokens"])[:200],
            "journal": jr[:300], "stats": J.stats(jr)}
    os.makedirs(os.path.dirname(os.path.abspath(a.signals)), exist_ok=True)
    json.dump(feed, open(a.signals, "w"), indent=1)
if a.telegram:
    import notify
    for r in out:
        mid = notify.send(r)
        for e in jr:
            if e["mint"] == r["mint"] and mid: e["msgId"] = mid
    for kind, e, text in notes:
        notify.post(text, reply_to=e.get("msgId"))
    if a.signals: json.dump({**json.load(open(a.signals)), "journal": jr[:300]}, open(a.signals, "w"), indent=1)
json.dump(sorted(seen | {r["mint"] for r in out}), open(a.state, "w"))
print(json.dumps({"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "window": F["window"], "count": len(out), "errors": errors,
                  "disclaimer": "Not financial advice.", "tokens": out}, indent=2))
