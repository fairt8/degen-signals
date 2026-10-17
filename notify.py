"""Telegram poster. Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID or TELEGRAM_CHAT_IDS (comma-separated, e.g. 123,-100456)."""
import json, os, sys, urllib.error, urllib.parse, urllib.request
def fmt(n): return f"{n/1e6:.2f}M" if n >= 1e6 else f"{n/1e3:.1f}K" if n >= 1e3 else f"{n:.0f}"
def dev_line(r):
    d = r.get("dev") or {}
    if not d.get("wallet"): return ""
    flags = ("🚩rug history " if d.get("rugHistory") else "") + ("sold " if d.get("sold") else f"holds {d.get('holdPct')}% ")
    return (f"Dev: {flags}· {d.get('priorTokens')} prior ({d.get('priorMigrated')} migrated, {d.get('priorDead')} dead) "
            f"· dev score {r.get('devScore', 0):+d}\n")
import os as _os
def chats():
    raw = _os.environ.get("TELEGRAM_CHAT_IDS") or _os.environ.get("TELEGRAM_CHAT_ID") or ""
    return [c.strip() for c in raw.split(",") if c.strip()]

def post(text, reply_to=None):
    """Post to every chat in TELEGRAM_CHAT_ID(S) (comma-separated). DRY_RUN=1 prints instead.
    reply_to: {chat_id: message_id} (or int for legacy single-chat). Returns {chat_id: message_id} for successes."""
    tok, cs = _os.environ.get("TELEGRAM_BOT_TOKEN"), chats()
    if _os.environ.get("DRY_RUN"):
        print(f"[DRY_RUN telegram -> {len(cs)} chats]", text.replace("\n", " | ")[:300], file=sys.stderr); return {}
    if not tok or not cs:
        print("telegram: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set, skipping", file=sys.stderr); return {}
    out = {}
    for chat in cs:
        q = {"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}
        rid = reply_to.get(chat) if isinstance(reply_to, dict) else (reply_to if len(cs) == 1 else None)
        if rid and rid > 0: q.update(reply_to_message_id=rid, allow_sending_without_reply="true")
        try:
            r = json.loads(urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage",
                           data=urllib.parse.urlencode(q).encode(), timeout=15).read())
            out[chat] = r["result"]["message_id"]
        except urllib.error.HTTPError as e:
            print(f"telegram error chat#{cs.index(chat)}: {e} {e.read()[:200]!r}", file=sys.stderr)
        except Exception as e:
            print(f"telegram error chat#{cs.index(chat)}: {e}", file=sys.stderr)
    return out
LABELS = {"today": "Today", "week": "Week", "month": "Month", "all": "All-time"}
BASIS = "PnL = sum of % per signal since alert; 24h result where available, else live price"
def _pct(x): return "n/a" if x is None else f"{x:+.1f}%"
def _wr(s): return "n/a" if s["winRate"] is None else f"{s['winRate']:.0f}% ({s['wins']}/{s['n']})"
def period_line(k, s):
    if not s["signals"]: return f"{LABELS[k]}: no signals"
    return f"{LABELS[k]}: {s['signals']} sig · Win {_wr(s)} · Total {_pct(s['totalPnl'])} · Avg {_pct(s['avgPnl'])} · 2x {s['hit2x']}/5x {s['hit5x']}"
def stats_block(ps):
    if not ps: return ""
    a = ps["all"]["basis"]
    return ("📊 Bot stats (WAT)\n" + "\n".join(e_(period_line(k, ps[k])) for k in ("today", "week", "month", "all"))
            + f"\n<i>{BASIS} (all-time: {a['24h']} at 24h, {a['live']} live)</i>")
def daily_summary(ps, date_str):
    t = ps["today"]
    return "\n".join([f"🗓 <b>Degen Signals daily summary: {date_str} (WAT)</b>", "",
        f"Signals today: {t['signals']}", f"Win rate: {_wr(t)}",
        f"Total PnL: {_pct(t['totalPnl'])} · Avg: {_pct(t['avgPnl'])}",
        e_(f"Best: {t['best'] or 'n/a'} · Worst: {t['worst'] or 'n/a'}"),
        f"2x hits: {t['hit2x']} · 5x hits: {t['hit5x']}", "",
        "\n".join(e_(period_line(k, ps[k])) for k in ("week", "month", "all")), "",
        f"<i>{BASIS}. Win = PnL above the configured threshold. Not financial advice.</i>"])
def e_(s):
    from html import escape; return escape(s, quote=False)

def ath(r, journal=None):
    """(ath_mc, label). GMGN token info -> pump.fun ath field -> highest MC seen in our journal (est.)."""
    import gmgn
    v = gmgn.ath_mc(r["mint"]) if r.get("chain") == "solana" else None
    if v: return max(v, r["mcap"]), ""
    try:
        req = urllib.request.Request(f"https://frontend-api-v3.pump.fun/coins/{r['mint']}", headers={"User-Agent": "Mozilla/5.0"})
        d = json.loads(urllib.request.urlopen(req, timeout=8).read())
        v = d.get("ath_market_cap") or d.get("athMarketCap")
        if v: return max(float(v), r["mcap"]), ""
    except Exception: pass
    for e in journal or []:
        if e.get("mint") == r["mint"] and e.get("price0") and e.get("maxPrice") and e.get("mcap0"):
            return max(e["mcap0"] * e["maxPrice"] / e["price0"], r["mcap"]), " (est., seen by bot)"
    return None, ""

def send(r, journal=None, pstats=None):
    from html import escape as e
    L = r["links"]
    link = lambda k, label: f'<a href="{e(L[k])}">{label}</a>' if L.get(k) else ""
    a, lbl = ath(r, journal)
    aths = f"${fmt(a)}{lbl}" if a else "n/a"
    sections = [
        f"<code>{e(r['mint'])}</code>\n{e(r['name'])} ${e(r['symbol'])}",
        f"MC: ${fmt(r['mcap'])} | ATH MC: {e(aths)}\nLiq: ${fmt(r['liq'])} · Age: {r['ageH']}h · 5m {r['ch5m']}% · 1h {r['ch1h']}%",
        f"Vol {r['window']}: ${fmt(r['vol'])} · Txns: {r['buys']} buys / {r['sells']} sells",
        f"Top10: {r.get('top10Pct')}% · Cluster: {r.get('clusterPct')}% ({e(str(r.get('clusterSource')))})",
        e(dev_line(r).strip()) or "Dev: n/a",
        e(__import__('gmgn').line(r.get('gmgn'))),
        stats_block(pstats),
        " | ".join(x for x in [link("dexscreener", "DexScreener"), link("pumpfun", "pump.fun"), link("bubblemaps", "Bubblemaps"),
                               link("insightx", "InsightX"), link("x_search", "X")] if x) + "\n⚠️ Not financial advice. DYOR.",
    ]
    sections = [s for s in sections if s]
    if (r.get("description") or "").strip():
        sections.append(f"<i>{e(r['description'].strip()[:400])}</i>")
    return post("\n\n".join(sections))
