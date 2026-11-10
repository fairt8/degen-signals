# Projects and templates guide

One place for each Degen project: what counts as "complete", where its code lives, and its shareable bot template.
Projects that aren't finished don't get a published template.

This guide has no secrets, keys, private links or personal details.

Updated 10 November 2026 (Africa/Lagos).

## Degen (this repo)

Free Solana memecoin signal app (Degenbot / DegenCall). It scans for "5R hunter" tokens, sends Telegram alerts and 12-hour PnL reports, and serves a public site plus a Telegram mini app. It does not trade or sign transactions.

Public site and mini app: [https://degen-signals.pages.dev/](https://degen-signals.pages.dev/) (mini app at [`/app/`](https://degen-signals.pages.dev/app/)).

**Projects, type and what each produces:**

| Project | Type | Produces |
|---|---|---|
| Signal scanner, Telegram alerts, 12h PnL reports, and Worker commands | Workflow | 1. 5R hunter Telegram alerts (PIRB-style format, with chart ATH, LP status, findings and description). 2. 12-hour PnL reports (daily, weekly, monthly and all-time; Hold and TP 50% sold at 2x; milestones). 3. Telegram command replies: `/tokens`, `/pnl`, `/help`, `/app`. |
| Public website and Telegram mini app | App | 1. The live site at https://degen-signals.pages.dev/ (signals, alerts, PnL, lookup). 2. The Telegram mini app at https://degen-signals.pages.dev/app/. 3. A client-side dashboard: hypothetical $100-per-signal equity curve (Hold and TP½@2x), strategy cards, freshness pill, theme toggle and market-cap progress bars. |
| Alpaca paper-trading bot | App | Planned, not started: 1. Paper-only orders from an agreed strategy. 2. A paper fill / activity log. 3. Paper PnL and performance summaries. Nothing can be built until paper API keys are provided. |

**Run it without the assistant:** [README](../README.md).

---

### 1. Signal scanner, Telegram alerts, 12h PnL reports, and Worker commands

**Type:** Workflow (a systemd timer on an Oracle VM, plus a Cloudflare Worker for the Telegram commands).

**Complete means all of these:** the 5R hunter scanner runs on its own; qualifying tokens produce Telegram alerts; 12-hour PnL reports go out at 12:00 AM and 12:00 PM Africa/Lagos (WAT); and the Worker answers `/tokens`, `/pnl`, `/help` and `/app`.

- [x] 5R hunter filters: small market cap, more than 1,000 transactions, sells at least 60% of buys, a DexScreener description required, top 10 holders under 25%, an InsightX cluster check, and an optional dev lookup.
- [x] PIRB-style Telegram alerts (contract address at the top, name, ATH market cap next to current market cap, key findings, description at the bottom; chart ATH, Fomo link, LP status, and BullX / Axiom / InsightX / Shuriken buttons).
- [x] Chart ATH uses a price-sanity and wick filter so a single candle cannot invent a fake all-time high.
- [x] 12-hour PnL reports at 12:00 AM and 12:00 PM WAT, covering daily, weekly, monthly and all-time for Hold and TP (50% sold at 2x), with milestones merged into ranges, long reports split into parts, a "Delayed report" label when a slot is late, and a link to the PnL tab.
- [x] Cloudflare Worker commands: `/tokens`, `/pnl`, `/help`, `/app`.
- [x] Scan and deploy run on an Oracle VM via a systemd timer (the earlier box loop is retired).
- [x] Shareable template staged as unpublished v1.

**Status: Complete.** Template: "Degen", unpublished v1, staged and waiting for the owner's confirmation. It will not be published until that confirmation is given.

---

### 2. Public website and Telegram mini app

**Type:** App.

**Complete means all of these:** the public site and mini app are live on Cloudflare Pages, the FVG-X-style redesign is in place, the BotFather mini app URL is set to the live `/app/` address, and (optionally) old fake MIGRATE milestone messages have been cleaned up.

- [x] Hosted on Cloudflare Pages at https://degen-signals.pages.dev/ (site, mini app, signal feed and archive).
- [x] Mini app at https://degen-signals.pages.dev/app/, with Signals, PnL and Lookup tabs, and deep links into a signal or the PnL tab.
- [x] FVG-X-style redesign: hypothetical $100-per-signal equity curve with Hold and TP½@2x toggles, strategy cards, freshness pill and refresh, theme toggle, and per-signal market-cap progress bars (computed in the browser; the signal feed is unchanged).
- [ ] Set the BotFather mini app URL to `https://degen-signals.pages.dev/app/`.
- [ ] Optional: clean up the old fake MIGRATE milestone messages in the Telegram chats.

**Status: Not fully complete.** No separate template is published for this app. The live site and mini app are part of the staged Degen template, which stays unpublished until the owner confirms it. What's still needed is listed above.

---

### 3. Alpaca paper-trading bot

**Type:** App.

**Complete means:** the owner has provided Alpaca paper API keys, the bot runs in paper mode only (no live trading and no transaction signing on Solana), and it can place paper orders, keep a fill / activity log, and report paper PnL.

- [ ] Receive the owner's Alpaca paper API keys (to be entered in the secret boxes, not in chat).
- [ ] Design and build the paper-trading bot.
- [ ] Paper order placement and a fill / activity log.
- [ ] Paper PnL and performance summaries.

**Status: Not started.** Waiting on the owner's paper API keys. No template will be created until the project is complete.

---

## Maintenance (not a separate project)

These are outstanding operational tasks. They are not secrets, but they should be done before certain switches are flipped.

- [ ] Apply the existing `signals-workflow.patch` (on the work box at `/workspace/signals-workflow.patch`) before GitHub Actions is ever re-enabled.
- [ ] File a GitHub support ticket for the hidden account that owns this repo, so the public repository page can be viewed normally.

---

## Summary

| Project | Agent | Type | Produces | Complete? | Template |
|---|---|---|---|---|---|
| Signal scanner, alerts, 12h PnL, Worker commands | Degen | Workflow | Alerts, 12h PnL reports, command replies | Yes | Staged, unpublished v1 (waiting for confirmation) |
| Public website and Telegram mini app | Degen | App | Live site, mini app, client-side dashboard | No (BotFather URL; optional message cleanup) | Covered by the staged Degen template; not published |
| Alpaca paper-trading bot | Degen | App | Paper orders, activity log, paper PnL (planned) | No (not started; waiting on paper API keys) | None until complete |
