const C = window.SIGNAL_CONFIG, DS = "https://api.dexscreener.com";
let rows = [], sortKey = "score", sortDir = -1;
const j = u => fetch(u).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
const fmt = n => n == null ? "-" : n >= 1e6 ? (n/1e6).toFixed(2)+"M" : n >= 1e3 ? (n/1e3).toFixed(1)+"K" : (+n).toFixed(0);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

async function load() {
  setStatus("Loading…");
  try {
    const [profiles, boosts, boostsTop, s1, s2] = await Promise.all([
      j(DS+"/token-profiles/latest/v1").catch(()=>[]),
      j(DS+"/token-boosts/latest/v1").catch(()=>[]),
      j(DS+"/token-boosts/top/v1").catch(()=>[]),
      j(DS+"/latest/dex/search?q=pumpfun").catch(()=>({pairs:[]})),
      j(DS+"/latest/dex/search?q=pumpswap").catch(()=>({pairs:[]}))]);
    for (const q of ["pump","solana","meme","ai"]) { const x = await j(DS+"/latest/dex/search?q="+q).catch(()=>({pairs:[]})); s1.pairs.push(...(x.pairs||[])); }
    const meta = {}, boostAmt = {};
    for (const p of [...profiles, ...boosts, ...boostsTop]) {
      const k = p.chainId+":"+p.tokenAddress;
      meta[k] = { ...(meta[k]||{}), description: p.description || meta[k]?.description, links: p.links || meta[k]?.links || [] };
      if (p.totalAmount || p.amount) boostAmt[k] = Math.max(boostAmt[k]||0, p.totalAmount||p.amount);
    }
    // pump.fun (via optional proxy) -> socials/description
    let pump = [];
    try { pump = await j(C.pumpProxy); } catch {}
    for (const c of (Array.isArray(pump)?pump:[])) {
      const k = "solana:"+c.mint, links = [];
      if (c.twitter) links.push({type:"twitter", url:c.twitter});
      if (c.telegram) links.push({type:"telegram", url:c.telegram});
      if (c.website) links.push({label:"Website", url:c.website});
      meta[k] = { description: c.description, links: [...(meta[k]?.links||[]), ...links], pump: true };
    }
    // resolve pairs via /tokens/v1 in batches of 30 per chain
    const byChain = {};
    for (const k of Object.keys(meta)) { const [ch, a] = k.split(":"); (byChain[ch] ||= []).push(a); }
    const pairs = [...(s1.pairs||[]), ...(s2.pairs||[]).filter(p=>p.chainId==="solana")];
    const reqs = [];
    for (const [ch, list] of Object.entries(byChain)) for (let i=0;i<list.length;i+=30)
      reqs.push(j(`${DS}/tokens/v1/${ch}/${list.slice(i,i+30).join(",")}`).catch(()=>[]));
    for (const r of await Promise.all(reqs)) pairs.push(...r);
    // best (highest-liquidity) pair per token
    const best = {};
    for (const p of pairs) { const k = p.chainId+":"+p.baseToken.address;
      if (!best[k] || (p.liquidity?.usd||0) > (best[k].liquidity?.usd||0)) best[k] = p; }
    rows = Object.entries(best).map(([k,p]) => build(p, meta[k]||{}, boostAmt[k]||p.boosts?.active||0))
      .filter(r => r.socials.length);           // HARD FILTER: must have a social
    rows.forEach(r => r.checks = checks(r)); render(); lookupHolders(); setStatus(`Updated ${new Date().toLocaleTimeString()} · ${rows.length} tokens with socials`);
  } catch (e) { setStatus("Error: "+e.message); }
}

function build(p, m, boost) {
  const socials = [];
  const add = (type,url) => url && !socials.some(s=>s.url===url) && socials.push({type,url});
  for (const s of p.info?.socials||[]) add(s.type, s.url);
  for (const l of m.links||[]) if (/twitter|telegram|discord|x\.com|t\.me|community/i.test((l.type||"")+(l.url||"")+(l.label||""))) add(l.type||l.label||"link", l.url);
  const websites = [...(p.info?.websites||[]).map(w=>w.url), ...(m.links||[]).filter(l=>!socials.some(s=>s.url===l.url)).map(l=>l.url)];
  const liq = p.liquidity?.usd||0, v5 = p.volume?.m5||0, v1 = p.volume?.h1||0,
        c5 = p.priceChange?.m5||0, c1 = p.priceChange?.h1||0, mc = p.marketCap||p.fdv||0,
        tx = p.txns?.h1||{buys:0,sells:0}, ratio = (tx.buys+1)/(tx.sells+1),
        ageH = p.pairCreatedAt ? (Date.now()-p.pairCreatedAt)/36e5 : null;
  const text = `${p.baseToken.name} ${p.baseToken.symbol} ${m.description||""}`.toLowerCase();
  const narratives = Object.entries(C.narratives).filter(([,kw]) => kw.some(w => new RegExp(`\\b${w}`).test(text))).map(([n])=>n);
  const clamp = (x,a,b)=>Math.max(a,Math.min(b,x)), reasons = [], flags = [];
  let s = 0;
  s += clamp(Math.log10(liq+1)/6*20,0,20);                 // liquidity 0-20
  s += clamp(Math.log10(v1+1)/6*12,0,12) + clamp(Math.log10(v5+1)/5*6,0,6); // volume 0-18
  s += clamp((c1+20)/60*8,0,8) + clamp((c5+10)/30*6,0,6);  // momentum 0-14
  s += clamp((ratio-0.5)/1.5*14,0,14);                     // buy pressure 0-14
  s += ageH==null?3: ageH<0.5?2: ageH<6?8: ageH<72?6: 3;  // age 0-8
  s += mc<1e4?2: mc<1e6?8: mc<2e7?6: 3;                   // mcap sweet spot 0-8
  s += clamp(boost/50*6,0,6);                              // boosts 0-6
  s += clamp(narratives.length*6,0,12);                    // narrative 0-12
  if (liq < C.minLiquidityUsd) { flags.push("Low liquidity"); s -= 15; }
  if (ageH!=null && ageH < 1) flags.push("Very new (<1h)");
  if (ratio < 0.8) { flags.push("Sell pressure"); s -= 10; }
  if (c1 < -30) flags.push("Dumping 1h");
  if (mc && liq/mc < 0.03) flags.push("Thin liq vs mcap");
  if (ratio>1.3) reasons.push(`Buys/sells ${ratio.toFixed(2)}`);
  if (c1>10) reasons.push(`+${c1.toFixed(0)}% 1h`);
  if (v1>50000) reasons.push(`$${fmt(v1)} 1h vol`);
  if (liq>50000) reasons.push(`$${fmt(liq)} liq`);
  if (boost) reasons.push(`Boosted ${boost}`);
  narratives.forEach(n=>reasons.push(`Narrative: ${n}`));
  s = Math.round(clamp(s,0,100));
  const signal = s>=65 && !flags.includes("Sell pressure") && liq>=C.minLiquidityUsd ? "STRONG BUY" : s>=45 ? "WATCH" : "AVOID";
  return { p, sym:p.baseToken.symbol, name:p.baseToken.name, chain:p.chainId, dex:p.dexId, liq, v5, v1, c5, c1, mc, ratio,
    ageH, boost, desc:(m.description||"").trim(), score:s, signal, reasons, flags, socials, websites, narratives };
}

function render() {
  const f = document.getElementById("filter").value, q = document.getElementById("q").value.toLowerCase();
  const list = rows.filter(r => (!F.preset5R || r.pass5R) && (!f || r.signal===f) && (!q || (r.sym+r.name+r.chain).toLowerCase().includes(q)))
    .sort((a,b)=> (a[sortKey] > b[sortKey] ? 1 : a[sortKey] < b[sortKey] ? -1 : 0) * sortDir);
  document.getElementById("rows").innerHTML = list.map(r => {
    const t = encodeURIComponent("$"+r.sym), a = r.p.baseToken.address;
    const pumpLink = r.chain==="solana" && /pump/.test(a+r.dex) ? ` · <a href="https://pump.fun/coin/${a}" target=_blank>pump.fun</a>` : "";
    return `<tr><td><span class="sig ${r.signal.replace(" ","")}">${r.signal}</span></td><td><b>${r.score}</b></td>
    <td><b>${esc(r.sym)}</b><br><small>${esc(r.name)} · ${r.chain}/${r.dex}</small></td>
    <td>$${fmt(r.liq)}</td><td>$${fmt(r.mc)}</td><td>$${fmt(r.v5)} / $${fmt(r.v1)}</td>
    <td class="${r.c5<0?'neg':'pos'}">${r.c5.toFixed(1)}%</td><td class="${r.c1<0?'neg':'pos'}">${r.c1.toFixed(1)}%</td>
    <td>${r.ratio.toFixed(2)}</td><td>${r.ageH==null?"-":r.ageH<48?r.ageH.toFixed(1)+"h":(r.ageH/24).toFixed(0)+"d"}</td>
    <td><small>${r.reasons.map(esc).join("<br>")||"-"}</small></td><td><small class="neg">${r.flags.join("<br>")||"-"}</small></td>
    <td><small>${r.pass5R?'<b class="pos">✅ 5R PASS</b><br>':''}${devCell(r)}<br>${r.checks.map(c=>`<span class="${c.ok===null?'':c.ok?'pos':'neg'}" title="${esc(c.v)}">${c.ok===null?'…':c.ok?'✓':'✗'} ${c.n}</span>`).join("<br>")}</small></td>
    <td><small><a href="${esc(r.p.url)}" target=_blank>DexScreener</a>${pumpLink}<br>
    ${r.socials.map(s=>`<a href="${esc(s.url)}" target=_blank>${esc(s.type)}</a>`).join(" · ")}<br>
    <a href="https://v2.bubblemaps.io/map?address=${a}&chain=${r.chain}" target=_blank>Bubblemaps</a> · <a href="https://app.insightx.network/bubblemaps/${r.chain}/${a}" target=_blank>InsightX</a><br><a href="https://x.com/search?q=${t}&f=live" target=_blank>X search</a> · <a href="https://www.tiktok.com/search?q=${encodeURIComponent(r.sym)}" target=_blank>TikTok</a></small></td></tr>`;
  }).join("");
}
// ---------- 5R hunter filters ----------
const F = Object.assign({}, C.filters, JSON.parse(localStorage.getItem("filters")||"{}"));
const HOLD = {};  // mint -> {top10Pct} cache (server also caches 15 min)
function checks(r) {
  const w = F.window, tx = r.p.txns?.[w] || {buys:0,sells:0}, vol = r.p.volume?.[w] || 0, mc = r.mc;
  const t = r.socials.map(s=>(s.type+" "+s.url).toLowerCase());
  const hasX = t.some(s=>/twitter|x\.com/.test(s)), hasTg = t.some(s=>/telegram|t\.me/.test(s)), hasWeb = r.websites.length>0;
  const h = HOLD[r.p.baseToken.address];
  const c = [
    ["MCap", mc>=F.mcapMin && mc<=F.mcapMax, "$"+fmt(mc)],
    ["Liq", r.liq>=F.liqMin && mc>0 && r.liq/mc*100>=F.liqPctMcapMin, "$"+fmt(r.liq)+" ("+(mc?(r.liq/mc*100).toFixed(0):0)+"% mc)"],
    ["Age", r.ageH!=null && r.ageH*60>=F.ageMinMin && r.ageH<=F.ageMaxH, r.ageH==null?"?":r.ageH.toFixed(2)+"h"],
    ["Vol/MC "+w, mc>0 && vol>=F.volToMcapMin*mc, (mc?(vol/mc).toFixed(2):0)+"x"],
    ["Txns "+w, tx.buys+tx.sells>=F.txnsMin, String(tx.buys+tx.sells)],
    ["Sells≥"+F.sellBuyRatioMin+"×buys", !F.requireMoreSellers || tx.sells>=F.sellBuyRatioMin*tx.buys, `${tx.sells}s/${tx.buys}b (txns; unique makers not in free API)`],
    ["5m 0-50%", r.c5>F.ch5Min && r.c5<F.ch5Max, r.c5+"%"],
    ["1h <300%", r.c1<F.ch1Max, r.c1+"%"],
    ["X + TG/web", (!F.requireX||hasX) && (!F.requireTgOrWeb||hasTg||hasWeb), `X:${hasX} TG:${hasTg} web:${hasWeb}`],
    ["Description", !F.requireDescription || r.desc.length>0, r.desc.slice(0,80)||"none"],
    ["Top10 <"+F.top10MaxPct+"%", r.chain!=="solana" ? false : h ? (h.top10Pct!=null && h.top10Pct<F.top10MaxPct) : null,
       r.chain!=="solana"?"non-Solana: no holder data":h?(h.top10Pct??"err")+"%":"pending"],
    ["Cluster ≤"+F.clusterMaxPct+"%", r.chain!=="solana" ? false : h ? (h.clusterPct!=null && h.clusterPct<=F.clusterMaxPct) : null,
       h ? `${h.clusterPct??"err"}% via ${h.clusterSource||"-"} ${JSON.stringify(h.clusterSources||{})}` : "pending"]
  ].map(([n,ok,v])=>({n,ok,v}));
  r.cheapPass = c.slice(0,-2).every(x=>x.ok);
  // optional signals (only enforced when the *On toggle is set)
  const pu=+r.p.priceUsd||0, pn=+r.p.priceNative||0, solUsd = pn && /SOL/.test(r.p.quoteToken?.symbol||"") ? pu/pn : null;
  r.estFeesSol = solUsd ? (r.p.volume?.h24||0)*F.feeRate/solUsd : null;
  if (F.estFeesOn) c.push({n:"Est fees ≥"+F.estFeesMinSol+" SOL", ok: r.estFeesSol!=null && r.estFeesSol>=F.estFeesMinSol, v:(r.estFeesSol??0).toFixed(2)+" SOL"});
  if (F.maxSingleHolderOn) c.push({n:"Max holder ≤"+F.maxSingleHolderPct+"%", ok: h ? h.maxSingleHolderPct<=F.maxSingleHolderPct : null, v: h?h.maxSingleHolderPct+"%":"pending"});
  if (F.freshWalletsOn) c.push({n:"Fresh wallets ≤"+F.freshWalletsMax, ok: h ? h.freshWallets<=F.freshWalletsMax : null, v: h?String(h.freshWallets):"pending"});
  r.pass5R = c.every(x=>x.ok===true);
  // dev lookup = score bonus/penalty only
  [r.devScore, r.devNotes] = devScore(h?.dev);
  r.baseScore ??= r.score;
  r.gmgn = h?.gmgn;
  r.score = Math.max(0, Math.min(100, r.baseScore + r.devScore + (r.gmgn?.scoreAdj||0) + (r.pass5R && r.narratives.length ? 5 : 0)));
  return c;
}
function devScore(d) {
  const W = F.devScore; if (!d || !d.wallet) return [0, []];
  let p = 0; const why = []; const add = (x,m)=>{p+=x; why.push((x>0?"+":"")+x+" "+m);};
  if (d.rugHistory) add(W.rugHistory, "dev rug history");
  if (d.priorMigrated) add(W.migratedBonus, `dev migrated ${d.priorMigrated} prior`);
  if (d.priorTokens>=W.serialLauncherMin && d.priorDead/Math.max(1,d.priorTokens)>0.8) add(W.serialLauncher, `serial launcher (${d.priorDead}/${d.priorTokens} dead)`);
  if ((d.holdPct||0)>W.holdPctMax) add(W.highHold, `dev holds ${d.holdPct}%`);
  if (d.funderSharedWithTopHolders) add(W.sharedFunder, "dev funder linked to top holders");
  return [p, why];
}
function devCell(r) {
  const h = HOLD[r.p.baseToken.address], d = h?.dev;
  const extra = `<small>fees≈${r.estFeesSol!=null?r.estFeesSol.toFixed(1)+" SOL":"?"}${h?` · max holder ${h.maxSingleHolderPct}% · fresh ${h.freshWallets}/10`+(h.insiderNetworks?.length?` · ${h.insiderNetworks.length} insider net`:""):""}</small>`;
  if (!d) return extra + (r.chain==="solana" ? "<br><small>dev: looked up when cheap filters pass</small>" : "");
  const g = h?.gmgn, gl = (!g || !["PASS","FAIL"].includes(g.status)) ? "" : `<br><small><b>GMGN: <span class="${g.status==="PASS"?"pos":g.status==="FAIL"?"neg":""}">${g.status}</span></b> ${esc((g.reasons||[]).join("; "))}${g.scoreAdj?` (score ${g.scoreAdj>0?"+":""}${g.scoreAdj})`:""}${g.link?` <a href="${g.link}" target=_blank>gmgn</a>`:""}</small>`;
  return extra + gl + `<br><small><b>Dev</b> <a href="${d.links.solscan}" target=_blank>${d.wallet.slice(0,4)}…</a> ${d.rugHistory?'<span class="neg">🚩rug history</span> ':''}${d.sold?'sold':'holds '+d.holdPct+'%'} · ${d.priorTokens} prior (${d.priorMigrated} migr, ${d.priorDead} dead)${d.funder?` · funded by ${d.funder.slice(0,4)}…`:''}<br>dev score <b class="${r.devScore<0?'neg':'pos'}">${r.devScore>0?'+':''}${r.devScore}</b> ${r.devNotes.join(", ")}</small>`;
}
async function lookupHolders() {
  const todo = rows.filter(r=>r.cheapPass && r.chain==="solana" && !HOLD[r.p.baseToken.address]).slice(0, F.holderLookupLimit);
  for (const r of todo) { const a = r.p.baseToken.address;
    try { HOLD[a] = await j("/holders/"+a); } catch { HOLD[a] = {top10Pct:null}; }
    try { HOLD[a].gmgn = await j("/gmgn/"+a); } catch { HOLD[a].gmgn = {status:"SKIPPED", reasons:["server.py not running"], scoreAdj:0}; } }
  rows.forEach(r => r.checks = checks(r)); render();
  setStatus(document.getElementById("status").textContent.replace(/ · 5R.*/,"")+` · 5R pass: ${rows.filter(r=>r.pass5R).length} (cheap filters: ${rows.filter(r=>r.cheapPass).length})`);
}
function buildPanel() {
  const el = document.getElementById("fpanel");
  el.innerHTML = Object.entries(F).filter(([,v])=>typeof v!=="object").map(([k,v]) => typeof v==="boolean"
    ? `<label><input type=checkbox data-f="${k}" ${v?"checked":""}> ${k}</label>`
    : k==="window" ? `<label>${k} <select data-f="${k}"><option ${v==="h1"?"selected":""}>h1</option><option ${v==="h24"?"selected":""}>h24</option></select></label>`
    : `<label>${k} <input size=6 data-f="${k}" value="${v}"></label>`).join(" ") + ` <button id="freset">Reset to config.js</button>`;
  el.querySelectorAll("[data-f]").forEach(i => i.onchange = () => {
    const k=i.dataset.f; F[k] = i.type==="checkbox" ? i.checked : k==="window" ? i.value : +i.value;
    localStorage.setItem("filters", JSON.stringify(F)); rows.forEach(r=>r.checks=checks(r)); render(); lookupHolders(); });
  document.getElementById("freset").onclick = () => { localStorage.removeItem("filters"); location.reload(); };
}
buildPanel();
const setStatus = t => document.getElementById("status").textContent = t;
document.querySelectorAll("th[data-k]").forEach(th => th.onclick = () => {
  sortDir = sortKey===th.dataset.k ? -sortDir : -1; sortKey = th.dataset.k; render(); });
document.getElementById("filter").onchange = render; document.getElementById("q").oninput = render;
document.getElementById("refresh").onclick = load;
load(); setInterval(load, C.refreshSeconds*1000);
