#!/usr/bin/env python3
"""Commit gate for the scan (box run_scan.sh and the Actions workflow). Keeps git history small:
the feed is committed only when something meaningful changed, or as a heartbeat every HEARTBEAT_S.

  persist.py restore STATE   before alert.py: bring back the last uncommitted feed/seen state if it is newer
  persist.py decide  STATE   after alert.py: exit 0 = commit, exit 1 = skip (state saved to STATE for next run)
  persist.py clear   STATE   after a successful push

Meaningful: new/changed signals (tokens), seen.json, journal changes other than live-price ticks (1h/24h results,
milestones, max gain, ATH, LP status/events, trend, safety, msgId), lastReportSlot, tgOffset, archive files.
Not meaningful on their own: updatedAt, candidates, cheapPass, lastRunErrors, derived stats, and live ticks
(last, lastT, lastPct, minPrice, samples, chartT, lp.t, lp.liq). Those ride along with the next commit/heartbeat."""
import json, os, shutil, subprocess, sys, time

FEED, SEEN, ARCH = "docs/signals.json", "seen.json", "docs/archive"
HEARTBEAT_S = int(os.environ.get("DEGEN_HEARTBEAT_S", 7000))  # ~2h
TOP_VOLATILE = {"updatedAt", "candidates", "cheapPass", "lastRunErrors", "stats", "periodStats", "statsBasis", "firstSeen"}
JR_VOLATILE = {"last", "lastT", "lastPct", "minPrice", "samples", "chartT"}
LP_VOLATILE = {"t", "liq"}

def norm(d):
    d = {k: v for k, v in (d or {}).items() if k not in TOP_VOLATILE}
    jr = []
    for e in d.get("journal") or []:
        e = {k: v for k, v in e.items() if k not in JR_VOLATILE}
        if isinstance(e.get("lp"), dict): e["lp"] = {k: v for k, v in e["lp"].items() if k not in LP_VOLATILE}
        jr.append(e)
    d["journal"] = jr
    return json.dumps(d, sort_keys=True)

def head(path):
    r = subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None

def load(s):
    try: return json.loads(s) if s else None
    except ValueError: return None

def reasons():
    out = []
    old, new = load(head(FEED)), load(open(FEED).read()) if os.path.exists(FEED) else None
    if new is None: return out
    if old is None: return ["feed new"]
    if (head(SEEN) or "").strip() != (open(SEEN).read().strip() if os.path.exists(SEEN) else ""): out.append("seen.json")
    if norm(old) != norm(new):
        ot, nt = {t["mint"] for t in old.get("tokens") or []}, {t["mint"] for t in new.get("tokens") or []}
        out.append(f"{len(nt - ot)} new signal(s)" if nt - ot else "journal/state change")
    st = subprocess.run(["git", "status", "--porcelain", "--", ARCH], capture_output=True, text=True).stdout.strip()
    if st: out.append("archive")
    age = time.time() - (old.get("updatedAt") or 0)
    if not out and age >= HEARTBEAT_S: out.append(f"heartbeat ({age/3600:.1f}h since last save)")
    return out

def restore_archive(pa):
    """Union pending archive months back into docs/archive (by mint, pending wins) so a failed push never drops
    signals that were moved out of the feed."""
    if not os.path.isdir(pa): return
    os.makedirs(ARCH, exist_ok=True)
    for f in os.listdir(pa):
        src, dst = os.path.join(pa, f), os.path.join(ARCH, f)
        if f == "index.json" or not os.path.exists(dst): shutil.copy(src, dst); continue
        a, b = load(open(src).read()) or {}, load(open(dst).read()) or {}
        for k in ("tokens", "journal"):
            seen = {e.get("mint") for e in a.get(k) or []}
            a[k] = (a.get(k) or []) + [e for e in b.get(k) or [] if e.get("mint") not in seen]
        json.dump({**b, **a}, open(dst, "w"), indent=1)

def main():
    cmd, state = sys.argv[1], sys.argv[2]
    os.makedirs(state, exist_ok=True)
    pf, ps = os.path.join(state, "pending_signals.json"), os.path.join(state, "pending_seen.json")
    pa = os.path.join(state, "pending_archive")
    if cmd == "restore":
        p, cur = load(open(pf).read()) if os.path.exists(pf) else None, load(open(FEED).read()) if os.path.exists(FEED) else None
        if p and (cur is None or (p.get("updatedAt") or 0) > (cur.get("updatedAt") or 0)):
            shutil.copy(pf, FEED)
            if os.path.exists(ps): shutil.copy(ps, SEEN)
            restore_archive(pa)
            print("persist: restored uncommitted state from", time.strftime("%FT%TZ", time.gmtime(p["updatedAt"])))
        elif p: print("persist: pending state older than the repo feed, ignored")
    elif cmd == "decide":
        rs = reasons()
        if os.path.exists(FEED): shutil.copy(FEED, pf)
        if os.path.exists(SEEN): shutil.copy(SEEN, ps)
        if os.path.isdir(ARCH): shutil.rmtree(pa, ignore_errors=True); shutil.copytree(ARCH, pa)
        try:  # local-only scan summary (counts + errors), never committed
            d = json.load(open(FEED))
            json.dump({"t": d.get("updatedAt"), "candidates": d.get("candidates"), "cheapPass": d.get("cheapPass"),
                       "errors": d.get("lastRunErrors"), "commit": rs}, open(os.path.join(state, "lastscan.json"), "w"))
        except Exception: pass
        print("persist: commit (" + ", ".join(rs) + ")" if rs else "persist: skip (no meaningful change; state kept locally)")
        sys.exit(0 if rs else 1)
    elif cmd == "clear":
        for f in (pf, ps):
            if os.path.exists(f): os.remove(f)
        shutil.rmtree(pa, ignore_errors=True)

if __name__ == "__main__": main()
