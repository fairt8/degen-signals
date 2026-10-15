"""Telegram poster. Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (e.g. @yourchannel or numeric id)."""
import json, os, sys, urllib.parse, urllib.request
def fmt(n): return f"{n/1e6:.2f}M" if n >= 1e6 else f"{n/1e3:.1f}K" if n >= 1e3 else f"{n:.0f}"
def dev_line(r):
    d = r.get("dev") or {}
    if not d.get("wallet"): return ""
    flags = ("🚩rug history " if d.get("rugHistory") else "") + ("sold " if d.get("sold") else f"holds {d.get('holdPct')}% ")
    return (f"Dev: {flags}· {d.get('priorTokens')} prior ({d.get('priorMigrated')} migrated, {d.get('priorDead')} dead) "
            f"· dev score {r.get('devScore', 0):+d}\n")
def send(r):
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        print("telegram: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set, skipping", file=sys.stderr); return False
    L = r["links"]
    text = (f"🎯 5R signal: ${r['symbol']} ({r['name']})\n"
            f"MC ${fmt(r['mcap'])} · Liq ${fmt(r['liq'])} · Vol {r['window']} ${fmt(r['vol'])}\n"
            f"5m {r['ch5m']}% · 1h {r['ch1h']}% · {r['buys']}B/{r['sells']}S · age {r['ageH']}h\n"
            f"Top10 {r.get('top10Pct')}% · Cluster {r.get('clusterPct')}% ({r.get('clusterSource')})\n"
            f"{dev_line(r)}"
            f"CA: {r['mint']}\n"
            f"<a href=\"{L['dexscreener']}\">DexScreener</a> | <a href=\"{L['pumpfun']}\">pump.fun</a> | "
            f"<a href=\"{L['bubblemaps']}\">Bubblemaps</a> | <a href=\"{L['insightx']}\">InsightX</a> | <a href=\"{L['x_search']}\">X</a>\n"
            f"⚠️ Not financial advice. DYOR.")
    text = text.replace("&", "&amp;").replace("<a href", "\0").replace("<", "&lt;").replace("\0", "<a href")  # light HTML escape
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data=data, timeout=15); return True
    except Exception as e:
        print(f"telegram error: {e}", file=sys.stderr); return False
