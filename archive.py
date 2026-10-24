"""Signal archive: docs/signals.json keeps only the last ARCHIVE_DAYS (and at most MAX_TOKENS / MAX_JOURNAL entries);
older tokens + journal entries move to docs/archive/YYYY-MM.json (WAT month of the alert) and are listed in
docs/archive/index.json. Nothing is dropped: all-time stats, /tokens all, /pnl and the site/mini app read both.
A file is rewritten only when its content changes, so idle scans don't touch the archive."""
import datetime as dt, glob, json, os, time

ARCHIVE_DAYS, MAX_TOKENS, MAX_JOURNAL = 30, 200, 300
WAT = dt.timezone(dt.timedelta(hours=1))

def adir(signals_path): return os.path.join(os.path.dirname(os.path.abspath(signals_path)), "archive")
def month(t): return dt.datetime.fromtimestamp(t or 0, WAT).strftime("%Y-%m")
def tt(x): return x.get("signalAt") or x.get("t0") or 0

def load(signals_path):
    """(tokens, journal) from every archive month file, newest first."""
    toks, jr = [], []
    for f in sorted(glob.glob(os.path.join(adir(signals_path), "[0-9][0-9][0-9][0-9]-[0-9][0-9].json")), reverse=True):
        d = json.load(open(f)); toks += d.get("tokens") or []; jr += d.get("journal") or []
    return sorted(toks, key=lambda x: -tt(x)), sorted(jr, key=lambda x: -tt(x))

def merge_journal(recent, archived):
    """Full journal (recent wins on duplicate mints), newest first."""
    ms = {e["mint"] for e in recent}
    return sorted(recent + [e for e in archived if e["mint"] not in ms], key=lambda e: -e["t0"])

def split(tokens, journal, now=None, days=ARCHIVE_DAYS):
    """-> (keep_tokens, keep_journal, old_tokens, old_journal). Old = alert older than `days` or beyond the caps."""
    cut = (now or time.time()) - days * 86400
    tokens = sorted(tokens, key=lambda x: -tt(x)); journal = sorted(journal, key=lambda x: -tt(x))
    kt = [x for x in tokens if tt(x) >= cut][:MAX_TOKENS]; kj = [e for e in journal if e["t0"] >= cut][:MAX_JOURNAL]
    kts, kjs = {id(x) for x in kt}, {id(x) for x in kj}
    return kt, kj, [x for x in tokens if id(x) not in kts], [e for e in journal if id(e) not in kjs]

def _write(path, obj):
    s = json.dumps(obj, indent=1)
    if os.path.exists(path) and open(path).read() == s: return False
    os.makedirs(os.path.dirname(path), exist_ok=True); open(path, "w").write(s); return True

def save(signals_path, old_tokens, old_journal):
    """Merge moved entries into their month files (by mint; newer copy wins). Returns archive summary for the feed."""
    a = adir(signals_path); by = {}
    for kind, xs in (("tokens", old_tokens), ("journal", old_journal)):
        for x in xs: by.setdefault(month(tt(x)), {"tokens": [], "journal": []})[kind].append(x)
    for m, new in by.items():
        f = os.path.join(a, m + ".json")
        cur = json.load(open(f)) if os.path.exists(f) else {"month": m, "tokens": [], "journal": []}
        for kind in ("tokens", "journal"):
            mints = {x["mint"] for x in new[kind]}
            cur[kind] = sorted(new[kind] + [x for x in cur.get(kind) or [] if x["mint"] not in mints], key=lambda x: -tt(x))
        _write(f, {"month": m, "note": "Archived Degen signals (older than %d days). Not financial advice." % ARCHIVE_DAYS, **{k: cur[k] for k in ("tokens", "journal")}})
    files = sorted((os.path.basename(f) for f in glob.glob(os.path.join(a, "[0-9][0-9][0-9][0-9]-[0-9][0-9].json"))), reverse=True)
    counts = {}
    for f in files:
        d = json.load(open(os.path.join(a, f))); counts[f] = {"tokens": len(d.get("tokens") or []), "journal": len(d.get("journal") or [])}
    summary = {"days": ARCHIVE_DAYS, "files": files, "tokens": sum(c["tokens"] for c in counts.values()),
               "journal": sum(c["journal"] for c in counts.values())}
    if files: _write(os.path.join(a, "index.json"), {**summary, "counts": counts})
    return summary
