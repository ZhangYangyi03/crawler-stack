# crawler-stack

One-call concurrent web fetching with three interchangeable engines, fast HTML
extraction, and a benchmark you can reproduce yourself. Built and measured on
Windows 11 / Python 3.13, 2026-11-09.

```python
from crawler_stack import crawl

r = crawl(["https://example.com", "https://www.python.org"], mode="fast")
print(r["rps"], r["results"][0]["title"], r["results"][0]["links"][:5])
```

| mode | engine | use for | measured (localhost) |
|---|---|---|---|
| `fast` | aiohttp + semaphore | bulk static HTML | 2971 req/s |
| `stealth` | curl_cffi Chrome impersonation | UA / TLS fingerprint gates | 1107 req/s |
| `render` | headless Chromium (Playwright) | Javascript-rendered pages | ~5.7 pages/s (serial-safe) |

All dependencies are optional. Missing ones fall back to stdlib `urllib`, so the
module always imports and never aborts a batch because one URL failed.

## Install

```bash
pip install -e .
python -m playwright install chromium   # only needed for mode="render"
python -m pytest -q                     # 8 tests
python benchmark.py --public            # reproducible benchmark
```

## API

`crawl(urls, mode="fast", concurrency=20, timeout=8, with_text=False)` returns

```json
{"mode":"fast","count":2,"elapsed":0.21,"rps":9.5,
 "results":[{"url":"...","status":200,"bytes":1256,"elapsed":0.19,
             "title":"...","links":["/a"],"text":"..."}]}
```

Each URL is isolated: a timeout, DNS failure or TLS error becomes an `error` field
on that one result. `with_text=True` additionally runs `trafilatura` for clean
article markdown. `capabilities()` reports which engines are importable.

## Measured numbers

Localhost HTTP echo, N=100, concurrency 20 (see `benchmark.py`):

```
urllib sequential        307 req/s
aiohttp concurrent      2971 req/s
curl_cffi stealth       1107 req/s
Scrapy 2.20 + parse       96 req/s
Playwright render       13.75 pages/s peak (concurrent opening deadlocks
                        intermittently on Windows; stable serial reuse ~5.7 pages/s)
```

Parsing throughput (pages/s):

```
selectolax.lexbor  27684
lxml               22292
parsel             11596
bs4 + lxml          1844
trafilatura          139
```

Breadth 16/16 on a local fixture server: static HTML, JS-rendered DOM, gzip,
302 redirect, JSON, GBK encoding, robots.txt, sitemap.xml, cookies, UA gate,
403-with-fingerprint, plus four public sites.

**The honest caveat:** the same 6 public sites over the real network ran at
0.6 req/s (fast, 5/6 succeeded) and 0.7 req/s (stealth, 4/6). The localhost
numbers measure CPU and the event loop, not web-scale throughput. A single
network egress is the ceiling; see [docs/LIMITS.md](docs/LIMITS.md) for the full
list of hard limits (CAPTCHA, login walls, no frontier/dedup/resume, SPA
pagination, 30s host-agent sandbox, legal boundary).

## Layout

```
crawler_stack.py   the whole library, ~250 lines
benchmark.py       localhost fixture + optional public-site run
tests/             pytest suite
docs/LIMITS.md     what this cannot do and why
```

Apache-2.0.
