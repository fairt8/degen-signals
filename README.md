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
Local run: `TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=@ch python3 alert.py --signals docs/signals.json --telegram`
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
