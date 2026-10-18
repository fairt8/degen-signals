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
        r["orders"] = pipeline.dex_orders(r["chain"], r["mint"])
        r["cto"] = True if (r.get("ctoProfile") or r["orders"].get("ctoOrder")) else (False if r["orders"].get("ctoOrder") is not None else None)
        r["holders"] = {"top5": h.get("top5"), "top5Pct": h.get("top5Pct"), "count": h.get("totalHolders"),
                        "whalePct": h.get("whalePct"), "insiderPct": h.get("insiderPctRugcheck"),
                        "freshWallets": h.get("freshWallets"), "clusterPct": h.get("clusterPct")}
        r["behaviour"] = pipeline.behaviour(r, h, F["behaviour"])
        pipeline.final_score(r, F["behaviour"])
        r["findings"] = pipeline.findings(r, F["behaviour"])
        import chart, liquidity
        r["lp"] = liquidity.status(r["mint"], r.get("pair"), r.get("dex"))
        r["chartAth"] = chart.ath(r["mint"], r["mcap"], r.get("priceUsd"), fallback_pool=r.get("pair"))
        del r["checks"]; out.append(r)
if a.debug:
    fails = {}
    for r in rows:
        for k, v in (r.get("checks") or {}).items(): fails[k] = fails.get(k, 0) + (not v)
    print(json.dumps({"candidates": len(rows), "cheapPass": len(cheap), "failCounts": fails}), file=sys.stderr)
import journal as J
if F.get("milestones"): J.MILESTONES = sorted(F["milestones"])
J.MILESTONE_STEP = F.get("milestoneStep", 50)
feed = json.load(open(a.signals)) if a.signals and os.path.exists(a.signals) else {"tokens": []}
jr = feed.get("journal", [])
# first time the bot saw each candidate (MC at first scan); pruned after 72h
_now = int(time.time()); fs = {k: v for k, v in (feed.get("firstSeen") or {}).items() if _now - v[0] < 72 * 3600}
for r in rows:
    if r.get("mcap"): fs.setdefault(r["mint"], [_now, r["mcap"]])
for r in out:
    v = fs.get(r["mint"]); r["firstScan"] = {"t": v[0], "mc": v[1]} if v else None
    r["odds"] = J.odds(jr, exclude=r["mint"])
for t in reversed(feed.get("tokens", [])):  # backfill journal from earlier feed signals
    if t.get("signalAt") and t.get("links"): J.add(jr, t, t0=t["signalAt"])
jr.sort(key=lambda e: -e["t0"])
for r in out:
    r["priceUsd"] = r.get("priceUsd"); J.add(jr, r)
try: notes = J.update(jr)
except Exception as e: notes = []; errors.append(f"journal update failed: {str(e)[:100]}")
try: J.backfill_chart(jr)
except Exception as e: errors.append(f"chart backfill failed: {str(e)[:100]}")
try:
    import liquidity
    notes += liquidity.monitor(jr)
except Exception as e: errors.append(f"LP monitor failed: {str(e)[:100]}")
if a.signals:
    for r in out: r["signalAt"] = int(time.time())
    feed = {"updatedAt": int(time.time()), "window": F["window"], "lastRunErrors": errors,
            "candidates": len(rows), "cheapPass": len(cheap), "tokens": (out + feed["tokens"])[:200],
            "journal": jr[:300], "stats": J.stats(jr),
            "periodStats": J.period_stats(jr, F.get("winThresholdPct", 0), tp=F.get("tp")), "statsBasis": "24h result where available, else live price",
            "lastReportSlot": feed.get("lastReportSlot"), "firstSeen": fs, "tgOffset": feed.get("tgOffset")}
    os.makedirs(os.path.dirname(os.path.abspath(a.signals)), exist_ok=True)
    json.dump(feed, open(a.signals, "w"), indent=1)
if a.telegram:
    import notify
    ps = J.period_stats(jr, F.get("winThresholdPct", 0), tp=F.get("tp"))
    for r in out:
        mid = notify.send(r, jr)
        for e in jr:
            if e["mint"] == r["mint"] and mid: e["msgId"] = mid
    for kind, e, text in notes:
        notify.post(text, reply_to=e.get("msgId"))
    # standalone PnL report twice a day: slot AM (from 00:00 WAT) and PM (from 12:00 WAT), first run in each slot
    import datetime as dt
    now = dt.datetime.now(J.WAT); slot = now.strftime("%Y-%m-%d") + ("-AM" if now.hour < 12 else "-PM")
    last = feed.get("lastReportSlot")
    if last is None:
        last = slot  # first deploy: don't fire for the slot already in progress; next slot sends
    elif a.signals and last != slot:
        if slot.endswith("-AM"):  # midnight report covers the day that just ended
            ref = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() - 1
            rps, day_label = J.period_stats(jr, F.get("winThresholdPct", 0), now=ref, tp=F.get("tp")), "Yesterday"
        else:
            rps, day_label = ps, "Today"
        sent = notify.post(notify.pnl_report(rps, slot, day_label))
        if sent and not os.environ.get("DRY_RUN"): last = slot
    # bot commands via getUpdates once per run, only when no always-on listener/webhook owns the updates
    tgo = feed.get("tgOffset")
    pol = os.environ.get("TG_COMMANDS_POLL")
    if (pol == "1" or (pol is None and (F.get("commands") or {}).get("workflowPolling"))) and not os.environ.get("DRY_RUN"):
        import commands
        tgo = commands.poll_once(tgo)
    if a.signals: json.dump({**json.load(open(a.signals)), "journal": jr[:300], "lastReportSlot": last, "tgOffset": tgo}, open(a.signals, "w"), indent=1)
json.dump(sorted(seen | {r["mint"] for r in out}), open(a.state, "w"))
print(json.dumps({"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "window": F["window"], "count": len(out), "errors": errors,
                  "disclaimer": "Not financial advice.", "tokens": out}, indent=2))
