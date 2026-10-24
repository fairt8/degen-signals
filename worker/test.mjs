import { handle } from "./worker.js";
const env = { SIGNALS_URL: "https://degen-signals.pages.dev/signals.json", BOT_USERNAME: "DegenGainsBot" };
for (const t of ["/help", "/tokens@DegenGainsBot week 2", "/pnl $FRFR", "/pnl $BONK", "/tokens@Other today", "/tokens yesterdayx"]) {
  const r = await handle(t, env); console.log("==", t, "->", r ? r.length + " msg(s)" : "ignored"); if (r) console.log(r[0].slice(0, 500));
}
