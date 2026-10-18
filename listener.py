#!/usr/bin/env python3
"""Always-on Telegram command listener (long polling). Env: DEGEN_TELEGRAM_BOT_TOKEN (box), TELEGRAM_CHAT_ID(S).
While this runs, keep workflow polling OFF (config.js commands.workflowPolling=false), since Telegram allows
only one getUpdates consumer at a time (409 Conflict otherwise), and no webhook may be set."""
import fcntl, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import commands as C
lock = open("/tmp/degen-listener.lock", "w")
try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError: print("listener already running", file=sys.stderr); sys.exit(0)
me = C.api("getMe", http_timeout=15)["result"]["username"]
if me.lower() != "degengainsbot": print(f"refusing: token belongs to @{me}, not @DegenGainsBot", file=sys.stderr); sys.exit(2)
ok = C.allowed()
print(time.strftime("%F %T"), f"listening as @{me} for {len(ok)} chats", file=sys.stderr, flush=True)
offset, back = None, 1
while True:
    try:
        r = C.poll(offset, 50)
        offset = C.process(r.get("result") or [], me, ok) or offset; back = 1
    except Exception as x:
        print(time.strftime("%F %T"), "poll error:", str(x)[:200], file=sys.stderr, flush=True)
        time.sleep(back); back = min(back * 2, 60)
    sys.stderr.flush()
