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
def send(r):
    from html import escape as e
    L = r["links"]
    link = lambda k, label: f'<a href="{e(L[k])}">{label}</a>' if L.get(k) else ""
    text = (f"🎯 5R signal: ${e(r['symbol'])} ({e(r['name'])})\n"
            f"MC ${fmt(r['mcap'])} · Liq ${fmt(r['liq'])} · Vol {r['window']} ${fmt(r['vol'])}\n"
            f"5m {r['ch5m']}% · 1h {r['ch1h']}% · {r['buys']}B/{r['sells']}S · age {r['ageH']}h\n"
            f"Top10 {r.get('top10Pct')}% · Cluster {r.get('clusterPct')}% ({e(str(r.get('clusterSource')))})\n"
            f"{e(dev_line(r))}"
            f"{e(__import__('gmgn').line(r.get('gmgn')))}\n"
            f"CA: <code>{e(r['mint'])}</code>\n"
            + " | ".join(x for x in [link("dexscreener", "DexScreener"), link("pumpfun", "pump.fun"), link("bubblemaps", "Bubblemaps"),
                                     link("insightx", "InsightX"), link("x_search", "X")] if x)
            + "\n⚠️ Not financial advice. DYOR.")
    return post(text)
