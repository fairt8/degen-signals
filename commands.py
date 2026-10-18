"""Telegram bot commands for Degen: /tokens, /pnl, /help. Shared by listener.py (always-on long polling)
and alert.py (optional getUpdates polling once per workflow run). Only real journal/DexScreener data."""
import datetime as dt, json, os, re, sys, time, urllib.parse, urllib.request
from html import escape as e
import journal as J, notify, pipeline

SIGNALS_URL = os.environ.get("SIGNALS_URL", "https://raw.githubusercontent.com/fairt8/degen-signals/main/docs/signals.json")
LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "signals.json")
PAGE, LIMIT = 20, 3800
HELP = ("<b>Degen bot commands</b>\n"
        "/tokens today|week|month|all [page]: signals in that period (WAT), with CA, alert time, alert MC → now, PnL, top milestone\n"
        "/pnl &lt;CA or $SYMBOL&gt;: live price/MC vs alert, PnL, max gain, milestones, hold vs TP\n"
        "/help: this list\n<i>Not financial advice.</i>")
COMMANDS = [{"command": "tokens", "description": "Signals: today | week | month | all [page]"},
            {"command": "pnl", "description": "PnL for a CA or $SYMBOL"},
            {"command": "help", "description": "How to use the bot"}]
_cache = {"t": 0, "d": None}

def feed(local_first=False):
    """signals.json: GitHub raw (fresh from workflow commits, 60s cache) else the local copy."""
    if local_first and os.path.exists(LOCAL): return json.load(open(LOCAL))
    if time.time() - _cache["t"] < 60 and _cache["d"]: return _cache["d"]
    try:
        d = json.loads(urllib.request.urlopen(urllib.request.Request(f"{SIGNALS_URL}?t={int(time.time())}",
                       headers={"User-Agent": "degen-bot"}), timeout=15).read())
    except Exception as x:
        print("feed fetch failed, using local:", x, file=sys.stderr); d = json.load(open(LOCAL))
    _cache.update(t=time.time(), d=d); return d

def tp_cfg():
    try: return pipeline.load_config().get("tp")
    except Exception: return None

def when(t): return dt.datetime.fromtimestamp(t, J.WAT).strftime("%d %b %H:%M") + " WAT"
def pct(x): return "n/a" if x is None else f"{x:+.1f}%"
def money(x): return "n/a" if not x else "$" + notify.fmt(x)
def mc_of(p): return p.get("marketCap") or p.get("fdv") if p else None

def top_ms(en):
    ms = en.get("milestones") or {}
    keys = list(ms) + (["2"] if en.get("hit2x") else []) + (["5"] if en.get("hit5x") else [])
    return (max(keys, key=float) + "x") if keys else "—"

def live_view(en, p):
    """Hold PnL (24h result if done, else live), max gain incl. live price, TP strategy PnL."""
    price0 = en.get("price0"); live = float(p["priceUsd"]) if p and p.get("priceUsd") else None
    livepct = round((live / price0 - 1) * 100, 1) if live and price0 else None
    if en.get("h24"): hold, basis = en["h24"]["pct"], "24h result"
    elif livepct is not None: hold, basis = livepct, "live"
    else: hold, b = J.ret(en); basis = f"last seen ({b})" if b else "n/a"
    mx = max(filter(None, [en.get("maxPrice"), live if not en.get("h24") else None, price0])) if price0 else None
    en2 = {**en, "maxPrice": mx}
    return {"live": live, "livePct": livepct, "hold": hold, "basis": basis,
            "maxGain": round((mx / price0 - 1) * 100, 1) if mx and price0 else None,
            "tp": J.tp_ret(en2, hold, tp_cfg()) if hold is not None else None}

def chunks(lines, head=""):
    out, cur = [], head
    for l in lines:
        if len(cur) + len(l) + 1 > LIMIT: out.append(cur); cur = ""
        cur += l + "\n"
    if cur.strip(): out.append(cur)
    return out

def cmd_tokens(args):
    period = (args[0].lower() if args else "today")
    period = {"day": "today", "daily": "today", "weekly": "week", "monthly": "month", "alltime": "all"}.get(period, period)
    if period not in ("today", "week", "month", "all"): return ["Usage: /tokens today|week|month|all [page]"]
    page = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) > 0 else 1
    jr = feed().get("journal") or []
    es = sorted([x for x in jr if x["t0"] >= J.period_bounds()[period]], key=lambda x: -x["t0"])
    label = notify.LABELS[period]
    if not es: return [f"No Degen signals in {label} (WAT) yet."]
    pages = (len(es) + PAGE - 1) // PAGE; page = min(page, pages)
    sel = es[(page - 1) * PAGE: page * PAGE]
    px = J.prices([x["mint"] for x in sel])
    lines = []
    for i, x in enumerate(sel, (page - 1) * PAGE + 1):
        p = px.get(x["mint"]); v = live_view(x, p)
        lines.append(f"{i}. <b>${e(x['symbol'])}</b> · {when(x['t0'])}\n<code>{x['mint']}</code>\n"
                     f"MC {money(x.get('mcap0'))} → {money(mc_of(p))} · PnL <b>{pct(v['hold'])}</b> ({v['basis']}) · "
                     f"max {pct(v['maxGain'])} · 🏆 {top_ms(x)}"
                     + (f" · ATH {money(max(x['athMc'], mc_of(p) or 0))}" if x.get("athMc") else "") + "\n")
    head = f"📋 <b>{label} signals (WAT)</b>: {len(es)} total" + (f" · page {page}/{pages}" if pages > 1 else "") + "\n\n"
    msgs = chunks(lines, head)
    if page < pages: msgs[-1] += f"\nMore: /tokens {period} {page + 1}"
    return msgs

def cmd_pnl(args):
    if not args: return ["Usage: /pnl &lt;contract address or $SYMBOL&gt;"]
    q = args[0].strip()
    jr = feed().get("journal") or []
    if re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", q):
        hits = [x for x in jr if x["mint"] == q]
    else:
        s = q.lstrip("$").lower(); hits = sorted([x for x in jr if x["symbol"].lower() == s], key=lambda x: -x["t0"])
    if not hits:
        return [not_signal(q)]
    x = hits[0]; p = J.prices([x["mint"]]).get(x["mint"]); v = live_view(x, p)
    import chart, liquidity
    chart.reset_budget(30)
    a = chart.ath(x["mint"], mc_of(p), v["live"], fallback_pool=(p or {}).get("pairAddress")) if p else None
    if a and a.get("mc"): ath_txt = f"{money(a['mc'])} (chart ATH, {when(a['t'])})" if a.get("t") else f"{money(a['mc'])} (chart ATH)"
    elif x.get("athMc"): ath_txt = f"{money(x['athMc'])} (chart ATH, stored)"
    elif x.get("maxPrice") and x.get("price0") and x.get("mcap0"): ath_txt = f"{money(x['mcap0'] * x['maxPrice'] / x['price0'])} (sampled since alert, est.)"
    else: ath_txt = "n/a"
    lp = liquidity.status(x["mint"], (p or {}).get("pairAddress"), (p or {}).get("dexId")) if p else (x.get("lp") or {})
    lp_txt = lp.get("label") or "n/a"
    ms = x.get("milestones") or {}
    msl = " · ".join(f"{k}x" + (f" ({when(t)})" if t else "") for k, t in sorted(ms.items(), key=lambda kv: float(kv[0]))) or "none yet"
    tpc = {**J.TP_DEFAULT, **(tp_cfg() or {})}
    out = (f"📈 <b>${e(x['symbol'])}</b> (Degen signal)\n<code>{x['mint']}</code>\n"
           f"Alert: {when(x['t0'])}\n"
           f"Price: {notify._price(x.get('price0'))} → {notify._price(v['live'])}\n"
           f"MC: {money(x.get('mcap0'))} → {money(mc_of(p))}\n"
           f"Live vs alert: <b>{pct(v['livePct'])}</b>\n"
           + (f"1h: {pct(x['h1']['pct'])}" if x.get("h1") else "1h: pending") + " · "
           + (f"24h: {pct(x['h24']['pct'])}" if x.get("h24") else "24h: pending") + "\n"
           f"Max gain since alert: {pct(v['maxGain'])} ({'chart high' if x.get('maxSrc') == 'chart' else 'sampled ~15 min'})\n"
           f"🏔 ATH MC: {ath_txt}\n"
           f"🔐 LP: {e(lp_txt)}\n"
           f"🏆 Milestones: {msl}\n"
           f"Hold PnL: <b>{pct(v['hold'])}</b> ({v['basis']}) · TP {tpc['sellFrac']*100:.0f}% @ +{tpc['atPct']:.0f}%: <b>{pct(v['tp'])}</b>\n"
           f'<a href="{e(x.get("link") or "https://dexscreener.com/solana/" + x["mint"])}">DexScreener</a> · '
           f'<a href="https://fomo.family/tokens/solana/{x["mint"]}">Fomo</a>')
    if len(hits) > 1: out += f"\n<i>{len(hits)} signals share this symbol; showing the latest. Use the CA for others.</i>"
    return [out]

def not_signal(q):
    try:
        if re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", q): ps = pipeline.get(f"{pipeline.DS}/tokens/v1/solana/{q}")
        else:
            s = q.lstrip("$").lower()
            ps = [p for p in (pipeline.get(f"{pipeline.DS}/latest/dex/search?q={urllib.parse.quote(s)}").get("pairs") or [])
                  if p.get("chainId") == "solana" and p["baseToken"]["symbol"].lower() == s]
    except Exception: ps = []
    if not ps: return f"❔ {e(q)} is not a Degen signal, and no live Solana pair was found on DexScreener."
    p = max(ps, key=lambda p: (p.get("liquidity") or {}).get("usd", 0))
    return (f"❔ <b>${e(p['baseToken']['symbol'])}</b> is <b>not a Degen signal</b> (not in our journal).\n"
            f"<code>{p['baseToken']['address']}</code>\nLive price: {notify._price(float(p['priceUsd']) if p.get('priceUsd') else None)} · "
            f"MC: {money(mc_of(p))} · Liq: {money((p.get('liquidity') or {}).get('usd'))}\n"
            f'<a href="{e(p.get("url") or "")}">DexScreener</a> · <a href="https://fomo.family/tokens/solana/{p["baseToken"]["address"]}">Fomo</a>')

def handle(text, bot_username=None):
    """Returns list of HTML messages, or None if not a command for us."""
    if not text or not text.startswith("/"): return None
    parts = text.split(); cmd = parts[0][1:]
    if "@" in cmd:
        cmd, who = cmd.split("@", 1)
        if bot_username and who.lower() != bot_username.lower(): return None
    cmd = cmd.lower()
    try:
        if cmd == "tokens": return cmd_tokens(parts[1:])
        if cmd == "pnl": return cmd_pnl(parts[1:])
        if cmd in ("help", "start"): return [HELP]
    except Exception as x:
        print("command error:", repr(x), file=sys.stderr); return ["⚠️ Error handling that command, try again shortly."]
    return None

# ---------- Telegram plumbing ----------
def poll(offset, wait=0):
    """getUpdates; wait = Telegram long-poll seconds (separate from the HTTP timeout)."""
    return api("getUpdates", http_timeout=wait + 15, offset=offset or 0, allowed_updates=["message", "channel_post"], **{"timeout": wait})

def api(method, http_timeout=40, **q):
    tok = os.environ["TELEGRAM_BOT_TOKEN"]
    data = urllib.parse.urlencode({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in q.items()}).encode()
    return json.loads(urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/{method}", data=data, timeout=http_timeout).read())

def allowed():
    return {str(c) for c in notify.chats()} | {c.strip() for c in os.environ.get("TELEGRAM_ALLOWED_CHATS", "").split(",") if c.strip()}

def reply(chat, mid, msgs):
    for i, m in enumerate(msgs):
        q = {"chat_id": chat, "text": m, "parse_mode": "HTML", "disable_web_page_preview": "true"}
        if i == 0 and mid: q.update(reply_to_message_id=mid, allow_sending_without_reply="true")
        api("sendMessage", http_timeout=20, **q)

def process(updates, bot_username, ok_chats):
    """Handle a batch of updates; returns next offset."""
    nxt = None
    for u in updates:
        nxt = u["update_id"] + 1
        m = u.get("message") or u.get("channel_post") or {}
        chat = str((m.get("chat") or {}).get("id"))
        if chat not in ok_chats: continue
        msgs = handle(m.get("text") or "", bot_username)
        if msgs:
            try: reply(chat, m.get("message_id"), msgs)
            except Exception as x: print("reply failed:", x, file=sys.stderr)
            print(time.strftime("%F %T"), "handled", repr((m.get("text") or "")[:60]), "chat", chat, file=sys.stderr)
    return nxt

def poll_once(offset):
    """Non-blocking getUpdates for workflow runs. Returns new offset (or the old one on error/conflict)."""
    try:
        me = api("getMe", http_timeout=15)["result"]["username"]
        r = poll(offset, 0)
        nxt = process(r.get("result") or [], me, allowed())
        return nxt or offset
    except Exception as x:
        print("command polling skipped:", str(x)[:150], file=sys.stderr); return offset

def set_commands():
    for scope in ({"type": "default"}, {"type": "all_private_chats"}, {"type": "all_group_chats"}):
        print(scope["type"], api("setMyCommands", commands=COMMANDS, scope=scope).get("ok"))

if __name__ == "__main__":  # local test: python3 commands.py "/tokens today"
    if sys.argv[1:2] == ["--set-commands"]: set_commands()
    else:
        for m in handle(" ".join(sys.argv[1:])) or ["(not a command)"]: print(m, "\n-----")
