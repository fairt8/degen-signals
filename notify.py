"""Telegram poster. Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (e.g. @yourchannel or numeric id)."""
import json, os, sys, urllib.parse, urllib.request
def fmt(n): return f"{n/1e6:.2f}M" if n >= 1e6 else f"{n/1e3:.1f}K" if n >= 1e3 else f"{n:.0f}"
def dev_line(r):
    d = r.get("dev") or {}
    if not d.get("wallet"): return ""
    flags = ("🚩rug history " if d.get("rugHistory") else "") + ("sold " if d.get("sold") else f"holds {d.get('holdPct')}% ")
    return (f"Dev: {flags}· {d.get('priorTokens')} prior ({d.get('priorMigrated')} migrated, {d.get('priorDead')} dead) "
            f"· dev score {r.get('devScore', 0):+d}\n")
import os as _os
def post(text, reply_to=None):
    """Raw post. DRY_RUN=1 prints instead of sending. Returns message_id or None."""
    tok, chat = _os.environ.get("TELEGRAM_BOT_TOKEN"), _os.environ.get("TELEGRAM_CHAT_ID")
    if _os.environ.get("DRY_RUN"):
        print("[DRY_RUN telegram]", text.replace("\n", " | ")[:300], file=sys.stderr); return -1
    if not tok or not chat:
        print("telegram: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set, skipping", file=sys.stderr); return None
    q = {"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}
    if reply_to and reply_to > 0: q.update(reply_to_message_id=reply_to, allow_sending_without_reply="true")
    try:
        r = json.loads(urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage",
                       data=urllib.parse.urlencode(q).encode(), timeout=15).read())
        return r["result"]["message_id"]
    except Exception as e:
        print(f"telegram error: {e}", file=sys.stderr); return None
def send(r):
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        print("telegram: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set, skipping", file=sys.stderr); return False
    from html import escape as e
    L = r["links"]
    link = lambda k, label: f'<a href="{e(L[k])}">{label}</a>' if L.get(k) else ""
    text = (f"🎯 5R signal: ${e(r['symbol'])} ({e(r['name'])})\n"
            f"MC ${fmt(r['mcap'])} · Liq ${fmt(r['liq'])} · Vol {r['window']} ${fmt(r['vol'])}\n"
            f"5m {r['ch5m']}% · 1h {r['ch1h']}% · {r['buys']}B/{r['sells']}S · age {r['ageH']}h\n"
            f"Top10 {r.get('top10Pct')}% · Cluster {r.get('clusterPct')}% ({e(str(r.get('clusterSource')))})\n"
            f"{e(dev_line(r))}"
            f"CA: <code>{e(r['mint'])}</code>\n"
            + " | ".join(x for x in [link("dexscreener", "DexScreener"), link("pumpfun", "pump.fun"), link("bubblemaps", "Bubblemaps"),
                                     link("insightx", "InsightX"), link("x_search", "X")] if x)
            + "\n⚠️ Not financial advice. DYOR.")
    return post(text)
