"""Telegram poster. Token: DEGEN_TELEGRAM_BOT_TOKEN on the box; TELEGRAM_BOT_TOKEN only in GitHub Actions (repo secret name).
Chats: TELEGRAM_CHAT_ID or TELEGRAM_CHAT_IDS (comma-separated, e.g. 123,-100456)."""
import json, os, sys, urllib.error, urllib.parse, urllib.request
def fmt(n): return f"{n/1e6:.2f}M" if n >= 1e6 else f"{n/1e3:.1f}K" if n >= 1e3 else f"{n:.0f}"
def dev_line(r):
    d = r.get("dev") or {}
    if not d.get("wallet"): return ""
    flags = ("🚩rug history " if d.get("rugHistory") else "") + ("sold " if d.get("sold") else f"holds {d.get('holdPct')}% ")
    return (f"Dev: {flags}· {d.get('priorTokens')} prior ({d.get('priorMigrated')} migrated, {d.get('priorDead')} dead) "
            f"· dev score {r.get('devScore', 0):+d}\n")
import os as _os
def bot_token():
    """Degen bot token. On the box only DEGEN_TELEGRAM_BOT_TOKEN is used (TELEGRAM_BOT_TOKEN there may belong to
    another bot); GitHub Actions uses the TELEGRAM_BOT_TOKEN secret."""
    if _os.environ.get("DEGEN_TELEGRAM_BOT_TOKEN"): return _os.environ["DEGEN_TELEGRAM_BOT_TOKEN"]
    if _os.environ.get("GITHUB_ACTIONS") == "true": return _os.environ.get("TELEGRAM_BOT_TOKEN")
    return None

def chats():
    raw = _os.environ.get("TELEGRAM_CHAT_IDS") or _os.environ.get("TELEGRAM_CHAT_ID") or ""
    return [c.strip() for c in raw.split(",") if c.strip()]

def post(text, reply_to=None, buttons=None):
    """Post to every chat in TELEGRAM_CHAT_ID(S) (comma-separated). DRY_RUN=1 prints instead.
    reply_to: {chat_id: message_id} (or int for legacy single-chat). Returns {chat_id: message_id} for successes."""
    tok, cs = bot_token(), chats()
    if _os.environ.get("DRY_RUN"):
        print(f"[DRY_RUN telegram -> {len(cs)} chats]", text.replace("\n", " | ")[:300], file=sys.stderr); return {}
    if not tok or not cs:
        print("telegram: Degen bot token (DEGEN_TELEGRAM_BOT_TOKEN on box / TELEGRAM_BOT_TOKEN in Actions) or TELEGRAM_CHAT_ID not set, skipping", file=sys.stderr); return {}
    out = {}
    for chat in cs:
        q = {"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}
        rid = reply_to.get(chat) if isinstance(reply_to, dict) else (reply_to if len(cs) == 1 else None)
        if rid and rid > 0: q.update(reply_to_message_id=rid, allow_sending_without_reply="true")
        if buttons: q["reply_markup"] = json.dumps({"inline_keyboard": buttons})
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
def ms_line(s):
    """Milestone counts: 2x and 5x always, higher ones only when hit."""
    ms = s.get("milestones") or {}
    keys = sorted(ms, key=float)
    parts = [f"{k}x {ms.get(k, 0)}" for k in keys if k in ("2", "5") or ms.get(k)]
    return " · ".join(parts) if parts else f"2x {s.get('hit2x', 0)} · 5x {s.get('hit5x', 0)}"

def tp_label():
    try:
        import pipeline; t = pipeline.load_config().get("tp") or {}
    except Exception: t = {}
    f, at = t.get("sellFrac", 0.5), t.get("atPct", 100)
    return f"TP {f*100:.0f}% @{1+at/100:g}x" + (f" SL {t['stopLossPct']}%" if t.get("stopLossPct") is not None else "")

def pnl_report(ps, slot, day_label="Today"):
    """Standalone PnL report (sent 12:00 AM / 12:00 PM WAT). ps = period_stats; day_label for the 'today' row."""
    date, half = slot.rsplit("-", 1)
    when = "12:00 AM" if half == "AM" else "12:00 PM"
    rows = []
    for k in ("today", "week", "month", "all"):
        s = ps[k]; label = day_label if k == "today" else LABELS[k]
        if not s["signals"]:
            rows.append(f"<b>{label}</b>: no signals"); continue
        rows.append(f"<b>{label}</b>: {s['signals']} signals\n"
                    f"Hold: Total {_pct(s['totalPnl'])} · Avg {_pct(s['avgPnl'])} · Win {_wr(s)}\n"
                    + (f"{tp_label()}: Total {_pct(s['tpTotalPnl'])} · Avg {_pct(s['tpAvgPnl'])} · Win "
                       + ("n/a" if s.get('tpWinRate') is None else f"{s['tpWinRate']:.0f}% ({s['tpWins']}/{s['n']})") + "\n" if 'tpTotalPnl' in s else "")
                    + e_(f"Best {s['best'] or 'n/a'} · Worst {s['worst'] or 'n/a'}") + "\n🚀 " + ms_line(s))
    a = ps["all"]["basis"]
    return "\n\n".join([f"📊 <b>Degen Signals PnL report: {date} {when} WAT</b>"] + rows +
        [f"<i>{BASIS} (all-time: {a['24h']} at 24h, {a['live']} live). TP = simulated: sell part at the target if the max gain seen reached it, rest at the hold basis. Max gain is sampled about every 15 min, so real peaks may be higher or lower. Win = PnL above the configured threshold. Not financial advice.</i>"])
def e_(s):
    from html import escape; return escape(s, quote=False)

def ath(r, journal=None):
    """(ath_mc, label). GMGN token info -> pump.fun ath field -> highest MC seen in our journal (est.)."""
    import gmgn
    v = gmgn.ath_mc(r["mint"]) if r.get("chain") == "solana" else None
    if v: return max(v, r["mcap"]), " (GMGN)"
    c = r.get("chartAth") or {}
    if c.get("mc"):  # real high from OHLCV candles (GeckoTerminal)
        import time as _t
        when = _t.strftime("%d %b %H:%M", _t.gmtime(c["t"] + 3600)) + " WAT" if c.get("t") else ""
        return max(c["mc"], r["mcap"]), f" (chart ATH{', ' + when if when else ''})"
    try:
        req = urllib.request.Request(f"https://frontend-api-v3.pump.fun/coins/{r['mint']}", headers={"User-Agent": "Mozilla/5.0"})
        d = json.loads(urllib.request.urlopen(req, timeout=8).read())
        v = d.get("ath_market_cap") or d.get("athMarketCap")
        if v: return max(float(v), r["mcap"]), ""
    except Exception: pass
    # fallback: highest MC the bot itself saw (journal max since alert, first-scan MC, current MC)
    seen = [r.get("mcap") or 0, (r.get("firstScan") or {}).get("mc") or 0]
    for e in journal or []:
        if e.get("mint") == r["mint"] and e.get("price0") and e.get("maxPrice") and e.get("mcap0"):
            seen.append(e["mcap0"] * e["maxPrice"] / e["price0"])
    return (max(seen), " (est., seen by bot)") if max(seen) else (None, "")

def _num(x, d=1):
    return "n/a" if x is None else f"{x:.{d}f}"

def _age(h):
    if h is None: return "n/a"
    m = h * 60
    return f"{m:.0f}m" if m < 60 else f"{h:.1f}h" if h < 48 else f"{h/24:.0f}d"

def _price(p):
    if not p: return "n/a"
    return f"${p:.10f}".rstrip("0") if p < 0.01 else f"${p:,.4f}"

def _yn(v):
    return "✅" if v is True else "❌" if v is False else "n/a"

def card(r, journal=None):
    """PIRB-style alert. Returns (html_text, inline_keyboard). Only real data; 'n/a' when unknown."""
    from html import escape as e
    import time as _t
    L, H, G = r["links"], r.get("holders") or {}, r.get("gmgn") or {}
    gp = G.get("pct") or {} if G.get("status") in ("PASS", "FAIL") else {}
    gp = {**((r.get("safety") or {}).get("pct") or {}), **gp}  # InsightX / rugcheck / RPC %s, GMGN on top when keyed
    dexname = {"pumpfun": "PF", "pumpswap": "PumpSwap"}.get(r.get("dex"), (r.get("dex") or "DEX").title())
    chain = "SOL" if r.get("chain") == "solana" else (r.get("chain") or "").upper()
    # emoji link row from the token's own socials/websites
    soc = []
    for u in r.get("socials") or []:
        ul = u.lower()
        icon = "🐦" if ("twitter" in ul or "x.com" in ul) else "💬" if ("t.me" in ul or "telegram" in ul) else "👾" if "discord" in ul else "🔗"
        soc.append(f'<a href="{e(u)}">{icon}</a>')
    soc += [f'<a href="{e(u)}">🌐</a>' for u in (r.get("websites") or [])[:2]]
    soc.append(f'<a href="{e(L["x_search"])}">🔍</a>')
    if L.get("pumpfun"): soc.append(f'<a href="{e(L["pumpfun"])}">💊</a>')
    if L.get("fomo"): soc.append(f'<a href="{e(L["fomo"])}">🟢 Fomo</a>')
    if L.get("axiom"): soc.append(f'<a href="{e(L["axiom"])}">⚡ Axiom</a>')
    if L.get("bullx"): soc.append(f'<a href="{e(L["bullx"])}">🐂 BullX</a>')
    # TOKEN DATA
    od = r.get("odds") or {}
    odds = (f"2x ~{od['x2']}% · Rug ~{od['rug']}% <i>(our past {od['n']} signals)</i>" if od.get("n") else "2x n/a · Rug n/a <i>(no history yet)</i>")
    fsn = r.get("firstScan")
    a, lbl = ath(r, journal)
    if fsn and fsn.get("mc"):
        ago = _age((_t.time() - fsn["t"]) / 3600)
        mcl = f"<b>${fmt(fsn['mc'])}</b> ⇨ ${fmt(r['mcap'])} [{ago}]"
    else:
        mcl = f"${fmt(r['mcap'])}"
    gl = __import__("safety").line(r.get("safety"))
    if G.get("status") in ("PASS", "FAIL"): gl += " | " + __import__("gmgn").line(G)
    ch = r.get("ch24h")
    sc = r.get("score")
    scl = ("n/a" if sc is None else f"<b>{sc}/100</b>" + (f" (capped at {sc}, would be {r.get('scoreUncapped')})" if r.get("scoreCapped") else ""))
    vl = r.get("volLiq"); B = {}
    try:
        import pipeline as _pl; B = _pl.load_config().get("behaviour") or {}
    except Exception: pass
    vflag = "" if vl is None else (" 🔴 inflated?" if vl >= B.get("volLiqRed", 40) else " 🟠 inflated?" if vl >= B.get("volLiqAmber", 20) else "")
    tok = ["━━ TOKEN DATA ━━",
           f"⭐ Score: {scl}",
           f"🤖 {odds}",
           f"🎯 {e(gl)}",
           f"🧢 MC: {mcl}" + (f" | ATH <b>${fmt(a)}</b>" if a else ""),
           f"🏔 ATH MC: {e(('$' + fmt(a) + lbl) if a else 'n/a')}",
           f"💧 Liq: <b>${fmt(r['liq'])}</b> ({_num(r.get('liqPctMc'), 0)}%)",
           f"🔐 LP: {e((r.get('lp') or {}).get('label') or 'n/a')}",
           f"💲 USD: <b>{_price(r.get('priceUsd'))}</b> ({'n/a' if ch is None else f'{ch:+.0f}%'} 24h)",
           f"📊 Vol {r['window']}: <b>${fmt(r['vol'])}</b> (🅑{r['buys']}/Ⓢ{r['sells']})",
           f"🔄 Vol24h/Liq: {'n/a' if vl is None else f'{vl}x'}{vflag}"]
    # DEV INFO
    d = r.get("dev") or {}
    o = r.get("orders") or {}
    if d.get("wallet"):
        held = "sold" if d.get("sold") else f"Held: {_num(d.get('holdPct'))}%"
        devl = (f'<a href="{e(d["links"]["solscan"])}">{e(d["wallet"][:4])}…{e(d["wallet"][-4:])}</a> · {held}'
                + (" · 🚩rug history" if d.get("rugHistory") else ""))
        prior = f"Prior launches: {d.get('priorTokens', 'n/a')} ({d.get('priorMigrated', 0)} migrated, {d.get('priorDead', 0)} dead)"
    else:
        devl, prior = "n/a", "Prior launches: n/a"
    dev = ["━━ DEV INFO ━━", f"👨‍💻 {devl}", f"📜 {prior}", f"🦅 Dex Paid: {_yn(o.get('dexPaid'))} · CTO: {_yn(r.get('cto'))}"]
    # HOLDERS INFO
    t5 = H.get("top5") or []
    t5l = ("·".join(f"{x:.1f}" for x in t5) + f" [{_num(H.get('top5Pct'), 0)}%]") if t5 else "n/a"
    cnt = H.get("count")
    pct = lambda v: "n/a" if v is None else f"{v:.1f}%"
    insider = gp.get("insider", H.get("insiderPct"))
    fresh = pct(gp["fresh"]) if "fresh" in gp else (f"{H['freshWallets']}/10 top" if H.get("freshWallets") is not None else "n/a")
    smart = pct((gp.get("smart") or 0) + (gp.get("kol") or 0)) if "smart" in gp else "n/a"
    hol = ["━━ HOLDERS INFO ━━",
           f"🔝 Top5: {t5l} | {f'{cnt:,}' if cnt else 'n/a'} holders",
           f"🎯 {pct(gp.get('sniper'))} · 📦 {pct(gp.get('bundler'))} · 🕵️ {pct(insider)}",
           f"🐋 {pct(H.get('whalePct'))} · 🧠 {smart}" + ("" if r.get("behaviour") else f" · 🌱 {fresh}"),
           f"🔗 Cluster: {pct(H.get('clusterPct', r.get('clusterPct')))}"]
    bh = r.get("behaviour") or {}
    bp = lambda k: "n/a" if bh.get(k + "Pct") is None else f"{bh[k + 'Pct']}% ({bh.get(k + 'N')})"
    hol.append(f"🤖 Bots {bp('bot')} · 🔁 Flippers {bp('flipper')} · 🌱 Fresh≤7d {bp('fresh')}"
               + (f" <i>[{bh.get('source')}, top {bh.get('sampled')}]</i>" if bh.get("sampled") else ""))
    # MISC
    misc = ["━━ MISC INFO ━━", f"📈 Narrative: {e(' · '.join(r.get('narratives') or []) or 'n/a')}",
            f"1️⃣ First scan @ MC {('$' + fmt(fsn['mc'])) if fsn else 'n/a'}"]
    head = (f"<code>{e(r['mint'])}</code>\n"
            f"<b>{e(r['name'])} (${e(r['symbol'])})</b> | {chain} · {e(dexname)}\n"
            f"🕐 {_age(r.get('ageH'))} · 👥 {f'{cnt:,}' if cnt else 'n/a'} holders\n"
            + " ".join(soc))
    body = "\n".join(tok) + "\n\n" + "\n".join(dev) + "\n\n" + "\n".join(hol) + "\n\n" + "\n".join(misc)
    fnd = r.get("findings") or []
    if fnd:
        nr = sum(1 for s, _ in fnd if s == "red"); na = len(fnd) - nr
        body += f"\n\n━━ FINDINGS ━━\n🚦 {nr} red, {na} amber\n" + "\n".join(("🔴 " if s == "red" else "🟠 ") + e(t) for s, t in fnd[:4]) + (f"\n… +{len(fnd)-4} more on site" if len(fnd) > 4 else "")
    elif r.get("findings") is not None:
        body += "\n\n━━ FINDINGS ━━\n🚦 0 red, 0 amber"
    text = head + "\n\n<blockquote>" + body + "</blockquote>\n⚠️ Not financial advice. DYOR."
    if (r.get("description") or "").strip():
        text += f"\n\n<i>{e(r['description'].strip()[:400])}</i>"
    gm = G.get("link") or f"https://gmgn.ai/sol/token/{r['mint']}"
    kb = [[{"text": "DexScreener", "url": L["dexscreener"]}, {"text": "GMGN", "url": gm}, {"text": "Bubblemaps", "url": L["bubblemaps"]}],
          [{"text": "⚡ Axiom", "url": L.get("axiom") or f"https://axiom.trade/t/{r['mint']}?chain=sol"},
           {"text": "🐂 BullX", "url": L.get("bullx") or f"https://neo.bullx.io/terminal?chainId=1399811149&address={r['mint']}"},
           {"text": "🟢 Fomo", "url": L.get("fomo") or f"https://fomo.family/tokens/solana/{r['mint']}"}],
          [{"text": "🥷 Shuriken", "url": L.get("shuriken") or "https://t.me/shuriken_trade_bot"}, {"text": "X search", "url": L["x_search"]}]
          + ([{"text": "pump.fun", "url": L["pumpfun"]}] if L.get("pumpfun") else []),
          [{"text": "📱 Open in Degen app", "url": app_link(r["mint"])}]]
    return text, kb

def app_link(mint):
    """t.me Mini App deep link (works in groups, opens inside Telegram) once configured in BotFather, else the website."""
    try:
        import pipeline as _pl; a = _pl.load_config().get("app") or {}
    except Exception: a = {}
    if a.get("tme"): return f"{a['tme']}?startapp={mint}"
    return f"{a.get('url') or 'https://fairt8.github.io/degen-signals/app/'}?ca={mint}"

def send(r, journal=None):
    text, kb = card(r, journal)
    return post(text, buttons=kb)
