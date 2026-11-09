"""Reproducible benchmark: localhost HTTP echo + real public sites.

    python benchmark.py            # localhost throughput + breadth
    python benchmark.py --public   # additionally hit 6 public sites
"""
from __future__ import annotations
import argparse, gzip, json, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crawler_stack import crawl, capabilities, extract

HTML = (b"<!doctype html><html><head><title>Bench Page</title></head><body>"
        b"<article><h1>Headline</h1><p>The quick brown fox jumps over the lazy dog.</p></article>"
        b"<script>document.title='JS Rendered Title';</script>"
        b"<a href='/p1'>one</a><a href='/p2'>two</a></body></html>")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in extra or []:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/js":
            return self.send(200, b"<html><head><title>Before</title></head><body><div id='x'>loading</div>"
                                 b"<script>document.title='JS Rendered Title';document.getElementById('x').textContent='rendered-ok';</script></body></html>")
        if p == "/json":
            return self.send(200, b'{"items":[{"id":1}]}', "application/json")
        if p == "/gzip":
            return self.send(200, gzip.compress(HTML), extra=[("Content-Encoding", "gzip")])
        if p == "/302":
            return self.send(302, b"", extra=[("Location", "/")])
        if p == "/gbk":
            return self.send(200, "<html><body><article><p>中文正文测试</p></article></body></html>".encode("gbk"), "text/html; charset=gbk")
        if p == "/robots.txt":
            return self.send(200, b"User-agent: *\nDisallow: /private\n", "text/plain")
        if p == "/cookie":
            return self.send(200, b"ok", extra=[("Set-Cookie", "sid=abc; Path=/")])
        if p == "/ua-gate":
            ua = self.headers.get("User-Agent", "")
            return self.send(200, b"passed") if "Chrome/" in ua else self.send(403, b"blocked")
        return self.send(200, HTML)

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--public", action="store_true")
    ap.add_argument("--n", type=int, default=100)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    report = {"capabilities": capabilities(), "localhost": {}, "breadth": {}}

    for mode, conc in [("fast", 20), ("stealth", 16)]:
        r = crawl([base] * args.n, mode=mode, concurrency=conc)
        report["localhost"][mode] = {"rps": r["rps"], "ok": sum(1 for x in r["results"] if x.get("status") == 200), "n": args.n}
    r = crawl([base + "js"] * 8, mode="render", concurrency=4)
    report["localhost"]["render"] = {"pages_per_s": r["rps"], "ok": sum(1 for x in r["results"] if x.get("title") == "JS Rendered Title"), "n": 8}

    for name, path in [("static", ""), ("js", "js"), ("gzip", "gzip"), ("redirect", "302"), ("json", "json"), ("gbk", "gbk"), ("robots", "robots.txt"), ("cookie", "cookie"), ("ua_gate", "ua-gate")]:
        x = crawl(base + path, mode="fast")["results"][0]
        report["breadth"][name] = x.get("status") or x.get("error")

    if args.public:
        urls = ["https://www.baidu.com", "https://www.python.org", "https://github.com",
                "https://httpbin.org/get", "https://pypi.org/simple/selectolax/",
                "https://raw.githubusercontent.com/psf/requests/main/README.md"]
        report["public"] = {}
        for mode in ["fast", "stealth"]:
            r = crawl(urls, mode=mode, concurrency=6, timeout=8)
            report["public"][mode] = {"rps": r["rps"],
                                      "ok": sum(1 for x in r["results"] if x.get("status") == 200),
                                      "errors": [x.get("error", "")[:60] for x in r["results"] if x.get("error")]}
    srv.shutdown()
    srv.server_close()
    out = json.dumps(report, ensure_ascii=False, indent=2)
    print(out, flush=True)
    with open("benchmark_results.json", "w", encoding="utf-8") as f:
        f.write(out)


if __name__ == "__main__":
    main()
