// Edit freely: trending narratives (keyword lists) and scoring thresholds.
window.SIGNAL_CONFIG = {
  refreshSeconds: 45,
  pumpProxy: "/pump/coins", // only used if served by server.py; ignored when missing
  narratives: {
    "AI / Agents": ["ai","agent","gpt","bot","neural","llm","grok","claude","agi","robot"],
    "Political": ["trump","maga","elon","biden","usa","america","vote","president","doge"],
    "Animals": ["dog","cat","pepe","frog","inu","shib","wif","bonk","monkey","ape","penguin","hamster"],
    "Meme culture": ["meme","chad","wojak","based","moon","degen","sigma","brainrot","67"],
    "Gaming / Culture": ["game","pixel","anime","tiktok","viral","music"]
  },
  minLiquidityUsd: 5000
};
// Adjustable filters (also editable in the UI panel; UI changes are saved to localStorage)
window.SIGNAL_CONFIG.filters = {
  preset5R: false,          // "5R hunter": show only tokens passing ALL filters below
  mcapMin: 20000, mcapMax: 300000,
  liqMin: 10000, liqPctMcapMin: 10,
  ageMinMin: 15, ageMaxH: 24,
  window: "h1",             // "h1" or "h24": window for volume & txn-count rules
  volToMcapMin: 1,          // volume(window) >= X * mcap
  txnsMin: 1000,            // buys+sells in window
  requireMoreSellers: true, // sell pressure rule: sells >= sellBuyRatioMin * buys (txn counts)
  sellBuyRatioMin: 0.6,
  ch5Min: 0, ch5Max: 50, ch1Max: 300,
  requireX: true, requireTgOrWeb: true, requireDescription: true,
  top10MaxPct: 25,          // top-10 holders (pools excluded) via rugcheck, through server.py
  clusterMaxPct: 25,        // fail 5R if clustered / common-funder supply > this %
  holderLookupLimit: 15,
  // simulated TP strategy (report/site only): sell sellFrac at +atPct if max gain seen reached it, rest at hold basis.
  // stopLossPct: null = off; e.g. -50 exits all at -50% if TP never hit and min price seen fell that far.
  tp: { atPct: 100, sellFrac: 0.5, stopLossPct: null },
  // behaviour alarms (bots / flippers / fresh wallets / inflated volume) + score cap
  behaviour: { botTokensDay: 15, botTxDay: 100, flipperTokens: 10, botPctAmber: 15, botPctRed: 30,
               flipperPctAmber: 15, flipperPctRed: 30, freshPctAmber: 30, freshPctRed: 50, volLiqAmber: 20, volLiqRed: 40, scoreCap: 40 },
  // multiplier milestones (max gain seen since alert); beyond the last one, every +milestoneStep (150x, 200x, ...)
  milestones: [2, 5, 10, 15, 20, 30, 50, 60, 70, 80, 90, 100], milestoneStep: 50,
  // Telegram commands (/tokens, /pnl, /help). Exactly one consumer may poll getUpdates:
  // keep workflowPolling false while the box listener (listener.py) or a Cloudflare Worker webhook is running.
  // Repo variable / env TG_COMMANDS_POLL=1 or 0 overrides this.
  commands: { workflowPolling: false },
  // Mini app: website URL; tme = t.me Mini App link after BotFather /newapp (e.g. "https://t.me/DegenGainsBot/app"), used for buttons in groups/alerts
  app: { url: "https://fairt8.github.io/degen-signals/app/", tme: "https://t.me/DegenGainsBot/app" },
  winThresholdPct: 0,       // journal: a signal "wins" if its PnL % is above this
  // PnL report: standalone Telegram message at 12:00 AM and 12:00 PM WAT (first run in each slot; lastReportSlot in docs/signals.json)
  // ---- optional signals (from @OLeksa_one / Padre-style filters); *_On=false => info/flag only, true => required for 5R
  feeRate: 0.0125, estFeesMinSol: 1.5, estFeesOn: false,          // est. fees = vol24 * feeRate (pump.fun ~1.25%)
  maxSingleHolderPct: 5, maxSingleHolderOn: false,                // single non-pool wallet > X% = caution
  freshWalletsMax: 3, freshWalletsOn: false,                      // top-10 holders with <15 lifetime txs
  // ---- dev (creator) lookup: score bonus/penalty only, never a 5R filter
  // ---- GMGN (optional, needs GMGN_API_KEY; info + score only, never blocks a 5R alert)
  gmgn: { minSmartKol: 1, maxComboPct: 25, maxSniperPct: 10, maxBundlerPct: 15, maxRatPct: 10,
          smartKolBonusEach: 5, smartKolBonusCap: 15, comboPenalty: -10, ratPenalty: -5 },
  devScore: { rugHistory: -20, migratedBonus: 5, serialLauncher: -10, serialLauncherMin: 5, holdPctMax: 5, highHold: -10, sharedFunder: -10 }
};
