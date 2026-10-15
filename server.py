#!/usr/bin/env python3
"""Static server + optional pump.fun proxy (pump.fun blocks browser CORS / often Cloudflare-blocks servers).
Run: python3 server.py [port]  -> http://localhost:8080"""
import pipeline, http.server, json, sys, time, urllib.request
CACHE = {}  # mint -> (ts, json)
PUMP = "https://frontend-api-v3.pump.fun/coins?offset=0&limit=50&sort=last_trade_timestamp&order=DESC&includeNsfw=false"
class H(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/gmgn/"):
            import gmgn
            mint = self.path.split("/")[2].split("?")[0]
            body = json.dumps(gmgn.analyze(mint, pipeline.load_config()["gmgn"])).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)
            return
        if self.path.startswith("/holders/"):
            mint = self.path.split("/")[2].split("?")[0]
            try: body, code = json.dumps(pipeline.holders_and_clusters(mint)).encode(), 200
            except Exception as e: body, code = json.dumps({"error": str(e)}).encode(), 502
            self.send_response(code); self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(body)
        elif self.path.startswith("/pump/coins"):
            try:
                req = urllib.request.Request(PUMP, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
                body, code = urllib.request.urlopen(req, timeout=10).read(), 200
                json.loads(body)
            except Exception as e:
                body, code = json.dumps({"error": str(e)}).encode(), 502
            self.send_response(code); self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(body)
        else: super().do_GET()
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
http.server.ThreadingHTTPServer(("", port), H).serve_forever()
