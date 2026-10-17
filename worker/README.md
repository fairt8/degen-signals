# Degen bot: 24/7 instant command replies on Cloudflare Workers (free)

The Worker is a Telegram webhook. It reads the journal from `signals.json` on GitHub and live prices from DexScreener,
and answers `/tokens`, `/pnl` and `/help` in the allowed chats within about a second. The free tier is 100k requests/day.

1. Create a free Cloudflare account, then: `npm i -g wrangler && wrangler login`
2. `cd worker && wrangler secret put TELEGRAM_BOT_TOKEN` (paste the bot token)
3. `wrangler secret put WEBHOOK_SECRET` (any random string, e.g. `openssl rand -hex 24`)
4. `wrangler deploy`. It prints `https://degen-bot.<you>.workers.dev`
5. Stop the box listener (`pkill -f run_listener.sh; pkill -f listener.py`), then point Telegram at the Worker:
   `curl "https://api.telegram.org/bot<TOKEN>/setWebhook" -d url=https://degen-bot.<you>.workers.dev -d secret_token=<WEBHOOK_SECRET> -d 'allowed_updates=["message","channel_post"]'`
6. Keep `commands.workflowPolling: false` in config.js. While a webhook is set, getUpdates is refused.

To go back to polling: `curl https://api.telegram.org/bot<TOKEN>/deleteWebhook`, then restart the box listener or enable workflowPolling.
Local logic test: `node test.mjs`.
