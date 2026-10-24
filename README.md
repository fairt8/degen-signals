# Degen Signals: free memecoin signal generator

> ⚠️ **NOT FINANCIAL ADVICE.** These are automated heuristic signals on extremely high-risk tokens. Do your own research.

## What it does
- Pulls live data from **DexScreener** (token-profiles/latest, token-boosts latest+top, search for pumpfun/pumpswap pairs, `/tokens/v1` batch lookup) and **Pump.fun** (`frontend-api-v3.pump.fun/coins` through the optional proxy).
- **Hard filter:** only tokens with at least one social link (X, Telegram, Discord, or community).
- **Score (0-100):** liquidity (20), 5m/1h volume (18), 5m/1h price change (14), 1h buy/sell ratio (14), age (8), market-cap range (8), boosts (6), narrative keywords (12), minus penalties for low liquidity or sell pressure.
- **Signals:** STRONG BUY (score ≥65, no sell pressure, enough liquidity), WATCH (≥45), AVOID. Each signal lists its reasons and risk flags (low liquidity, very new, sell pressure, dumping, thin liquidity compared with market cap).
- Sortable table, filter and search, auto-refresh every 45s, and links to DexScreener, pump.fun, the token's socials, and live X and TikTok searches for the ticker.

## Run locally
```
python3 server.py 8080   # open http://localhost:8080
```
`index.html` also works as a plain static file. In that case pump.fun data is skipped because the browser blocks it with CORS, and DexScreener still covers pumpfun and pumpswap pairs.

## Configure
Edit `config.js` to change the narrative keyword lists (AI, political, animals, …), the refresh interval, and the minimum liquidity.

## Narrative from X / TikTok
Neither X nor TikTok has a free API. Narrative scoring uses keyword matching on the token's name, symbol, and description, and each row links to a live X or TikTok search. Later you can add a server-side feed (for example the paid X API, or a scraper you run yourself) that updates `narratives` in `config.js` on a schedule.

## Deploy for free
- **GitHub Pages / Netlify / Vercel (static):** push the folder and deploy. No build step. pump.fun proxy data won't be available, but everything else works.
- **With the proxy:** Render or Railway free tiers can run `python3 server.py $PORT`. Or port `/pump/coins` to a Vercel or Netlify serverless function or a Cloudflare Worker. pump.fun sits behind Cloudflare and may block datacenter IPs.

## Community / Telegram bot idea
1. Create a bot with @BotFather and a public channel (for example @DegenSignals), then add the bot as an admin.
2. Run a small cron script (GitHub Actions on a schedule is free) that reuses the scoring in `app.js` and posts new STRONG BUY tokens with `https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=@DegenSignals&text=...`, including the reasons, risk flags, links, and the NFA disclaimer.
3. Link the channel and an X account from the site header to build the community.

## Filters & "5R hunter" preset
Defaults live in `config.js` → `filters`. The UI panel edits them (saved in localStorage; "Reset" restores config.js). Tick `preset5R` to show only tokens passing ALL:
mcap $20k–300k · liq ≥ $10k and ≥10% of mcap · age 15min–24h · volume(window) ≥ 1× mcap · txns(window) ≥ 1000 · sells > buys · 5m change 0–50%, 1h < 300% · X + (Telegram or website) · non-empty DexScreener description · top-10 holders < 25%.
`window` = `h1` or `h24`. The "5R filters" column shows ✓/✗/… per filter for every token (hover for values).
- Holders: `server.py` `/holders/<mint>` uses rugcheck.xyz's public report, removes pool/bonding-curve/known accounts, sums the top 10, and caches for 15 minutes. It is only called for Solana tokens that already pass every cheaper filter (max `holderLookupLimit` per refresh). It needs server.py, so static hosting can't do this check.
- "More sellers" uses sell txns > buy txns. DexScreener's free API doesn't expose unique makers.
- Description comes from DexScreener token-profiles/boosts only. There's no free per-token description endpoint.

## Sell-pressure rule & clusters (v3)
- Sell-pressure rule: sells ≥ `sellBuyRatioMin` × buys (default 0.6, in the selected window).
- Cluster check: the 5R preset fails if clustered supply is above `clusterMaxPct` (25%). The value used is the maximum across these sources:
  - **InsightX**: set `INSIGHTX_API_KEY` (UUID from the InsightX Hub, https://insightx.network). Calls `GET api.insightx.network/dex-metrics/v1/sol/<mint>/clusters` with header `X-API-Key`.
  - **Bubblemaps**: set `BUBBLEMAPS_API_KEY` (from a Pro subscription, https://pro.bubblemaps.io; 25 credits per call). Calls `GET api.bubblemaps.io/v0/tokens/map/solana/<mint>` with header `X-ApiKey`.
  - **rugcheck** insider-flagged holders (free).
  - **Free fallback**: the first funder of each top-10 holder, found via public Solana RPC (`SOLANA_RPC` env to override). Holders that share a funder count as a cluster. Results are cached 24h per wallet and 15 min per token.
- Each token links to Bubblemaps and InsightX maps.

## Headless alerts
`python3 alert.py [--window h24] [--state seen.json] [--all] [--debug]` prints JSON of newly passing tokens. Seen mints are stored in `seen.json`, so each token is reported once. You can cron it and pipe the output to a Telegram poster.

## Fully autonomous free deploy (GitHub Actions + Pages + Telegram)
Files: `.github/workflows/signals.yml` (cron every 10 min) · `alert.py` + `pipeline.py` + `notify.py` · `docs/` (PWA: index.html, manifest, sw.js, icon, signals.json) · `seen.json` (dedupe state).
1. Telegram: in @BotFather send `/newbot` and copy the token. Create a public channel and add the bot as an admin. The chat id is `@channelname`.
2. Create a **public** GitHub repo (Actions minutes are free and unlimited for public repos), then from this folder run: `git init && git add . && git commit -m init && git branch -M main && git remote add origin https://github.com/<you>/<repo>.git && git push -u origin main`
3. Repo → Settings → Secrets and variables → Actions. Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Optionally add `INSIGHTX_API_KEY`, `BUBBLEMAPS_API_KEY`, and `SOLANA_RPC` (a free Helius or QuickNode RPC is more reliable than the public one).
4. Settings → Actions → General → Workflow permissions: **Read and write**.
5. Settings → Pages → Deploy from branch `main`, folder `/docs`. The site goes live at `https://<you>.github.io/<repo>/` and can be installed as an app.
6. Actions tab → "5R signals" → Run workflow (first run). After that the cron runs on its own. GitHub can delay scheduled runs, and it disables them after 60 days without repo activity, but the bot's commits count as activity.
Local run (box): `DEGEN_TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=@ch python3 alert.py --signals docs/signals.json --telegram`. On the box only `DEGEN_TELEGRAM_BOT_TOKEN` is used; `TELEGRAM_BOT_TOKEN` is read only in GitHub Actions (repo secret) and the Worker (secret).
Graceful failures: if rugcheck or RPC blocks the GitHub runner, the token is skipped (never posted unverified) and the error appears in `lastRunErrors` in signals.json and on the site. pump.fun is not needed by the pipeline.

## Dev lookup & optional signals (v4)
- **Dev (creator) lookup** comes free from the rugcheck report. It shows the creator wallet, dev holding %, whether the dev sold, prior launches (migrated means current market cap ≥ $69k, dead means < $5k), rug-history risk, the dev wallet's first funder (public RPC), and whether that funder is linked to top holders. It changes the score only (`devScore` weights in config.js) and is never a 5R filter. It appears in the page, in alert.py JSON (`dev`, `devScore`, `devNotes`), on the PWA, and in Telegram.
- **Optional signals** are shown as info and only enforced when `*On: true`:
  - `estFeesMinSol`: estimated fees = 24h volume × `feeRate`, in SOL. This mirrors the Padre "total fees" filter and @OLeksa_one's fee rule.
  - `maxSingleHolderPct`: any non-pool wallet above 5%.
  - `freshWalletsMax`: top-10 holders with fewer than 15 lifetime transactions.
  - Insider networks from rugcheck feed into cluster %.

## Journal & watch mode (v5)
- Every 5R signal is saved to `docs/signals.json` → `journal`. Each run records entry price/mcap/time and devScore, the price at 1h and 24h, the max seen price (sampled about every 10 min, so it's a lower bound), and whether it hit 2x or 5x. `stats` holds win rate, average, best and worst. The site shows the journal and stats.
- Telegram sends follow-ups as replies to the original alert: 1h and 24h results, 2x/5x hits, and, for the first 6h, trend notices. Trend is fast (last 3 samples) vs slow (last 9), or DexScreener m5/h1 before 9 samples exist. A notice is sent only when the state changes: "trend turned up" or "momentum fading – consider exit".
- Dry run: `DRY_RUN=1 python3 alert.py --signals docs/signals.json --telegram` prints the Telegram messages instead of sending them.
- No workflow change needed. The journal lives inside the already-committed `docs/signals.json`.

## GMGN layer (optional)
`gmgn.py` uses GMGN's official OpenAPI (`https://openapi.gmgn.ai`, header `X-APIKEY`). Get a free key at https://gmgn.ai/ai by uploading an Ed25519 public key. It reads only, about 6 calls per token, and only for tokens that already pass the cheap 5R filters. Results are cached 10 min.
For each token it looks at holders tagged smart_degen, renowned (KOL), sniper, bundler, fresh_wallet and rat_trader, ignoring the pool account.
- **PASS** needs at least `minSmartKol` smart/KOL wallets still holding, sniper+bundler+fresh supply at or below `maxComboPct`, and each of snipers, bundlers and rat traders at or below its own cap.
- **Score:** +5 per smart/KOL holder (cap +15), −10 if the combined cap is exceeded, −5 for rat traders.
- **Never a gate:** every 5R alert still fires and shows `GMGN: PASS/FAIL — …`. It shows `SKIPPED` without a key and `ERROR` if the API fails.
Settings are in config.js → `filters.gmgn`. To enable it on GitHub, add the repo secret `GMGN_API_KEY` and add `GMGN_API_KEY: ${{ secrets.GMGN_API_KEY }}` to the workflow's `env:`.

## PnL & win rate (v6)
- `journal.period_stats` computes Today, This week (Mon), This month and All-time in WAT (UTC+1), grouped by alert time. For each it gives signals, wins, win rate, total PnL (sum of % per signal), average PnL, best/worst, and 2x/5x hits. The return used is the 24h result where available, otherwise the live price. Basis counts are shown alongside.
- Win = PnL above `winThresholdPct` (config.js, default 0).
- The 1h/24h follow-ups show PnL plus the max gain seen. Alerts themselves carry no stats block.
- A standalone PnL report goes to all chats twice a day, on the first run in the 12:00 AM WAT and 12:00 PM WAT slots. `lastReportSlot` (e.g. `2026-10-17-PM`) in docs/signals.json makes sure each slot sends once. The 12 AM report covers the day that just ended ("Yesterday").
- The website shows a PnL & win rate table at the top.

- **TP strategy (simulated):** set in `config.js` → `tp` (`atPct` 100, `sellFrac` 0.5, optional `stopLossPct`, off by default). If a signal's max gain seen reached +atPct, PnL = sellFrac×atPct + (1−sellFrac)×hold PnL; otherwise it's the same as hold. The result is shown next to hold in the 12h PnL report and in the site's PnL table, but not in alerts. Max gain is sampled about every 15 min, so real peaks may be higher or lower.

## Alert layout (PIRB-style) & extra metrics (v7)
Alerts start with the contract address (code), then name ($SYMBOL) | chain · DEX, age · holders, and an emoji row of the token's own socials. Below that is a blockquote with sections:
- **TOKEN DATA:** our historical 2x/rug odds, GMGN, MC first scan ⇨ now [time since], ATH MC, liq (% of MC), USD price (24h %), and volume with buys/sells.
- **DEV INFO:** wallet, held/sold, prior launches, Dex Paid, CTO.
- **HOLDERS INFO:** Top5 % [sum] | holders, snipers/bundlers/insiders, whales/fresh/smart money, cluster.
- **MISC INFO:** narrative, first scan MC.

The description goes at the bottom in italics, and inline URL buttons offer DexScreener, GMGN, Bubblemaps, X search and pump.fun.
Data sources:
- **Dex Paid:** DexScreener `/orders/v1` (approved tokenProfile).
- **CTO:** profile `cto` flag, `/community-takeovers/latest/v1`, or a communityTakeover order.
- **Top5, holders, whales (non-pool wallets ≥2%), insiders:** rugcheck.
- **Snipers, bundlers, fresh, smart money:** GMGN when a key is set, otherwise `n/a`. Fresh falls back to the RPC fresh-wallet count.
- **First scan:** `firstSeen` in docs/signals.json, the first time the bot saw a candidate, pruned after 72h.
- **2x odds / rug %:** computed only from our own journal (share of past signals ≥1h old that hit 2x, or fell ≥90%), with the sample size shown.

Missing data is shown as `n/a` and never guessed.

## Behaviour alarms, findings & score cap (v8)
- **Bot-holder %:** share of the sampled top-10 holders with 15+ distinct tokens or 100+ txns in a day. With a GMGN key it uses wallet activity; without one it falls back to RPC signatures and uses the txns/day rule only.
- **Serial-flipper %:** share of holders that bought 10+ tokens on their entry day. Needs GMGN, otherwise `n/a`.
- **Fresh ≤7d %:** holder's first tx within 7 days before launch (RPC).
- **Vol24h/Liq:** 🟠 at `volLiqAmber` (20x), 🔴 at `volLiqRed` (40x).
- **Score:** the same 0–100 heuristic as the web UI, plus dev and GMGN adjustments. It's capped at `scoreCap` (40) when bots or flippers are red, or when the dev has rug history or mostly dead launches. Shown as "capped at X, would be Y".
- **Findings:** red and amber issues in plain language, with a "N red, M amber" summary. Alerts show up to 4; the site shows all of them.

All thresholds are in config.js → `behaviour`. No extra RPC calls: these come from the signatures already scanned for funder checks, cached for 24h.

## Multiplier milestones (v9)
`milestones` in config.js (2, 5, 10, 15, 20, 30, 50–100) plus every `milestoneStep` (50x) beyond. Each journal entry records `milestones` {"10": ts}, `topMilestone` and `topMilestoneT`, based on the max price seen since the alert (sampled each run, tracked for 24h). The first time a signal crosses a milestone, the bot replies to the original alert in every chat, once per milestone. The 12h PnL report and the site table show counts per period: 2x and 5x always, higher ones only when hit. Milestones reached before this feature existed are recorded without sending a message.

## Telegram commands (v10)
`/tokens today|week|month|all [page]` (WAT boundaries, 20 per page), `/pnl <CA or $SYMBOL>`, `/help`. `/cmd@DegenGainsBot` also works.
The bot answers only in the chats in TELEGRAM_CHAT_ID(S), plus any in TELEGRAM_ALLOWED_CHATS. The command menu is set with `python3 commands.py --set-commands`.
Telegram allows only ONE update consumer at a time. Pick one:
- **Box listener** (current setup): `nohup ./run_listener.sh >> listener.log 2>&1 &`. It long-polls for instant replies and restarts itself if it crashes. It does not survive a box reboot.
- **Cloudflare Worker webhook** (free, 24/7): see `worker/README.md`.
- **Workflow polling** (slow, one check per run, about every 15 min): set `commands.workflowPolling: true` in config.js or the env `TG_COMMANDS_POLL=1`. The offset is stored as `tgOffset` in docs/signals.json. Keep it off while the listener or the Worker is active.
Command data: the journal comes from `signals.json` (GitHub raw, refreshed by each workflow run) and prices come live from DexScreener. A token that is not in the journal gets live price/MC and the note "not a Degen signal".

## Chart ATH, Fomo link, LP status + unlock monitor (v11)
- **Chart ATH** (`chart.py`): the GeckoTerminal public OHLCV API (free, ~30 req/min, throttled to one call per 2.1s and cached for 10 min) for the token's top SOL/USDC pools. It uses 5-min candles (~83h of history) and adds hourly candles for older pools. ATH MC = highest candle high × circulating supply (DexScreener MC ÷ price). Alerts show `MC … | ATH $X` and `🏔 ATH MC: $X (chart ATH, time)`. Each run, the journal raises `maxPrice` to the chart high since the alert (`maxSrc: "chart"`), which feeds max gain, TP sim and milestones; replies then say "chart high". Old entries are backfilled silently (4 per run, capped at the 24h window). A pool GeckoTerminal can't chart (e.g. one quoted in a non-SOL token) falls back to the bot's sampled max, marked as such.
- **Fomo**: `https://fomo.family/tokens/solana/<CA>` (Fomo's web/app token route). It appears in the alert link row and buttons, `/pnl`, and the site.
- **LP status** (`liquidity.py`): the rugcheck report for the DexScreener main pair gives `lpLockedPct` and lockers (unlock date). The label is one of 🔥 Burned (PumpSwap migrations burn LP) / 🔒 Locked X% · unlock date / 🔥🔒 Burned+locked / ⚠️ partial / ❌ not locked; bonding-curve and concentrated-liquidity pools show n/a.
- **Monitor**: each run re-checks up to 15 of the last 7 days' signals (least recently checked first) and replies once per event to the original alert in all chats: `⚠️ LIQUIDITY UNLOCKED` (burned/locked % falls ≥20 points from the max seen), `⚠️ LIQUIDITY PULLED` (DexScreener liquidity < 5% of the max seen, from ≥$2k), `⚠️ LIQUIDITY UNLOCK DATE PASSED`. Events are stored in `journal[].lpEvents`.

## Telegram Mini App (v12)
`docs/app/` is served at https://fairt8.github.io/degen-signals/app/. It's a single page with no build step. It uses telegram-web-app.js, theme colors, BackButton, MainButton and haptics, and also works in a normal browser.
- **Tabs:** Signals (Today/Week/Month/All, copy CA, MC ⇨ now live from DexScreener, chart ATH, LP, score and red/amber flags), PnL (hold vs TP, win rate, milestones per period) and Lookup (CA or $SYMBOL; non-signals show live DexScreener data). Tapping a signal opens a detail view with performance, milestones history, LP status and unlock/pull warnings, findings, holders/behaviour, GMGN, dev, links (opened with WebApp.openLink) and the description.
- **Deep links:** `?ca=<mint>` (detail), `?q=<query>` (lookup), `?tab=pnl`, and the Telegram `startapp=<mint>` parameter.
- **Bot:** the menu button (default) is a web_app button. `/app` replies with a web_app button in private chats and a url button in groups (groups can't use web_app buttons). Alerts get "📱 Open in Degen app": once `config.js app.tme` is set to the BotFather Mini App link, it opens inside Telegram via `<tme>?startapp=<mint>`; until then it opens the website.

## Safety check & trading-terminal links
- `🎯 Safety check: PASS/WARN/FAIL` (safety.py) replaces the GMGN line. Free sources: rugcheck report (mint/freeze authority, transfer tax, danger risks, rugged flag, insider graph), LP status, Solana-RPC dev/holder/funder analysis, plus InsightX DEX metrics (sniper/bundler/insider/dev/cluster % of supply) when `INSIGHTX_API_KEY` is set. Thresholds: `safety` in config.js. Info + score adjustment only; never blocks a 5R alert.
- InsightX free plan: 5 req/min, 1,000 req/month. Key (UUID) from https://hub.insightx.network → add repo secret `INSIGHTX_API_KEY`. Degen calls it once per NEW alert only.
- GMGN is dormant: used automatically only if `GMGN_API_KEY` ever appears.
- Links: Axiom `https://axiom.trade/t/<CA>?chain=sol`, BullX NEO `https://neo.bullx.io/terminal?chainId=1399811149&address=<CA>`, Shuriken bot `https://t.me/shuriken_trade_bot` (paste the CA; no documented token deep link). These terminals have no free public data API (Shuriken's API needs an account Agent Key; Axiom/BullX none).

## Box fallback scanner (while GitHub Actions is disabled)
The same "5R signals" job runs from the Grok Bot box every 15 min (:00/:15/:30/:45 +20s) via `~/.degen/run_scan.sh`
(separate clone in `~/.degen/repo`, secrets in `~/.degen/scan.env` chmod 600, log `~/.degen/scan.log`, flock-guarded, nohup loop + watchdog).
- Stop (switch back to Actions): `~/.degen/stop.sh`
- Resume: `~/.degen/start.sh`

## Data size: archive, commit gate, local candidate detail

- **`docs/signals.json` keeps the last 30 days** (max 200 tokens / 300 journal). Older signals move to
  `docs/archive/YYYY-MM.json` (month in WAT, deduped by mint; `docs/archive/index.json` lists them) and the feed's
  `archive` key names the files. Nothing is dropped: `stats`/`periodStats` (site, mini app PnL, 12h reports, milestones
  odds) are computed on recent + archived signals, and the Worker's `/tokens all|month…` and `/pnl` merge the archive
  when a period reaches past the feed or a lookup misses. The site and mini app load the archive files too.
- **Commit gate (`persist.py`)**: the scan commits only on meaningful change (new signals, seen.json, results,
  milestones, ATH/max, LP status, report slot, tgOffset, archive), or a heartbeat every ~2h (`DEGEN_HEARTBEAT_S`).
  updatedAt / candidates / lastRunErrors / live price ticks alone don't commit; they're kept as pending local state
  (box `~/.degen/state`, Actions `.state` cache) and restored on the next run.
- **Per-candidate detail (`firstSeen`) is off the public repo**: `alert.py --firstseen PATH` keeps it in a local
  untracked file (box `~/.degen/state/firstseen.json`, Actions `.state/`). The feed only has counts.
