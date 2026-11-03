/* Degen Signals shared UI for the website (docs/index.html) and the Telegram mini app (docs/app/index.html).
   Everything is computed client-side from signals.json (+ archive/*.json). No trading: $ figures are a hypothetical
   fixed stake per signal, labelled as such. Not financial advice. */
(() => {
const CFG = window.DEGEN || {}, BASE = CFG.base || "./", SITE = !!CFG.site;
const tg = window.Telegram?.WebApp, inTg = !!(tg && tg.initData !== undefined && tg.platform && tg.platform !== "unknown");
const DATA = BASE + "signals.json", DS = "https://api.dexscreener.com", TP = {at: 100, frac: .5}, STAKE = 100, DAY = 86400, WAT = 3600;
let D = null, LIVE = {}, TRIED = {}, tab = "home", view = null, period = "today", hp = "all", seg = null, filt = "any", strat = "hold", evf = "all";
const $ = s => document.querySelector(s), esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = n => n == null || isNaN(n) ? "n/a" : Math.abs(n) >= 1e9 ? (n/1e9).toFixed(2)+"B" : Math.abs(n) >= 1e6 ? (n/1e6).toFixed(2)+"M" : Math.abs(n) >= 1e3 ? (n/1e3).toFixed(1)+"K" : (+n).toFixed(0);
const money = n => n ? "$" + fmt(n) : "n/a";
const usd = (n, sign = true) => n == null || isNaN(n) ? "n/a" : (sign ? (n > 0 ? "+" : n < 0 ? "−" : "") : (n < 0 ? "−" : "")) + "$" + Math.abs(n).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
const pct = x => x == null || isNaN(x) ? "n/a" : (x >= 0 ? "+" : "") + (+x).toFixed(1) + "%";
const xm = x => x == null || isNaN(x) || !isFinite(x) ? "n/a" : (x >= 100 ? x.toFixed(0) : x >= 10 ? x.toFixed(1) : x.toFixed(2)) + "x";
const cls = x => x == null ? "" : x >= 0 ? "pos" : "neg";
const price = p => p == null ? "n/a" : p >= 1 ? "$" + p.toFixed(4) : "$" + Number(p.toPrecision(4)).toFixed(Math.max(2, -Math.floor(Math.log10(p)) + 3));
const when = t => { const d = new Date((t + WAT) * 1000), m = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(" ")[d.getUTCMonth()];
  return `${String(d.getUTCDate()).padStart(2,"0")} ${m} ${String(d.getUTCHours()).padStart(2,"0")}:${String(d.getUTCMinutes()).padStart(2,"0")} WAT`; };
const ago = s => s < 60 ? "now" : s < 3600 ? Math.floor(s/60) + "m" : s < DAY ? Math.floor(s/3600) + "h " + Math.floor(s%3600/60) + "m" : Math.floor(s/DAY) + "d";
function bounds(now = Date.now()/1000){ const w = new Date((now+WAT)*1000); w.setUTCHours(0,0,0,0);
  const day = w.getTime()/1000 - WAT, dow = (w.getUTCDay()+6)%7, m = new Date(w); m.setUTCDate(1);
  return {today: day, week: day - dow*86400, month: m.getTime()/1000 - WAT, all: 0}; }
const PL = {today: "Today", week: "Week", month: "Month", all: "All"}, PLL = {today: "Today", week: "This week", month: "This month", all: "All-time"};
const hap = (k = "light") => { try { tg?.HapticFeedback?.impactOccurred(k); } catch(e){} };
const open = u => { hap(); if (inTg && /^https:\/\/t\.me\//.test(u)) tg.openTelegramLink(u); else if (inTg) tg.openLink(u); else window.open(u, "_blank", "noopener"); };
async function copy(t){ try { await navigator.clipboard.writeText(t); } catch(e){ const a = document.createElement("textarea"); a.value = t; document.body.appendChild(a); a.select(); document.execCommand("copy"); a.remove(); }
  try { tg?.HapticFeedback?.notificationOccurred("success"); } catch(e){} toast("CA copied"); }
function toast(m){ const d = document.createElement("div"); d.textContent = m;
  d.style.cssText = "position:fixed;left:50%;bottom:90px;transform:translateX(-50%);background:var(--blue);color:#fff;padding:8px 14px;border-radius:18px;z-index:99";
  document.body.appendChild(d); setTimeout(() => d.remove(), 1400); }
const I = { // inline icons
  home: '<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  sig: '<path d="M4 6h16M4 12h16M4 18h10"/>', bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0"/>',
  pnl: '<path d="M4 19h16M6 15l4-5 3 3 5-7"/>', more: '<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>', ref: '<path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5"/>'};
const svg = k => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${I[k]}</svg>`;

/* ---------- data ---------- */
async function live(mints){ const need = mints.filter(m => (!LIVE[m] || Date.now() - LIVE[m].t > 60000) && !(TRIED[m] > Date.now() - 60000));
  need.forEach(m => TRIED[m] = Date.now()); let got = false;
  for (let i = 0; i < need.length; i += 30) { try {
    const ps = await (await fetch(`${DS}/tokens/v1/solana/${need.slice(i, i+30).join(",")}`)).json();
    for (const p of ps) { const m = p.baseToken.address; if (!LIVE[m]?.p || Date.now() - LIVE[m].t > 60000 || (p.liquidity?.usd||0) > (LIVE[m].p.liquidity?.usd||0)) { LIVE[m] = {p, t: Date.now()}; got = true; } }
  } catch(e){} } return got; }
function needLive(mints){ live(mints).then(g => { if (g && !view) render(true); }); }
const mcOf = p => p ? (p.marketCap || p.fdv) : null;
function calc(e){ // hold / TP / max gain, same rules as the bot (journal.tp_ret)
  const p = LIVE[e.mint]?.p, p0 = e.price0, lv = p?.priceUsd ? +p.priceUsd : null;
  const lp = lv && p0 ? (lv/p0 - 1)*100 : null;
  let hold, basis; if (e.h24) [hold, basis] = [e.h24.pct, "24h result"]; else if (lp != null) [hold, basis] = [lp, "live"]; else [hold, basis] = [e.lastPct ?? e.h1?.pct ?? null, "last seen"];
  const mx = p0 ? Math.max(e.maxPrice||0, e.h24 ? 0 : (lv||0), p0) : null, mg = mx ? (mx/p0 - 1)*100 : null;
  const tp = hold == null ? null : mg >= TP.at ? TP.frac*TP.at + (1-TP.frac)*hold : hold;
  const ath = Math.max(e.athMc||0, mcOf(p)||0) || null;
  const cur = lv || e.last, curX = p0 && cur ? cur/p0 : e.lastPct != null ? 1 + e.lastPct/100 : null;
  const mcNow = mcOf(p) || (curX && e.mcap0 ? e.mcap0*curX : null);
  const rug = (curX != null && curX <= .1) || !!(e.lpEvents && (e.lpEvents.pulled || e.lpEvents.unlocked));
  return {p, lv, livePct: lp, hold, basis, maxGain: mg, peakX: mg == null ? null : 1 + mg/100, tp, ath, athX: ath && e.mcap0 ? ath/e.mcap0 : null, mcNow, curX, rug, closed: !!e.h24};
}
const topMs = e => { const k = Object.keys(e.milestones||{}).concat(e.hit2x?["2"]:[], e.hit5x?["5"]:[]); return k.length ? Math.max(...k.map(Number)) : null; };
const tokOf = m => D.tokens.find(t => t.mint === m), jrOf = m => D.journal.find(e => e.mint === m);
const inPeriod = p => { const b = bounds()[p]; return D.journal.filter(e => e.t0 >= b); };

// hypothetical portfolio: STAKE $ per signal; realized when the 24h result is in, unrealized while still tracking (live/last price)
function book(J, mode){
  const now = Date.now()/1000, R = J.map(e => { const c = calc(e), v = mode === "tp" ? c.tp : c.hold; return {e, c, v, closed: c.closed, tc: c.closed ? Math.min(e.t0 + DAY, now) : now}; }).filter(r => r.v != null);
  const cl = R.filter(r => r.closed).sort((a, b) => a.tc - b.tc), op = R.filter(r => !r.closed), $v = r => STAKE*r.v/100;
  const realized = cl.reduce((s, r) => s + $v(r), 0), unreal = op.reduce((s, r) => s + $v(r), 0);
  const t0 = R.length ? Math.min(...R.map(r => r.e.t0)) : now, pts = [[t0, 0]]; let cum = 0;
  for (const r of cl) { cum += $v(r); pts.push([r.tc, cum]); } pts.push([now, cum + unreal]);
  let peak = 0, dd = 0; for (const [, v] of pts) { peak = Math.max(peak, v); dd = Math.max(dd, peak - v); }
  const vs = R.map(r => r.v), wins = vs.filter(v => v > (window.SIGNAL_CONFIG?.winThresholdPct ?? 0)).length, gain = vs.filter(v => v > 0).reduce((a, b) => a + b, 0), loss = -vs.filter(v => v < 0).reduce((a, b) => a + b, 0);
  const avg = vs.length ? vs.reduce((a, b) => a + b, 0)/vs.length : null, srt = [...R].sort((a, b) => b.v - a.v);
  return {n: R.length, closed: cl.length, open: op.length, staked: STAKE*R.length, realized, unreal, pnl: realized + unreal, pts, dd, ddPct: R.length ? dd/(STAKE*R.length)*100 : null,
    wins, winRate: R.length ? wins/R.length*100 : null, pf: loss ? gain/loss : gain ? Infinity : null, avg, avgX: avg == null ? null : 1 + avg/100, exp$: avg == null ? null : STAKE*avg/100,
    best: srt[0], worst: srt[srt.length-1], since: R.length ? t0 : null};
}

/* ---------- small renderers ---------- */
let gid = 0;
function spark(pts, small){
  const W = 300, H = small ? 46 : 90; if (!pts || pts.length < 2) return `<svg class="spark${small?" sm":""}" viewBox="0 0 ${W} ${H}"></svg>`;
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]), x0 = Math.min(...xs), x1 = Math.max(...xs) || 1, lo = Math.min(0, ...ys), hi = Math.max(0, ...ys), sp = (hi - lo) || 1;
  const X = x => x1 === x0 ? W : (x - x0)/(x1 - x0)*W, Y = y => 4 + (hi - y)/sp*(H - 8), last = ys[ys.length-1], col = last >= 0 ? "var(--grn)" : "var(--red)", id = "g" + (++gid);
  const d = pts.map((p, i) => (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1)).join(" ");
  return `<svg class="spark${small?" sm":""}" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><defs><linearGradient id="${id}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${col}" stop-opacity=".35"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
    <line x1="0" x2="${W}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--hint)" stroke-opacity=".5" stroke-dasharray="4 4" vector-effect="non-scaling-stroke"/>
    <path d="${d} L${W} ${Y(0)} L0 ${Y(0)} Z" fill="url(#${id})"/><path d="${d}" fill="none" stroke="${col}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
}
// entry MC -> current MC on a log scale from 0.1x (rug) to >=10x, with peak-since-alert, chart ATH and 2x/5x/10x milestone ticks
function bar(c){
  if (c.curX == null) return "";
  const top = Math.max(10, (c.peakX||1)*1.25, (c.athX||1)*1.1, c.curX*1.25), L = Math.log(.1), S = Math.log(top) - L, P = x => Math.max(0, Math.min(100, (Math.log(Math.max(x, .1)) - L)/S*100));
  const e = P(1), cu = P(c.curX), up = c.curX >= 1, ticks = [2, 5, 10, 20, 50, 100, 500, 1000].filter(t => t < top*.97 && (t <= 10 || t >= top/8));
  return `<div class="bar" title="Entry MC → now (log scale). Dotted = peak since alert, 🏔 = chart ATH">
    <div class="f ${up?"up":"dn"}" style="left:${Math.min(e,cu)}%;width:${Math.abs(cu-e)}%"></div>
    ${c.peakX > 1.05 ? `<div class="pk" style="left:${P(c.peakX)}%"></div>` : ""}
    <div class="tk e" style="left:${e}%"></div><div class="tl" style="left:${e}%">entry</div><div class="tl" style="left:3%">−90%</div>
    ${ticks.map(t => `<div class="tk" style="left:${P(t)}%"></div><div class="tl" style="left:${P(t)}%">${t}x</div>`).join("")}
    ${c.athX && c.athX > 1.05 ? `<div class="ath" style="left:${P(c.athX)}%">🏔</div>` : ""}
    <div class="cur ${up?"":"dn"}" style="left:${cu}%"></div></div>`;
}
function lpChip(e, t){ const lp = e.lp || t?.lp || {}, ev = e.lpEvents && Object.keys(e.lpEvents).length;
  if (ev) return `<span class="pill r">⚠️ LP ${esc(Object.keys(e.lpEvents)[0])}</span>`;
  const s = lp.status, ok = /burn|lock/.test(s||"") && !/unlock/.test(s||""); return s ? `<span class="pill ${ok?"g":s==="unlocked"||s==="pulled"?"r":"a"}">${/burn/.test(s)?"🔥":ok?"🔒":"🔓"} LP ${esc(s)}${lp.pct!=null&&!/burn/.test(s)?" "+Math.round(lp.pct)+"%":""}</span>` : ""; }
function safeChip(e, t){ const s = e.safety?.status || t?.safety?.status; return s ? `<span class="pill ${s==="PASS"?"g":s==="FAIL"?"r":"a"}">🎯 ${esc(s)}</span>` : ""; }
function card(e){
  const t = tokOf(e.mint) || {}, c = calc(e), f = t.findings || [], nr = f.filter(x => x[0]==="red").length, na = f.length - nr, ms = topMs(e);
  return `<div class="card" data-m="${esc(e.mint)}"><div class="row"><span class="sym">$${esc(e.symbol)} <small>${esc(t.name||"")}</small></span><b class="${cls(c.hold)}" style="font-size:16px">${pct(c.hold)}</b></div>
   <div class="row" style="margin-top:6px"><span style="display:flex;gap:4px;flex-wrap:wrap">${c.closed?'<span class="pill">closed 24h</span>':'<span class="pill b">tracking</span>'}${lpChip(e,t)}${safeChip(e,t)}${ms?`<span class="pill g">🚀 ${ms}x</span>`:""}${c.rug?'<span class="pill r">☠️ rugged</span>':""}${e.trend==="up"?'<span class="pill g">📈 up</span>':e.trend==="fading"?'<span class="pill a">fading</span>':""}</span>
   <small style="white-space:nowrap">${esc(c.basis)}</small></div>
   <div class="stats3"><span><small>Entry MC</small><b>${money(e.mcap0)}</b></span><span><small>Now</small><b class="${c.curX>=1?"pos":"neg"}">${money(c.mcNow)} · ${xm(c.curX)}</b></span><span><small>Peak / ATH</small><b>${xm(c.peakX)} / ${xm(c.athX)}</b></span></div>
   ${bar(c)}
   <div class="row"><small>${when(e.t0)} · ⭐ ${t.score ?? e.score ?? "n/a"}${nr?` · <span class="neg">${nr} red</span>`:""}${na?` · <span class="amb">${na} amber</span>`:""}</small><button class="btn ghost" data-copy="${esc(e.mint)}">Copy CA</button></div></div>`;
}
const tile = (l, v, c = "") => `<div class="tile"><small>${l}</small><b class="${c}">${v}</b></div>`;
const chips = (items, cur, attr) => `<div class="chips">${items.map(([k, l, n]) => `<button class="chip ${k===cur?"on":""}" data-${attr}="${k}">${l}${n!=null?`<span class="n">${n}</span>`:""}</button>`).join("")}</div>`;
const periodChips = (cur, attr) => chips(Object.keys(PL).map(k => [k, PL[k]]), cur, attr);
const pfTxt = v => v == null ? "n/a" : v === Infinity ? "∞" : v.toFixed(2);
const STRAT = {hold: {n: "Hold", s: "Hold", d: "Hold every signal: 24h result, live price until then", col: "var(--blue)"}, tp: {n: "TP 50% @ 2x", s: "TP ½ @2x", d: "Sell half at +100% if the peak reached 2x, hold the rest", col: "#a78bfa"}};

/* ---------- views ---------- */
function home(){
  const J = inPeriod(hp), B = {hold: book(J, "hold"), tp: book(J, "tp")}, b = B[strat];
  needLive(J.filter(e => !e.h24).map(e => e.mint));
  const ret = b.staked ? b.pnl/b.staked*100 : null;
  let h = `<div class="hero"><div class="row"><span class="lbl">Hypothetical equity · $${STAKE}/signal · ${esc(STRAT[strat].n)}</span></div>
   <div class="big">${b.n ? usd(b.staked + b.pnl, false) : "$0.00"}</div>
   <div class="meta"><span class="pill ${ret>=0?"g":"r"}">${usd(b.pnl)} · ${pct(ret)}</span><span class="pill">${b.open} tracking</span><span class="pill">win ${b.winRate==null?"n/a":b.winRate.toFixed(0)+"%"}</span><span class="pill b">free signals</span><span class="pill">no trading</span></div>
   ${spark(b.pts)}
   <div class="tiles">${tile("Realized", usd(b.realized), cls(b.realized))}${tile("Unrealized", usd(b.unreal), cls(b.unreal))}${tile("Staked", usd(b.staked, false))}</div>
   <div class="row" style="margin-top:10px;gap:8px;flex-wrap:wrap">${periodChips(hp, "hp")}<div class="seg" style="min-width:190px">${Object.keys(STRAT).map(k => `<button class="${k===strat?"on":""}" data-st="${k}">${STRAT[k].s}</button>`).join("")}</div></div>
   <small style="display:block;margin-top:8px">${PLL[hp]} · ${b.n} signals. Paper maths only: a fixed $${STAKE} per alert, realized at the 24h result, unrealized while still tracking. Not a real portfolio, not financial advice.</small></div>`;
  h += `<div class="sec">Strategies <a href="#" data-tab="pnl">Details ›</a></div><div class="cols c2">${Object.keys(STRAT).map(k => stratCard(k, B[k])).join("")}</div>`;
  const top = [...J].map(e => [e, calc(e).hold]).filter(x => x[1] != null).sort((a, c) => c[1] - a[1]).slice(0, 4).map(x => x[0]);
  h += `<div class="sec">Top signals · ${PLL[hp]} <a href="#" data-tab="signals">All ${J.length} ›</a></div>${top.length ? `<div class="cols c2">${top.map(card).join("")}</div>` : '<div class="card empty">No signals in this period yet.</div>'}`;
  const ev = events().slice(0, 5);
  h += `<div class="sec">Latest alerts <a href="#" data-tab="alerts">All ›</a></div><div class="card">${ev.length ? ev.map(evHtml).join('<div style="height:10px"></div>') : '<div class="empty">No alerts yet.</div>'}</div>`;
  $("#main").innerHTML = disc() + h;
}
function stratCard(k, b){ const S = STRAT[k], ret = b.staked ? b.pnl/b.staked*100 : null;
  return `<div class="card strat"><div class="row"><span><span class="dot" style="background:${S.col}"></span><b>${S.n}</b></span><span class="pill ${ret>=0?"g":"r"}">${pct(ret)}</span></div><small>${S.d}</small>
   <div class="row" style="margin-top:8px;align-items:flex-end"><span><small style="font-size:10.5px;letter-spacing:.06em">EQUITY</small><br><b style="font-size:20px">${usd(b.staked + b.pnl, false)}</b></span><small style="text-align:right">realized <b class="${cls(b.realized)}">${usd(b.realized)}</b><br>open <b class="${cls(b.unreal)}">${usd(b.unreal)}</b></small></div>
   ${spark(b.pts, true)}
   <div class="tiles">${tile("Win rate", b.winRate==null?"n/a":b.winRate.toFixed(0)+"%")}${tile("Avg multiple", xm(b.avgX), cls(b.avg))}${tile("Max DD", b.dd ? "−$"+b.dd.toFixed(0) : "$0", b.dd?"neg":"")}
   ${tile("Open", b.open)}${tile("Closed", b.closed)}${tile("Profit factor", pfTxt(b.pf), b.pf>=1?"pos":b.pf!=null?"neg":"")}</div></div>`; }
function disc(){ return `<div class="disc">⚠️ <b>Not financial advice.</b> Automated heuristics on extremely risky memecoins. Most go to zero. DYOR.</div>`; }

function signals(){
  const J0 = inPeriod(period).sort((a, c) => c.t0 - a.t0), C = new Map(J0.map(e => [e, calc(e)]));
  const act = J0.filter(e => !C.get(e).closed), clo = J0.filter(e => C.get(e).closed);
  if (!seg) seg = act.length ? "active" : "all";
  const base = seg === "active" ? act : seg === "closed" ? clo : J0;
  const F = {any: () => true, running: e => C.get(e).curX > 1, x2: e => (C.get(e).peakX||0) >= 2 || topMs(e) >= 2, rug: e => C.get(e).rug};
  const J = base.filter(F[filt]), sumOpen = act.reduce((s, e) => s + (C.get(e).hold != null ? STAKE*C.get(e).hold/100 : 0), 0);
  let h = `<div class="seg" style="margin-bottom:10px"><button class="${seg==="active"?"on":""}" data-seg="active">Active · ${act.length}</button><button class="${seg==="closed"?"on":""}" data-seg="closed">Closed · ${clo.length}</button><button class="${seg==="all"?"on":""}" data-seg="all">All · ${J0.length}</button></div>
   ${periodChips(period, "p")}<div class="row" style="margin:8px 0 12px">${chips([["any","All"],["running","Running", base.filter(F.running).length],["x2","2x+", base.filter(F.x2).length],["rug","Rugged", base.filter(F.rug).length]], filt, "f")}
   <small style="white-space:nowrap" title="Hypothetical $${STAKE} per still-tracking signal">${act.length ? `<b class="${cls(sumOpen)}">${usd(sumOpen)}</b> open` : ""}</small></div>`;
  h += J.length ? `<div class="cols c2">${J.map(card).join("")}</div>` : `<div class="card empty">No ${seg === "all" ? "" : seg + " "}signals match this filter.</div>`;
  $("#main").innerHTML = h;
  needLive(J.slice(0, 60).map(e => e.mint));
}
function events(){ const E = [];
  for (const e of D.journal) { E.push({t: e.t0, k: "sig", e});
    for (const [m, ts] of Object.entries(e.milestones || {})) if (ts) E.push({t: ts, k: "ms", e, m});
    if (e.h1) E.push({t: e.t0 + 3600, k: "res", e, w: "1h", v: e.h1.pct}); if (e.h24) E.push({t: e.t0 + DAY, k: "res", e, w: "24h", v: e.h24.pct});
    for (const [k, ts] of Object.entries(e.lpEvents || {})) if (ts) E.push({t: ts, k: "lp", e, w: k}); }
  const now = Date.now()/1000; return E.filter(x => x.t <= now + 60).sort((a, b) => b.t - a.t); }
function evHtml(x){ const e = x.e, S = `<b>$${esc(e.symbol)}</b>`;
  const [ic, txt] = x.k === "sig" ? ["🎯", `${S} new signal at ${money(e.mcap0)} MC`] : x.k === "ms" ? ["🚀", `${S} hit <b class="pos">${esc(x.m)}x</b> from alert (${money(e.mcap0*x.m)} MC)`]
    : x.k === "res" ? [x.v >= 0 ? "✅" : "🔻", `${S} ${x.w} result <b class="${cls(x.v)}">${pct(x.v)}</b>`] : ["⚠️", `${S} <span class="neg">${{unlocked:"liquidity unlocked",pulled:"liquidity pulled",unlockPassed:"LP unlock date passed"}[x.w]||esc(x.w)}</span>`];
  return `<div class="ev card" data-m="${esc(e.mint)}" style="margin:0;border:0;padding:0;background:none;box-shadow:none"><div class="ic">${ic}</div><div class="bd">${txt}<br><small>${when(x.t)} · ${ago(Date.now()/1000 - x.t)} ago</small></div></div>`; }
function alerts(){ const E = events(), n = k => E.filter(x => x.k === k).length, L = E.filter(x => evf === "all" || x.k === evf).slice(0, 150);
  $("#main").innerHTML = `<div style="margin-bottom:12px">${chips([["all","All"],["ms","Milestones",n("ms")],["sig","Signals",n("sig")],["res","Results",n("res")],["lp","LP warnings",n("lp")]], evf, "ev")}</div>
   <div class="card">${L.length ? L.map(evHtml).join('<div style="height:12px"></div>') : '<div class="empty">Nothing here yet.</div>'}</div>
   <small>Milestones are measured from the alert price (2x, 3x, 5x, 10x…), using chart highs where available. Times in WAT.</small>`; }

function msCounts(p){ const ms = p.milestones || {"2": p.hit2x, "5": p.hit5x};
  return Object.entries(ms).sort((a,b) => a[0]-b[0]).filter(([k,v]) => k==="2"||k==="5"||v).map(([k,v]) => `<span class="pill">${k}x ${v}</span>`).join(" "); }
function pnl(){
  const J = inPeriod(hp), B = {hold: book(J, "hold"), tp: book(J, "tp")};
  needLive(J.filter(e => !e.h24).map(e => e.mint));
  const kv = (k, v, c = "") => `<div class="kv"><span class="h">${k}</span><b class="${c}">${v}</b></div>`;
  let h = `<div style="margin-bottom:12px">${periodChips(hp, "hp")}</div><div class="cols c2">` + Object.keys(STRAT).map(k => { const b = B[k], S = STRAT[k], ret = b.staked ? b.pnl/b.staked*100 : null;
    return `<div class="card strat"><div class="row"><span><span class="dot" style="background:${S.col}"></span><b>${S.n}</b></span><span class="pill ${ret>=0?"g":"r"}">${pct(ret)}</span></div><small>${S.d}</small>${spark(b.pts, true)}
     ${kv("Signals", `${b.n} <small>(${b.closed} closed · ${b.open} open)</small>`)}${kv("Since", b.since ? when(b.since) : "n/a")}
     ${kv("Hypothetical equity", usd(b.staked + b.pnl, false))}${kv("Realized", usd(b.realized), cls(b.realized))}${kv("Unrealized", usd(b.unreal), cls(b.unreal))}
     ${kv("Win rate", b.winRate == null ? "n/a" : `${b.winRate.toFixed(1)}% <small>(${b.wins}/${b.n})</small>`)}${kv("Expectancy", b.avg == null ? "n/a" : `${pct(b.avg)} · ${usd(b.exp$)}/signal`, cls(b.avg))}
     ${kv("Avg multiple", xm(b.avgX))}${kv("Profit factor", pfTxt(b.pf), b.pf>=1?"pos":b.pf!=null?"neg":"")}${kv("Max drawdown", b.dd ? `−$${b.dd.toFixed(0)} <small>(${b.ddPct.toFixed(1)}% of staked)</small>` : "$0", b.dd?"neg":"")}
     ${kv("Best", b.best ? `$${esc(b.best.e.symbol)} ${pct(b.best.v)}` : "n/a", "pos")}${kv("Worst", b.worst ? `$${esc(b.worst.e.symbol)} ${pct(b.worst.v)}` : "n/a", "neg")}</div>`; }).join("") + `</div>`;
  const P = D.periodStats || {};
  h += `<div class="sec">Bot report figures (server)</div><div class="cols c2 wide">` + Object.keys(PLL).map(k => { const p = P[k]; if (!p) return "";
    return `<div class="card"><div class="row"><b>${PLL[k]}</b><small>${p.signals} signals</small></div>
    <table><tr><th></th><th>Win rate</th><th>Total</th><th>Avg</th></tr>
    <tr><td>Hold</td><td>${p.winRate==null?"n/a":p.winRate+"%"} <small>(${p.wins}/${p.n})</small></td><td class="${cls(p.totalPnl)}"><b>${pct(p.totalPnl)}</b></td><td class="${cls(p.avgPnl)}">${pct(p.avgPnl)}</td></tr>
    <tr><td>TP 50% @2x</td><td>${p.tpWinRate==null?"n/a":p.tpWinRate+"%"} <small>(${p.tpWins??0}/${p.n})</small></td><td class="${cls(p.tpTotalPnl)}"><b>${pct(p.tpTotalPnl)}</b></td><td class="${cls(p.tpAvgPnl)}">${pct(p.tpAvgPnl)}</td></tr></table>
    <div style="margin-top:6px">${msCounts(p)}</div><small>Best ${esc(p.best||"–")} · Worst ${esc(p.worst||"–")}</small></div>`; }).join("") + `</div>
    <small>Total = sum of % per signal since alert. ${esc(D.statsBasis||"")}. TP sim = sell 50% at +100% if max gain reached 2x, the rest at the hold basis. Max gain uses the chart high where available. Strategy cards above are a hypothetical $${STAKE} per signal, computed in your browser with live prices for signals still tracking, so they can differ slightly from the bot's report. WAT periods. Not financial advice.</small>`;
  $("#main").innerHTML = h;
}

function more(q0){
  const s = D.stats || {}, A = D.archive || {}, f = a => a && a.n ? `${a.n} closed · win ${a.winRate}% · avg ${pct(a.avg)} · best ${pct(a.best)} · worst ${pct(a.worst)}` : "no results yet";
  const fr = fresh(), kv = (k, v) => `<div class="kv"><span class="h">${k}</span><span>${v}</span></div>`;
  $("#main").innerHTML = `<div class="sec" style="margin-top:0">Token PnL lookup</div><div class="card"><input id="q" placeholder="Contract address or $SYMBOL" autocomplete="off" autocapitalize="off" value="${esc(q0||"")}">
    ${inTg ? "" : '<button class="btn" id="go" style="margin-top:8px;width:100%;padding:10px">Look up</button>'}</div><div id="res"></div>
   <div class="cols c2"><div class="card"><b>📡 Feed & scanner</b>${kv("Feed saved", fr ? `${when(fr)} (${ago(Date.now()/1000 - fr)} ago)` : "n/a")}${kv("Scan interval", "every 15 min")}${kv("Volume window", esc(D.window||"n/a"))}
     ${kv("Last run", `${D.candidates ?? "n/a"} scanned · ${D.cheapPass ?? "n/a"} near-pass${D.lastRunErrors?.length?` · <span class="amb">⚠ ${D.lastRunErrors.length} lookup errors</span>`:""}`)}<small>The feed is saved on new signals/results, else about every 2h, so “feed saved” can lag the last scan.</small></div>
    <div class="card"><b>📒 Journal summary</b>${kv("Signals (all-time)", `${s.signals||0}${A.journal?` <small>(incl. ${A.journal} archived)</small>`:""}`)}${kv("Hit 2x / 5x", `${s.hit2x||0} / ${s.hit5x||0}`)}
     <div class="kv" style="display:block"><span class="h">1h:</span> <small>${f(s.h1)}</small></div><div class="kv" style="display:block"><span class="h">24h:</span> <small>${f(s.h24)}</small></div>
     ${(A.files||[]).length ? kv("Archive", A.files.map(x => `<a href="${BASE}archive/${esc(x)}" target=_blank>${esc(x.replace(".json",""))}</a>`).join(" · ")) : kv("Archive", `<small>none yet (signals older than ${A.days||30} days move here)</small>`)}</div></div>
   <details class="card"><summary><b>🗂 Full signal journal</b> <small>(${D.journal.length} signals)</small></summary><div class="tw" style="margin-top:8px">${journalTable()}</div></details>
   <div class="card"><b>🔗 Links</b><div class="links"><button class="btn" data-open="https://t.me/DegenGainsBot">Telegram bot</button>${SITE?`<button class="btn ghost" data-open="https://t.me/DegenGainsBot/app">Mini app</button>`:`<button class="btn ghost" data-open="https://degen-signals.pages.dev/">Website</button>`}
     <button class="btn ghost" data-open="${BASE}signals.json">signals.json</button>${SITE?'<button class="btn ghost" id="inst" hidden>Install app</button>':""}</div>
     <small style="display:block;margin-top:8px">Free signals. The bot never trades, holds keys or signs transactions. Hold/TP figures are simulations from public price data. Not financial advice, DYOR.</small></div>`;
  bind($("#main")); if (SITE && INST) { const b = $("#inst"); b.hidden = false; b.onclick = () => INST.prompt(); }
  const q = $("#q"), go = () => { const v = q.value.trim(); if (v) { hap("medium"); doLookup(v); } };
  q.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
  if (inTg) { const upd = () => q.value.trim() ? tg.MainButton.setText("Look up").show() : tg.MainButton.hide(); q.addEventListener("input", upd); upd(); tg.MainButton.offClick(window._mb||(()=>{})); window._mb = go; tg.MainButton.onClick(go); }
  else $("#go").onclick = go;
  if (q0) doLookup(q0);
}
function journalTable(){ const pc = x => x == null ? "–" : `<span class="${cls(x)}">${pct(x)}</span>`;
  return `<table><tr><th>Token</th><th>Alert</th><th>Entry MC</th><th>Dev</th><th>Now</th><th>1h</th><th>24h</th><th>Max</th><th>ATH MC</th><th>LP</th><th>Trend</th><th></th></tr>` +
   D.journal.map(e => `<tr><td><a href="#" data-view="${esc(e.mint)}">$${esc(e.symbol)}</a></td><td>${when(e.t0)}</td><td>${money(e.mcap0)}</td><td>${e.devScore??"–"}</td><td>${pc(e.lastPct)}</td><td>${pc(e.h1?.pct)}</td><td>${pc(e.h24?.pct)}</td>
    <td>${e.price0&&e.maxPrice?(e.maxPrice/e.price0).toFixed(2)+"x":"–"}${topMs(e)>=2?` 🚀${topMs(e)}x`:""}${e.maxSrc==="chart"?"":"<small>*</small>"}</td><td>${e.athMc?money(e.athMc):"–"}</td>
    <td><small>${esc(e.lp?.label||"–")}${e.lpEvents&&Object.keys(e.lpEvents).length?' <span class="neg">⚠️ '+esc(Object.keys(e.lpEvents).join(", "))+'</span>':""}</small></td><td>${e.trend==="up"?"📈 up":e.trend==="fading"?"⚠️ fading":"–"}</td>
    <td><a href="#" data-open="https://fomo.family/tokens/solana/${esc(e.mint)}">Fomo</a></td></tr>`).join("") +
   `</table><small>Max = chart high since alert (GeckoTerminal candles); * = bot-sampled only. ATH MC = all-time chart high × supply. LP from rugcheck, re-checked for 7 days.</small>`; }
const isCA = s => /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(s);
async function doLookup(q){
  const r = $("#res"); r.innerHTML = `<div class="empty">Looking up…</div>`;
  const hits = isCA(q) ? D.journal.filter(e => e.mint === q) : D.journal.filter(e => e.symbol.toLowerCase() === q.replace(/^\$/,"").toLowerCase()).sort((a,c) => c.t0 - a.t0);
  if (hits.length) { await live([hits[0].mint]); r.innerHTML = tokenHtml(hits[0], hits.length > 1 ? `${hits.length} signals share this symbol; showing the latest.` : ""); bind(r); return; }
  let ps = [];
  try { if (isCA(q)) ps = await (await fetch(`${DS}/tokens/v1/solana/${q}`)).json();
    else { const s = q.replace(/^\$/,"").toLowerCase(); ps = ((await (await fetch(`${DS}/latest/dex/search?q=${encodeURIComponent(s)}`)).json()).pairs||[]).filter(p => p.chainId==="solana" && p.baseToken.symbol.toLowerCase()===s); } } catch(e){}
  if (!ps.length) { r.innerHTML = `<div class="card">❔ ${esc(q)} is not a Degen signal, and no live Solana pair was found on DexScreener.</div>`; return; }
  const p = ps.reduce((a, c) => (c.liquidity?.usd||0) > (a.liquidity?.usd||0) ? c : a), m = p.baseToken.address;
  r.innerHTML = `<div class="card"><div class="row"><span class="sym">$${esc(p.baseToken.symbol)}</span><span class="pill">not a Degen signal</span></div>
   <div class="row"><span class="ca">${esc(m)}</span><button class="btn ghost" data-copy="${esc(m)}">Copy</button></div>
   <div class="grid"><span>💲 ${price(+p.priceUsd)}</span><span>🧢 MC ${money(mcOf(p))}</span><span>💧 Liq ${money(p.liquidity?.usd)}</span><span>24h ${pct(p.priceChange?.h24)}</span></div>
   ${linkRow({dexscreener: p.url, gmgn: `https://gmgn.ai/sol/token/${m}`, bubblemaps: `https://v2.bubblemaps.io/map?address=${m}&chain=solana`, fomo: `https://fomo.family/tokens/solana/${m}`, axiom: `https://axiom.trade/t/${m}?chain=sol`, bullx: `https://neo.bullx.io/terminal?chainId=1399811149&address=${m}`, pumpfun: `https://pump.fun/coin/${m}`})}</div>`;
  bind(r);
}
function linkRow(L){ const n = {dexscreener:"DexScreener", gmgn:"GMGN", bubblemaps:"Bubblemaps", insightx:"InsightX", fomo:"Fomo", axiom:"Axiom", bullx:"BullX", shuriken:"Shuriken bot", x_search:"X search", tiktok:"TikTok", pumpfun:"pump.fun"};
  return `<div class="links">${Object.keys(n).filter(k => L[k]).map(k => `<button class="btn ${k==="fomo"?"":"ghost"}" data-open="${esc(L[k])}">${n[k]}</button>`).join("")}</div>`; }
function tokenHtml(e, note = ""){
  const t = tokOf(e.mint) || {}, c = calc(e), H = t.holders || {}, B = t.behaviour || {}, d = t.dev || {}, G = t.gmgn || {}, f = t.findings || [], X = t.extras || {};
  const S0 = t.safety || {}, S = e.safety || (S0.status ? {status: S0.status, reasons: [...(S0.fails||[]), ...(S0.warns||[]), ...(S0.oks||[])], pct: S0.pct, sources: S0.sources} : {});
  const TL = t.links || {}, L = {...TL, dexscreener: TL.dexscreener || e.link, gmgn: G.link || TL.gmgn || `https://gmgn.ai/sol/token/${e.mint}`, insightx: TL.insightx || null,
    fomo: TL.fomo || `https://fomo.family/tokens/solana/${e.mint}`, axiom: TL.axiom || `https://axiom.trade/t/${e.mint}?chain=sol`,
    bullx: TL.bullx || `https://neo.bullx.io/terminal?chainId=1399811149&address=${e.mint}`, shuriken: TL.shuriken || "https://t.me/shuriken_trade_bot", bubblemaps: TL.bubblemaps || `https://v2.bubblemaps.io/map?address=${e.mint}&chain=solana`,
    x_search: TL.x_search || `https://x.com/search?q=%24${encodeURIComponent(e.symbol)}&f=live`, pumpfun: TL.pumpfun || `https://pump.fun/coin/${e.mint}`};
  const ms = Object.entries(e.milestones||{}).sort((a,b) => a[0]-b[0]), ev = Object.entries(e.lpEvents||{}), lpn = e.lp || t.lp || {};
  const pc = v => v == null ? "n/a" : v + "%";
  return `<div class="card"><div class="row"><span class="sym">$${esc(e.symbol)} <small>${esc(t.name||"")}</small></span><b class="${cls(c.hold)}" style="font-size:18px">${pct(c.hold)}</b></div>
  <div class="row" style="margin:6px 0"><span class="ca">${esc(e.mint)}</span><button class="btn" data-copy="${esc(e.mint)}">Copy CA</button></div>
  <div style="display:flex;gap:4px;flex-wrap:wrap">${c.closed?'<span class="pill">closed 24h</span>':'<span class="pill b">tracking</span>'}${lpChip(e,t)}${safeChip(e,t)}${topMs(e)?`<span class="pill g">🚀 ${topMs(e)}x</span>`:""}${c.rug?'<span class="pill r">☠️ rugged</span>':""}</div>
  <small>Alert ${when(e.t0)}${note?" · "+esc(note):""}</small>
  <div class="stats3"><span><small>Entry MC</small><b>${money(e.mcap0)}</b></span><span><small>Now</small><b class="${c.curX>=1?"pos":"neg"}">${money(c.mcNow)} · ${xm(c.curX)}</b></span><span><small>Peak / ATH</small><b>${xm(c.peakX)} / ${xm(c.athX)}</b></span></div>${bar(c)}
  <div class="sec">Performance</div><div class="grid">
   <span>💲 ${price(e.price0)} ⇨ ${price(c.lv ?? e.last)}</span><span>🧢 ${money(e.mcap0)} ⇨ ${money(c.mcNow)}</span>
   <span>Live vs alert <b class="${cls(c.livePct)}">${pct(c.livePct)}</b></span><span>Max <b>${pct(c.maxGain)}</b> <small>(${e.maxSrc==="chart"?"chart":"sampled"})</small></span>
   <span>1h ${e.h1?pct(e.h1.pct):"pending"}</span><span>24h ${e.h24?pct(e.h24.pct):"pending"}</span>
   <span>Hold <b class="${cls(c.hold)}">${pct(c.hold)}</b> <small>${c.basis}</small></span><span>TP 50%@2x <b class="${cls(c.tp)}">${pct(c.tp)}</b></span>
   <span>🏔 ATH MC <b>${money(c.ath)}</b></span><span><small>${e.athT?"chart ATH "+when(e.athT):e.athMc?"chart ATH":"sampled"}</small></span>
   <span>$${STAKE} hold → <b class="${cls(c.hold)}">${c.hold==null?"n/a":usd(STAKE*(1+c.hold/100), false)}</b></span><span>$${STAKE} TP → <b class="${cls(c.tp)}">${c.tp==null?"n/a":usd(STAKE*(1+c.tp/100), false)}</b> <small>hypothetical</small></span></div>
  <div class="sec">Milestones</div>${ms.length ? ms.map(([k,ts]) => `<span class="pill g">${k}x${ts?" · "+when(ts):""}</span>`).join(" ") : '<small>none yet</small>'}
  <div class="sec">Liquidity</div><div>${esc(lpn.label||"🔐 n/a")}${lpn.t?` <small>(checked ${when(lpn.t)})</small>`:""}</div>
   ${ev.length ? ev.map(([k,ts]) => `<div class="neg">⚠️ ${{unlocked:"LIQUIDITY UNLOCKED",pulled:"LIQUIDITY PULLED",unlockPassed:"UNLOCK DATE PASSED"}[k]||esc(k)} · ${when(ts)}</div>`).join("") : '<small>No unlock/pull events</small>'}
   <div class="grid"><span>💧 Liq ${money(c.p?.liquidity?.usd ?? t.liq)}</span><span>Liq/MC ${t.liqPctMc ?? "n/a"}%</span></div>
  ${t.mcap ? `<div class="sec">Signal snapshot</div><div class="grid">
   <span>Vol ${esc(t.window||"")} ${money(t.vol)}</span><span>${t.buys??"?"}B / ${t.sells??"?"}S</span>
   <span class="${cls(t.ch5m)}">5m ${pct(t.ch5m)}</span><span class="${cls(t.ch1h)}">1h ${pct(t.ch1h)}</span>
   <span>Age ${t.ageH ?? "n/a"}h</span><span>Vol24h/Liq ${t.volLiq ?? "n/a"}x</span>
   ${t.firstScan?`<span>First scan MC ${money(t.firstScan.mc)}</span>`:""}${X.estFeesSol!=null?`<span>Fees ≈ ${X.estFeesSol} SOL</span>`:""}
   ${X.maxSingleHolderPct!=null?`<span>Max holder ${X.maxSingleHolderPct}%</span>`:""}${X.freshWallets!=null?`<span>Fresh ${X.freshWallets}/10</span>`:""}
   ${t.odds?.n?`<span>Our history: 2x ~${t.odds.x2}% / rug ~${t.odds.rug}% <small>(n=${t.odds.n})</small></span>`:""}${t.narratives?.length?`<span>🏷 ${esc(t.narratives.join(", "))}</span>`:""}</div>` : ""}
  <div class="sec">Score & findings</div><div>⭐ <b>${t.score ?? e.score ?? "n/a"}/100</b>${t.scoreCapped?` <small>(capped, would be ${t.scoreUncapped})</small>`:""}</div>
   ${f.length ? f.map(x => `<div class="${x[0]==="red"?"neg":"amb"}">${x[0]==="red"?"🔴":"🟠"} ${esc(x[1])}</div>`).join("") : '<small>No red/amber findings</small>'}
  <div class="sec">Holders</div><div class="grid">
   <span>🔝 Top5 ${H.top5Pct ?? "n/a"}%</span><span>👥 ${H.count?.toLocaleString() ?? "n/a"} holders</span>
   <span>🤖 Bots ${pc(B.botPct)}</span><span>🔁 Flippers ${pc(B.flipperPct)}</span><span>🌱 Fresh ${pc(B.freshPct)}</span><span>🐋 Whales ${pc(H.whalePct)}</span>
   <span>🔗 Cluster ${pc(H.clusterPct ?? t.clusterPct)}</span><span>🕵️ Insiders ${pc(H.insiderPct)}</span></div>
   ${H.top5?.length?`<small>Top5: ${esc(H.top5.join(" · "))}</small>`:""}${B.sampled?`<small> · behaviour from ${esc(B.source)}, top ${B.sampled}</small>`:""}
  <div class="sec">🎯 Safety check</div><div><b class="${S.status==="FAIL"?"neg":S.status==="WARN"?"amb":"pos"}">${esc(S.status||"n/a")}</b> <small>${esc((S.reasons||[]).join("; "))}${S.sources?.length?" ["+esc(S.sources.join(" · "))+"]":""}</small></div>
   ${S.pct && Object.keys(S.pct).length ? `<div class="grid">${Object.entries(S.pct).map(([k,v]) => `<span>${esc(k)} ${v}%</span>`).join("")}</div>` : ""}
   ${["PASS","FAIL"].includes(G.status) ? `<div><small>GMGN: ${esc(G.status)} ${esc((G.reasons||[]).join("; "))}</small></div>` : ""}
  <div class="sec">Dev</div><div>${d.wallet ? `<a href="#" data-open="${esc(d.links?.solscan||"https://solscan.io/account/"+d.wallet)}">${esc(d.wallet.slice(0,4))}…${esc(d.wallet.slice(-4))}</a> · ${d.sold?"sold":"holds "+d.holdPct+"%"} · ${d.priorTokens??"n/a"} prior (${d.priorMigrated??0} migrated, ${d.priorDead??0} dead)${d.rugHistory?' · <span class="neg">🚩 rug history</span>':""}${t.devScore!=null?` · dev score <b class="${cls(t.devScore)}">${t.devScore}</b>`:""}` : "n/a"}</div>
   <div class="grid"><span>Dex Paid ${t.orders?.dexPaid===true?"✅":t.orders?.dexPaid===false?"❌":"n/a"}</span><span>CTO ${t.cto===true?"✅":t.cto===false?"❌":"n/a"}</span></div>
  ${linkRow(L)}${(t.socials||[]).length?`<div class="links">${t.socials.map(u => `<button class="btn ghost" data-open="${esc(u)}">social</button>`).join("")}</div>`:""}${t.description?`<div class="desc">${esc(t.description)}</div>`:""}
  <p><small>Not financial advice. DYOR.</small></p></div>`;
}
function detail(m){
  const e = jrOf(m); if (!e) { view = null; return render(); }
  if (inTg) { tg.BackButton.show(); tg.MainButton.hide(); }
  $("#main").innerHTML = `<div style="max-width:760px;margin:auto">${tokenHtml(e)}${inTg ? "" : `<button class="btn ghost" id="back" style="width:100%;padding:10px">← Back</button>`}</div>`;
  bind($("#main")); $("#back")?.addEventListener("click", back); window.scrollTo(0, 0);
  live([m]).then(g => { if (g && view === m) { const y = scrollY; $("#main").firstElementChild.firstElementChild.outerHTML = tokenHtml(e); bind($("#main")); scrollTo(0, y); } });
}

/* ---------- shell ---------- */
const TABS = [["home","Home","home"],["signals","Signals","sig"],["alerts","Alerts","bell"],["pnl","PnL","pnl"],["more","More","more"]];
function fresh(){ if (!D) return null; return Math.max(D.updatedAt || 0, ...D.journal.slice(0, 50).map(e => e.lastT || 0)) || null; }
function pill(){ const el = $("#live"); if (!el || !D) return; const t = fresh(), a = Date.now()/1000 - t;
  el.className = "live" + (a > 3*3600 ? " r" : a > 1800 ? " a" : ""); el.innerHTML = `<i></i>${a > 3*3600 ? "Stale" : "Live"} · ${ago(a)}`;
  el.title = `Feed saved ${when(t)}. Scans run every 15 min; the feed is saved on new signals/results, else about every 2h.`; }
function theme(set){ const k = "degen-theme"; let v = set || (() => { try { return localStorage.getItem(k); } catch(e){ return null; } })() || (inTg && tg.colorScheme === "light" ? "light" : "dark");
  if (set) try { localStorage.setItem(k, v); } catch(e){}
  document.documentElement.dataset.theme = v; const b = $("#theme"); if (b) b.innerHTML = svg(v === "light" ? "moon" : "sun");
  const bg = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim(); document.querySelector('meta[name=theme-color]')?.setAttribute("content", bg);
  if (inTg) try { tg.setHeaderColor?.(bg); tg.setBackgroundColor?.(bg); } catch(e){} }
function shell(){
  document.body.insertAdjacentHTML("afterbegin", `<header class="top"><div class="in"><div class="logo">DG</div><div class="brand"><b>Degen Signals</b><small>free signals · alerts only</small></div>
   <span class="live" id="live"><i></i>Loading</span><button class="ib" id="theme" title="Theme" aria-label="Toggle theme"></button><button class="ib" id="refresh" title="Refresh" aria-label="Refresh">${svg("ref")}</button></div></header>`);
  document.body.insertAdjacentHTML("beforeend", `<nav class="bn"><div class="in">${TABS.map(([k, l, ic]) => `<button data-tab="${k}">${svg(ic)}${l}</button>`).join("")}</div></nav>`);
  theme(); }
function render(soft){
  document.querySelectorAll("nav.bn button").forEach(b => b.classList.toggle("on", b.dataset.tab === tab && !view)); pill();
  if (view) return detail(view);
  if (inTg) { tg.BackButton.hide(); if (tab !== "more") tg.MainButton.hide(); }
  if (soft && tab === "more") return; // keep lookup input/results while live prices land
  const y = soft ? scrollY : 0;
  ({home, signals, alerts, pnl, more})[tab]();
  bind($("#main")); if (soft) scrollTo(0, y);
}
function back(){ hap(); view = null; render(); }
function bind(root){
  root.querySelectorAll("[data-copy]").forEach(b => b.onclick = ev => { ev.stopPropagation(); copy(b.dataset.copy); });
  root.querySelectorAll("[data-open]").forEach(b => b.onclick = ev => { ev.preventDefault(); ev.stopPropagation(); open(b.dataset.open); });
}
document.addEventListener("click", ev => {
  const g = (s) => ev.target.closest(s);
  let b;
  if ((b = g("[data-tab]"))) { ev.preventDefault(); hap(); tab = b.dataset.tab; view = null; render(); return scrollTo(0, 0); }
  if ((b = g("[data-p]"))) { hap(); period = b.dataset.p; seg = null; return render(); }
  if ((b = g("[data-hp]"))) { hap(); hp = b.dataset.hp; return render(); }
  if ((b = g("[data-st]"))) { hap(); strat = b.dataset.st; return render(); }
  if ((b = g("[data-seg]"))) { hap(); seg = b.dataset.seg; return render(); }
  if ((b = g("[data-f]"))) { hap(); filt = b.dataset.f; return render(); }
  if ((b = g("[data-ev]"))) { hap(); evf = b.dataset.ev; return render(); }
  if ((b = g("[data-view]"))) { ev.preventDefault(); hap(); view = b.dataset.view; return render(); }
  if (g("#theme")) { hap(); return theme(document.documentElement.dataset.theme === "light" ? "dark" : "light"); }
  if (g("#refresh")) { hap("medium"); return refresh(); }
  if (g("[data-copy],[data-open]")) return;
  const cd = g("[data-m]"); if (cd) { hap(); view = cd.dataset.m; render(); }
});
document.addEventListener("click", ev => { const b = ev.target.closest("[data-copy]"); if (b && !b.onclick) { ev.stopPropagation(); copy(b.dataset.copy); } }, true);
async function refresh(){ const b = $("#refresh"); b.classList.add("spin"); LIVE = {}; TRIED = {};
  try { D = await getData(true); render(true); toast("Updated"); } catch(e) { toast("Refresh failed"); } b.classList.remove("spin"); }
// signals.json holds the last 30 days; older signals are in archive/YYYY-MM.json (feed.archive.files), merged here
let ARCH = {t: 0, key: "", tokens: [], journal: []};
async function getData(force){
  const d = await (await fetch(DATA + "?t=" + Date.now())).json(), files = d.archive?.files || [], key = files.join(",");
  if (files.length && (force || key !== ARCH.key || Date.now() - ARCH.t > 600000)) {
    const ds = await Promise.all(files.map(f => fetch(BASE + "archive/" + f + "?t=" + Math.floor(Date.now()/600000)).then(r => r.ok ? r.json() : {}).catch(() => ({}))));
    ARCH = {t: Date.now(), key, tokens: ds.flatMap(x => x.tokens || []), journal: ds.flatMap(x => x.journal || [])};
  }
  d.journal = d.journal || []; d.tokens = d.tokens || [];
  if (files.length) { const jm = new Set(d.journal.map(e => e.mint)), tm = new Set(d.tokens.map(t => t.mint));
    d.journal = d.journal.concat(ARCH.journal.filter(e => !jm.has(e.mint))); d.tokens = d.tokens.concat(ARCH.tokens.filter(t => !tm.has(t.mint))); }
  d.journal.sort((a, c) => c.t0 - a.t0);
  return d;
}
let INST = null;
async function load(){
  shell(); $("#main").innerHTML = '<div class="empty">Loading…</div>';
  try { D = await getData(); }
  catch(e) { $("#main").innerHTML = `<div class="empty">Could not load signals (${esc(e.message)})</div>`; return; }
  // token param: t.me/DegenGainsBot/app?startapp=<mint> (start_param / tgWebAppStartParam in query or hash), or website ?ca=<mint>
  const qs = new URLSearchParams(location.search), hs = new URLSearchParams(location.hash.slice(1));
  const start = tg?.initDataUnsafe?.start_param || qs.get("tgWebAppStartParam") || hs.get("tgWebAppStartParam") || qs.get("startapp") || qs.get("ca");
  const q = qs.get("q"), tb = ({lookup: "more", milestones: "alerts", journal: "more"})[qs.get("tab")] || qs.get("tab"), pp = qs.get("period");
  if (TABS.some(t => t[0] === tb)) tab = tb; if (PL[pp]) { period = pp; hp = pp; }
  if (q) { tab = "more"; render(); return more(q); }
  if (start && jrOf(start)) view = start; else if (start && isCA(start)) { tab = "more"; render(); return more(start); }
  render();
}
if (tg) { try { tg.ready(); tg.expand(); tg.BackButton.onClick(back); } catch(e){} }
addEventListener("beforeinstallprompt", e => { e.preventDefault(); INST = e; const b = $("#inst"); if (b) { b.hidden = false; b.onclick = () => INST.prompt(); } });
load();
setInterval(pill, 30000);
setInterval(async () => { try { D = await getData(); if (!view) render(true); else pill(); } catch(e){} }, 120000);
})();
