// Degen Telegram command bot as a Cloudflare Worker webhook (free tier: 100k requests/day).
// Reads the journal from signals.json (GitHub raw / Pages) and live prices from DexScreener.
// Secrets: TELEGRAM_BOT_TOKEN, WEBHOOK_SECRET.  Vars: ALLOWED_CHATS ("1318404489,-1004348482526"),
// SIGNALS_URL, BOT_USERNAME, TP_AT_PCT (100), TP_SELL_FRAC (0.5).  Not financial advice.
const DS = "https://api.dexscreener.com";
const PAGE = 20, LIMIT = 3800;
const LABEL = { today: "Today", week: "Week", month: "Month", all: "All-time" };
const WAT = 3600; // UTC+1
const esc = s => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const pct = x => x == null ? "n/a" : (x >= 0 ? "+" : "") + x.toFixed(1) + "%";
const fmt = n => n >= 1e6 ? (n / 1e6).toFixed(2) + "M" : n >= 1e3 ? (n / 1e3).toFixed(1) + "K" : n.toFixed(0);
const money = x => x ? "$" + fmt(x) : "n/a";
const price = p => p == null ? "n/a" : p >= 1 ? "$" + p.toFixed(4) : "$" + Number(p.toPrecision(4)).toFixed(Math.max(2, -Math.floor(Math.log10(p)) + 3));
const when = t => { const d = new Date((t + WAT) * 1000);
  const m = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][d.getUTCMonth()];
  return `${String(d.getUTCDate()).padStart(2, "0")} ${m} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} WAT`; };
const mcOf = p => p ? (p.marketCap || p.fdv) : null;
const CA = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;

function bounds(now = Date.now() / 1000) {
  const w = new Date((now + WAT) * 1000); w.setUTCHours(0, 0, 0, 0);
  const day = w.getTime() / 1000 - WAT, dow = (w.getUTCDay() + 6) % 7;
  const m = new Date(w); m.setUTCDate(1);
  return { today: day, week: day - dow * 86400, month: m.getTime() / 1000 - WAT, all: 0 };
}
async function feed(env) {
  const r = await fetch(env.SIGNALS_URL + "?t=" + Math.floor(Date.now() / 60000), { cf: { cacheTtl: 60 } });
  return r.json();
}
// signals.json keeps the last 30 days; older signals live in archive/YYYY-MM.json (listed in feed.archive.files).
async function archived(env, f) {
  const files = f.archive?.files || [], base = env.SIGNALS_URL.replace(/signals\.json$/, "archive/"), out = [];
  const ds = await Promise.all(files.map(n => fetch(base + n + "?t=" + Math.floor(Date.now() / 600000), { cf: { cacheTtl: 600 } })
    .then(r => r.ok ? r.json() : {}).catch(() => ({}))));
  for (const d of ds) out.push(...(d.journal || []));
  return out;
}
// journal incl. archive when needed (periods reaching past the feed's oldest entry, or a lookup miss)
async function journal(env, since = null, mint = null, sym = null) {
  const f = await feed(env), jr = f.journal || [];
  if (!(f.archive?.files || []).length) return jr;
  const oldest = jr.length ? Math.min(...jr.map(e => e.t0)) : Infinity;
  const miss = (mint && !jr.some(e => e.mint === mint)) || (sym && !jr.some(e => e.symbol.toLowerCase() === sym));
  if (!(since !== null && since < oldest) && !miss) return jr;
  const seen = new Set(jr.map(e => e.mint));
  return jr.concat((await archived(env, f)).filter(e => !seen.has(e.mint)));
}
async function prices(mints) {
  const out = {};
  for (let i = 0; i < mints.length; i += 30) {
    try {
      const ps = await (await fetch(`${DS}/tokens/v1/solana/${mints.slice(i, i + 30).join(",")}`)).json();
      for (const p of ps) { const m = p.baseToken.address, l = p.liquidity?.usd || 0;
        if (!out[m] || l > (out[m].liquidity?.usd || 0)) out[m] = p; }
    } catch (e) {}
  }
  return out;
}
function ret(e) {
  if (e.h24) return [e.h24.pct, "24h result"];
  if (e.lastPct != null) return [e.lastPct, "last seen (live)"];
  if (e.h1) return [e.h1.pct, "last seen (live)"];
  return [null, "n/a"];
}
function view(e, p, env) {
  const p0 = e.price0, live = p?.priceUsd ? +p.priceUsd : null;
  const livePct = live && p0 ? Math.round((live / p0 - 1) * 1000) / 10 : null;
  let [hold, basis] = e.h24 ? [e.h24.pct, "24h result"] : livePct != null ? [livePct, "live"] : ret(e);
  const mx = p0 ? Math.max(e.maxPrice || 0, e.h24 ? 0 : (live || 0), p0) : null;
  const maxGain = mx && p0 ? Math.round((mx / p0 - 1) * 1000) / 10 : null;
  const at = +(env.TP_AT_PCT || 100), f = +(env.TP_SELL_FRAC || 0.5);
  const tp = hold == null ? null : maxGain >= at ? Math.round((f * at + (1 - f) * hold) * 10) / 10 : hold;
  return { live, livePct, hold, basis, maxGain, tp, at, f };
}
const topMs = e => { const k = Object.keys(e.milestones || {}).concat(e.hit2x ? ["2"] : [], e.hit5x ? ["5"] : []);
  return k.length ? Math.max(...k.map(Number)) + "x" : "—"; };
function chunks(lines, head) {
  const out = []; let cur = head;
  for (const l of lines) { if (cur.length + l.length + 1 > LIMIT) { out.push(cur); cur = ""; } cur += l + "\n"; }
  if (cur.trim()) out.push(cur); return out;
}
async function cmdTokens(args, env) {
  let period = (args[0] || "today").toLowerCase();
  period = { day: "today", daily: "today", weekly: "week", monthly: "month", alltime: "all" }[period] || period;
  if (!LABEL[period]) return ["Usage: /tokens today|week|month|all [page]"];
  let page = Math.max(1, parseInt(args[1]) || 1);
  const b = bounds()[period], jr = await journal(env, b);
  const es = jr.filter(e => e.t0 >= b).sort((a, c) => c.t0 - a.t0);
  if (!es.length) return [`No Degen signals in ${LABEL[period]} (WAT) yet.`];
  const pages = Math.ceil(es.length / PAGE); page = Math.min(page, pages);
  const sel = es.slice((page - 1) * PAGE, page * PAGE), px = await prices(sel.map(e => e.mint));
  const lines = sel.map((e, i) => { const p = px[e.mint], v = view(e, p, env);
    return `${(page - 1) * PAGE + i + 1}. <b>$${esc(e.symbol)}</b> · ${when(e.t0)}\n<code>${e.mint}</code>\n` +
      `MC ${money(e.mcap0)} → ${money(mcOf(p))} · PnL <b>${pct(v.hold)}</b> (${v.basis}) · max ${pct(v.maxGain)} · 🏆 ${topMs(e)}` +
      (e.athMc ? ` · ATH ${money(Math.max(e.athMc, mcOf(p) || 0))}` : "") + "\n"; });
  const msgs = chunks(lines, `📋 <b>${LABEL[period]} signals (WAT)</b>: ${es.length} total` + (pages > 1 ? ` · page ${page}/${pages}` : "") + "\n\n");
  if (page < pages) msgs[msgs.length - 1] += `\nMore: /tokens ${period} ${page + 1}`;
  return msgs;
}
async function notSignal(q) {
  let ps = [];
  try {
    if (CA.test(q)) ps = await (await fetch(`${DS}/tokens/v1/solana/${q}`)).json();
    else { const s = q.replace(/^\$/, "").toLowerCase();
      ps = ((await (await fetch(`${DS}/latest/dex/search?q=${encodeURIComponent(s)}`)).json()).pairs || [])
        .filter(p => p.chainId === "solana" && p.baseToken.symbol.toLowerCase() === s); }
  } catch (e) {}
  if (!ps.length) return `❔ ${esc(q)} is not a Degen signal, and no live Solana pair was found on DexScreener.`;
  const p = ps.reduce((a, c) => (c.liquidity?.usd || 0) > (a.liquidity?.usd || 0) ? c : a);
  return `❔ <b>$${esc(p.baseToken.symbol)}</b> is <b>not a Degen signal</b> (not in our journal).\n<code>${p.baseToken.address}</code>\n` +
    `Live price: ${price(p.priceUsd ? +p.priceUsd : null)} · MC: ${money(mcOf(p))} · Liq: ${money(p.liquidity?.usd)}\n<a href="${esc(p.url)}">DexScreener</a> · <a href="https://fomo.family/tokens/solana/${p.baseToken.address}">Fomo</a>`;
}
async function cmdPnl(args, env) {
  if (!args.length) return ["Usage: /pnl &lt;contract address or $SYMBOL&gt;"];
  const q = args[0].trim(), jr = CA.test(q) ? await journal(env, null, q) : await journal(env, null, null, q.replace(/^\$/, "").toLowerCase());
  const hits = CA.test(q) ? jr.filter(e => e.mint === q)
    : jr.filter(e => e.symbol.toLowerCase() === q.replace(/^\$/, "").toLowerCase()).sort((a, c) => c.t0 - a.t0);
  if (!hits.length) return [await notSignal(q)];
  const e = hits[0], p = (await prices([e.mint]))[e.mint], v = view(e, p, env);
  const ms = Object.entries(e.milestones || {}).sort((a, c) => a[0] - c[0]).map(([k, t]) => `${k}x` + (t ? ` (${when(t)})` : "")).join(" · ") || "none yet";
  let out = `📈 <b>$${esc(e.symbol)}</b> (Degen signal)\n<code>${e.mint}</code>\nAlert: ${when(e.t0)}\n` +
    `Price: ${price(e.price0)} → ${price(v.live)}\nMC: ${money(e.mcap0)} → ${money(mcOf(p))}\nLive vs alert: <b>${pct(v.livePct)}</b>\n` +
    `${e.h1 ? "1h: " + pct(e.h1.pct) : "1h: pending"} · ${e.h24 ? "24h: " + pct(e.h24.pct) : "24h: pending"}\n` +
    `Max gain since alert: ${pct(v.maxGain)} (${e.maxSrc === "chart" ? "chart high" : "sampled ~15 min"})\n` +
    `🏔 ATH MC: ${e.athMc ? (mcOf(p) > e.athMc ? money(mcOf(p)) + " (new high now)" : money(e.athMc) + " (chart ATH" + (e.athT ? ", " + when(e.athT) : "") + ")") : (e.maxPrice && e.price0 ? money(e.mcap0 * e.maxPrice / e.price0) + " (sampled since alert, est.)" : "n/a")}\n` +
    `🎯 Safety check: ${esc(e.safety?.status || "n/a")}${({PASS: " ✅", WARN: " 🟠", FAIL: " ❌"})[e.safety?.status] || ""}${e.safety?.reasons?.length ? " · " + esc(e.safety.reasons.slice(0, 3).join("; ")) : ""}` +
    `${["PASS", "FAIL"].includes(e.gmgn?.status) ? " | GMGN: " + e.gmgn.status : ""}\n` +
    `🔐 LP: ${esc(e.lp?.label || "n/a")}${e.lp?.t ? " <i>(checked " + when(e.lp.t) + ")</i>" : ""}\n🏆 Milestones: ${ms}\n` +
    `Hold PnL: <b>${pct(v.hold)}</b> (${v.basis}) · TP ${v.f * 100}% @ +${v.at}%: <b>${pct(v.tp)}</b>\n` +
    `<a href="${esc(e.link || "https://dexscreener.com/solana/" + e.mint)}">DexScreener</a> · <a href="https://fomo.family/tokens/solana/${e.mint}">Fomo</a> · ` +
    `<a href="https://axiom.trade/t/${e.mint}?chain=sol">Axiom</a> · <a href="https://neo.bullx.io/terminal?chainId=1399811149&address=${e.mint}">BullX</a> · <a href="https://t.me/shuriken_trade_bot">Shuriken</a>`;
  if (hits.length > 1) out += `\n<i>${hits.length} signals share this symbol; showing the latest. Use the CA for others.</i>`;
  return [out];
}
const HELP = "<b>Degen bot commands</b>\n/tokens today|week|month|all [page]: signals in that period (WAT), with CA, alert time, alert MC → now, PnL, top milestone\n" +
  "/pnl &lt;CA or $SYMBOL&gt;: live price/MC vs alert, PnL, max gain, milestones, hold vs TP\n/app: open the Degen mini app\n/help: this list\n<i>Not financial advice.</i>";
export async function handle(text, env) {
  if (!text || !text.startsWith("/")) return null;
  const parts = text.trim().split(/\s+/); let [cmd, who] = parts[0].slice(1).split("@");
  if (who && env.BOT_USERNAME && who.toLowerCase() !== env.BOT_USERNAME.toLowerCase()) return null;
  cmd = cmd.toLowerCase();
  try {
    if (cmd === "tokens") return await cmdTokens(parts.slice(1), env);
    if (cmd === "pnl") return await cmdPnl(parts.slice(1), env);
    if (cmd === "help") return [HELP];
    if (cmd === "app" || cmd === "start") return "APP";
  } catch (e) { return ["⚠️ Error handling that command, try again shortly."]; }
  return null;
}
export function appReply(env, chatType) {
  // web_app buttons only work in private chats; groups get a url button (t.me Mini App link once set in BotFather, else the website)
  const url = env.APP_URL || "https://fairt8.github.io/degen-signals/app/";
  const btn = chatType === "private" ? { text: "📱 Open Degen app", web_app: { url } } : { text: "📱 Open Degen app", url: env.APP_TME_LINK || url };
  return { text: "📱 <b>Degen Signals app</b>: signals feed, PnL dashboard, token lookup and per-token details (chart ATH, LP status, findings, links).\n<i>Not financial advice.</i>",
           markup: { inline_keyboard: [[btn]] } };
}
async function send(env, chat, text, replyTo, markup) {
  const body = { chat_id: chat, text, parse_mode: "HTML", disable_web_page_preview: true };
  if (markup) body.reply_markup = markup;
  if (replyTo > 0) Object.assign(body, { reply_to_message_id: replyTo, allow_sending_without_reply: true });
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`,
    { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  return r.ok;
}
export default {
  async fetch(req, env, ctx) {
    if (req.method !== "POST") return new Response("degen bot ok");
    if (req.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) return new Response("forbidden", { status: 403 });
    const u = await req.json(), m = u.message || u.channel_post || {};
    const chat = String(m.chat?.id), ok = (env.ALLOWED_CHATS || "").split(",").map(s => s.trim());
    if (!ok.includes(chat)) return new Response("ignored");
    const work = (async () => {
      let msgs = await handle(m.text || "", env), sent = 0;
      if (msgs === "APP") msgs = [appReply(env, m.chat?.type)];
      for (let i = 0; msgs && i < msgs.length; i++) {
        const x = typeof msgs[i] === "string" ? { text: msgs[i] } : msgs[i];
        sent += await send(env, chat, x.text, i === 0 ? m.message_id : null, x.markup) ? 1 : 0;
      }
      return { replies: msgs ? msgs.length : 0, sent };
    })();
    // authenticated self-test (secret header already checked): wait and report delivery
    if (req.headers.get("X-Degen-Test") === "1") return Response.json(await work);
    ctx.waitUntil(work);
    return new Response("ok");
  },
};
