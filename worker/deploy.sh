#!/bin/bash
# One-shot deploy of the Degen command Worker + webhook switch, with rollback to the box listener on failure.
# Needs: wrangler authenticated (npx wrangler whoami), $DEGEN_TELEGRAM_BOT_TOKEN in env (box; the Worker secret is still named TELEGRAM_BOT_TOKEN). Secret kept in ~/.degen/webhook_secret (never in repo).
set -uo pipefail
cd "$(dirname "$0")"
W="npx --yes wrangler@4"
SECRET_FILE=~/.degen/webhook_secret
TOK="${DEGEN_TELEGRAM_BOT_TOKEN:?DEGEN_TELEGRAM_BOT_TOKEN not set}"
TG="https://api.telegram.org/bot$TOK"
who=$(curl -s "$TG/getMe" | python3 -c "import json,sys;print(json.load(sys.stdin).get('result',{}).get('username',''))")
[ "$who" = "DegenGainsBot" ] || { echo "token is for @$who, not @DegenGainsBot: aborting"; exit 1; }
rollback() {
  echo "!! $1: rolling back to box listener"
  curl -s "$TG/deleteWebhook" >/dev/null
  pgrep -f run_listener.sh >/dev/null || (cd .. && nohup ./run_listener.sh >> listener.log 2>&1 &)
  exit 1
}
$W whoami 2>&1 | grep -q "You are logged in" || { echo "wrangler not authenticated"; exit 1; }
[ -s "$SECRET_FILE" ] || { mkdir -p ~/.degen; chmod 700 ~/.degen; openssl rand -hex 24 > "$SECRET_FILE"; chmod 600 "$SECRET_FILE"; }
OUT=$($W deploy 2>&1); echo "$OUT" | grep -vi secret | tail -8
URL=$(echo "$OUT" | grep -oE 'https://[a-z0-9.-]+\.workers\.dev' | head -1)
[ -n "$URL" ] || { echo "no workers.dev URL (register a subdomain: dashboard > Workers & Pages, or 'wrangler subdomain')"; exit 1; }
printf %s "$TOK" | $W secret put TELEGRAM_BOT_TOKEN >/dev/null 2>&1 || { echo "secret put TELEGRAM_BOT_TOKEN failed"; exit 1; }
tr -d '\n' < "$SECRET_FILE" | $W secret put WEBHOOK_SECRET >/dev/null 2>&1 || { echo "secret put WEBHOOK_SECRET failed"; exit 1; }
echo "$URL" > ~/.degen/worker_url
sleep 5
S=$(tr -d '\n' < "$SECRET_FILE")
# pre-switch checks against the Worker (unauthenticated request must be rejected)
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$URL" -H 'content-type: application/json' -d '{"message":{"chat":{"id":1318404489},"text":"/help"}}')
echo "no-secret POST -> HTTP $code"; [ "$code" = 403 ] || { echo "expected 403"; exit 1; }
# switch: stop listener, set webhook
pkill -f run_listener.sh; pkill -f listener.py; sleep 1
curl -s "$TG/setWebhook" --data-urlencode "url=$URL" --data-urlencode "secret_token=$S" \
  --data-urlencode 'allowed_updates=["message","channel_post"]' -d drop_pending_updates=false | grep -q '"ok":true' || rollback "setWebhook failed"
curl -s "$TG/getWebhookInfo" | python3 -c "import json,sys;r=json.load(sys.stdin)['result'];print('webhook:',r.get('url'),'pending',r.get('pending_update_count'),'last_error',r.get('last_error_message'))"
# end-to-end: simulated updates from the private chat with the secret header
for t in "/help" '/pnl $FRFR'; do
  body=$(python3 -c "import json,sys;print(json.dumps({'update_id':1,'message':{'message_id':0,'chat':{'id':1318404489,'type':'private'},'text':sys.argv[1]}}))" "$t")
  res=$(curl -s -X POST "$URL" -H 'content-type: application/json' -H "X-Telegram-Bot-Api-Secret-Token: $S" -H 'X-Degen-Test: 1' -d "$body")
  echo "$t -> $res"; echo "$res" | grep -q '"sent":[1-9]' || rollback "worker test failed"
done
echo "OK: webhook live at $URL"
