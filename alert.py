#!/usr/bin/env python3
"""Headless 5R hunter. Prints JSON of NEW passing tokens; remembers seen mints in a state file.
Usage: python3 alert.py [--state seen.json] [--window h1|h24] [--all] [--debug]
Env (optional): INSIGHTX_API_KEY, BUBBLEMAPS_API_KEY, GMGN_API_KEY, SOLANA_RPC"""
import argparse, json, os, sys, time
import pipeline
ap = argparse.ArgumentParser()
ap.add_argument("--state", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen.json"))
ap.add_argument("--window", choices=["h1", "h24"]); ap.add_argument("--all", action="store_true", help="ignore state (report seen too)")
ap.add_argument("--signals", help="append new signals to this JSON feed (e.g. docs/signals.json)")
ap.add_argument("--telegram", action="store_true", help="post new signals via TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID env")
ap.add_argument("--firstseen", default=os.environ.get("FIRSTSEEN_PATH"), help="local (untracked) file for per-scan first-seen MCs; default: inside the feed (legacy)")
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
    r["rugcheck"] = h.get("rugcheck")
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
        import chart, liquidity, gmgn, insightx, safety
        r["lp"] = liquidity.status(r["mint"], r.get("pair"), r.get("dex"))
        if os.environ.get("GMGN_API_KEY"): r["gmgn"] = gmgn.analyze(r["mint"], F["gmgn"])  # dormant without a key
        r["insightx"] = insightx.overview(r["mint"]) if r["mint"] not in seen else None  # free tier: 1 call per new alert
        r["safety"] = safety.check(r, F["safety"])
        r["gmgnScore"] = (r["gmgn"] or {}).get("scoreAdj", 0) if r.get("gmgn") else r["safety"]["scoreAdj"]
        pipeline.final_score(r, F["behaviour"])
        r["findings"] = pipeline.findings(r, F["behaviour"])
        r["chartAth"] = chart.ath(r["mint"], r["mcap"], r.get("priceUsd"), fallback_pool=r.get("pair"))
        del r["checks"]; out.append(r)
if a.debug:
    fails = {}
    for r in rows:
        for k, v in (r.get("checks") or {}).items(): fails[k] = fails.get(k, 0) + (not v)
    print(json.dumps({"candidates": len(rows), "cheapPass": len(cheap), "failCounts": fails}), file=sys.stderr)
    print("keys:", {k: bool(os.environ.get(k)) for k in ("INSIGHTX_API_KEY", "GMGN_API_KEY", "BUBBLEMAPS_API_KEY")}, file=sys.stderr)
    import urllib.request, urllib.error
    def _st(u):  # reachability only (unauthenticated GET status), no data used
        try: return urllib.request.urlopen(urllib.request.Request(u, headers=pipeline.UA), timeout=10).status
        except urllib.error.HTTPError as x: return x.code
        except Exception as x: return type(x).__name__
    _m = "So11111111111111111111111111111111111111112"
    print("reach:", {"insightx_api": _st(f"https://api.insightx.network/dex-metrics/v1/sol/{_m}"),
                     "shuriken_api": _st("https://api.shuriken.trade/api/v2/tokens/search?chain=solana&q=bonk"),
                     "bullx_neo": _st(f"https://neo.bullx.io/terminal?chainId=1399811149&address={_m}"),
                     "axiom": _st(f"https://axiom.trade/t/{_m}?chain=sol")}, file=sys.stderr)
import journal as J, archive
if F.get("milestones"): J.MILESTONES = sorted(F["milestones"])
J.MILESTONE_STEP = F.get("milestoneStep", 50)
feed = json.load(open(a.signals)) if a.signals and os.path.exists(a.signals) else {"tokens": []}
jr = feed.get("journal", [])
arch_tokens, arch_jr = archive.load(a.signals) if a.signals else ([], [])
arch_mints = {e["mint"] for e in arch_jr}
# first time the bot saw each candidate (MC at first scan); pruned after 72h. Kept in a local untracked file when
# --firstseen is set (box: ~/.degen/state/firstseen.json, Actions: cached .state/), not in the public feed.
_now = int(time.time())
_fs_src = json.load(open(a.firstseen)) if a.firstseen and os.path.exists(a.firstseen) else (feed.get("firstSeen") or {})
fs = {k: v for k, v in _fs_src.items() if _now - v[0] < 72 * 3600}
for r in rows:
    if r.get("mcap"): fs.setdefault(r["mint"], [_now, r["mcap"]])
if a.firstseen:
    os.makedirs(os.path.dirname(os.path.abspath(a.firstseen)), exist_ok=True); json.dump(fs, open(a.firstseen, "w"))
full = archive.merge_journal(jr, arch_jr)  # all-time journal: recent feed + archive
for r in out:
    v = fs.get(r["mint"]); r["firstScan"] = {"t": v[0], "mc": v[1]} if v else None
    r["odds"] = J.odds(full, exclude=r["mint"])
for t in reversed(feed.get("tokens", [])):  # backfill journal from earlier feed signals
    if t.get("signalAt") and t.get("links") and t["mint"] not in arch_mints: J.add(jr, t, t0=t["signalAt"])
jr.sort(key=lambda e: -e["t0"])
for r in out:
    r["priceUsd"] = r.get("priceUsd")
    if r["mint"] not in arch_mints: J.add(jr, r)
try: notes = J.update(jr)
except Exception as e: notes = []; errors.append(f"journal update failed: {str(e)[:100]}")
try: J.backfill_safety(jr, F["safety"])
except Exception as e: errors.append(f"safety backfill failed: {str(e)[:100]}")
full = archive.merge_journal(jr, arch_jr)
try: J.backfill_chart(full)  # may also fill archived entries (saved back to the archive below)
except Exception as e: errors.append(f"chart backfill failed: {str(e)[:100]}")
try:
    import liquidity
    notes += liquidity.monitor(jr)
except Exception as e: errors.append(f"LP monitor failed: {str(e)[:100]}")
for r in out: r["signalAt"] = int(time.time())
WIN, TPC = F.get("winThresholdPct", 0), F.get("tp")
def save_feed(extra=None):
    """Recent (<= archive.ARCHIVE_DAYS, capped) stays in the feed; older/overflow moves to docs/archive/. Stats are all-time."""
    if not a.signals: return
    kt, kj, ot, oj = archive.split(out + [t for t in feed.get("tokens", []) if t["mint"] not in {r["mint"] for r in out}], jr)
    arch_ids = {e["mint"] for e in oj}
    summary = archive.save(a.signals, ot + [t for t in arch_tokens if t["mint"] not in {x["mint"] for x in ot}],
                           oj + [e for e in full if e["mint"] in arch_mints and e["mint"] not in arch_ids])
    allj = archive.merge_journal(kj, oj + [e for e in full if e["mint"] in arch_mints])
    d = {"updatedAt": int(time.time()), "window": F["window"], "lastRunErrors": errors,
         "candidates": len(rows), "cheapPass": len(cheap), "tokens": kt, "journal": kj,
         "stats": J.stats(allj), "periodStats": J.period_stats(allj, WIN, tp=TPC),
         "statsBasis": "24h result where available, else live price; all-time includes archived signals",
         "archive": summary, "lastReportSlot": feed.get("lastReportSlot"), "tgOffset": feed.get("tgOffset"),
         "reportProgress": feed.get("reportProgress")}
    if not a.firstseen: d["firstSeen"] = fs
    d.update(extra or {})
    os.makedirs(os.path.dirname(os.path.abspath(a.signals)), exist_ok=True)
    json.dump(d, open(a.signals, "w"), indent=1)
save_feed()
if a.telegram:
    import notify
    ps = J.period_stats(full, WIN, tp=TPC)
    for r in out:
        mid = notify.send(r, full)
        for e in jr:
            if e["mint"] == r["mint"] and mid: e["msgId"] = mid
    for kind, e, text in notes:
        notify.post(text, reply_to=e.get("msgId"))
    # standalone PnL report twice a day: slot AM (from 00:00 WAT) and PM (from 12:00 WAT), first run in each slot
    import datetime as dt
    now = dt.datetime.now(J.WAT); slot = now.strftime("%Y-%m-%d") + ("-AM" if now.hour < 12 else "-PM")
    last = feed.get("lastReportSlot"); report_progress = feed.get("reportProgress")
    if last is None:
        last = slot  # first deploy: don't fire for the slot already in progress; next slot sends
    elif a.signals and last != slot:
        if slot.endswith("-AM"):  # midnight report covers the day that just ended
            ref = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() - 1
            rps, day_label = J.period_stats(full, WIN, now=ref, tp=TPC), "Yesterday"
        else:
            rps, day_label = ps, "Today"
        # latest due slot only (older missed slots are never back-filled); parts resume per chat so none repeat
        late = now.hour % 12 >= 1 and f"Delayed report, sent {now.strftime('%I:%M %p')} WAT" or ""
        prog = feed.get("reportProgress") or {}
        prog = prog.get("done") if prog.get("slot") == slot else {}
        done, ok = notify.post_parts(notify.split_message(notify.pnl_report(rps, slot, day_label, late)), prog)
        report_progress = {"slot": slot, "done": done}
        if ok and not os.environ.get("DRY_RUN"): last = slot
    # bot commands via getUpdates once per run, only when no always-on listener/webhook owns the updates
    tgo = feed.get("tgOffset")
    pol = os.environ.get("TG_COMMANDS_POLL")
    if (pol == "1" or (pol is None and (F.get("commands") or {}).get("workflowPolling"))) and not os.environ.get("DRY_RUN"):
        import commands
        tgo = commands.poll_once(tgo)
    save_feed({"lastReportSlot": last, "tgOffset": tgo, "reportProgress": report_progress})
json.dump(sorted(seen | {r["mint"] for r in out}), open(a.state, "w"))
print(json.dumps({"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "window": F["window"], "count": len(out), "errors": errors,
                  "disclaimer": "Not financial advice.", "tokens": out}, indent=2))
