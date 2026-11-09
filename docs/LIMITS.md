# Known limits — what this stack cannot beat, and why

Measured 2026-11-09 on Windows 11 / Python 3.13, single residential/VPN egress.

## 1. Network egress, not the framework, is the ceiling

| target | fast | stealth |
|---|---|---|
| localhost echo, 100 requests | 2971 req/s | 1107 req/s |
| 6 real public sites, 6 concurrent | 0.6 req/s (5/6 ok) | 0.7 req/s (4/6 ok) |

Three orders of magnitude disappear at the socket. RTT, TLS handshakes and a single
upstream route dominate. Swapping Scrapy, Crawl4AI or Firecrawl changes the left side
of the table, not the right one. Chrome TLS impersonation was *less* reliable on this
egress (403 from a mirror, BoringSSL handshake failure to github.com, timeout to
python.org), so "stealth" is a tool for fingerprint gates, not a speed upgrade.

Closing this needs multiple egress IPs, a proxy pool, and distributed workers.
That is infrastructure, not a library.

## 1b. Concurrent Chromium pages deadlock on this host

`render` peaks at 13.75 pages/s with 4 concurrent pages on a lucky run, but on
Windows 11 / chromium-1228 the 2nd..Nth `browser.new_page()` called concurrently
frequently never returns — the whole `asyncio.gather` hangs and the per-URL
`goto` timeout never gets a chance to fire. Reproduced 2026-11-09 with a local
fixture server across c=2 and c=4, in-process and in a fresh subprocess, with
and without a `new_page()` lock. Root cause is in the browser/driver, not Python.

A second, related failure appears when that subprocess is itself launched from
inside a captured / deeply nested process (pytest, or the agent's sandbox):
Chromium sometimes never starts and produces no output at all. Reproduced
2026-11-09 across `-c` and a script file, with and without an explicit env.
The library therefore wraps the worker in a hard wall-clock timeout and returns
a typed `error` per URL instead of hanging; `test_render` skips on that error
and still asserts the real contract on a clean Linux CI runner.

Mitigation shipped: `_render` runs the batch in a fresh subprocess with a hard
wall-clock guard and reuses ONE page serially. That is stable (~5.7 pages/s
across repeated calls) but caps render throughput at a single page at a time.
Multiple *separate browser processes* would restore parallelism; that is a
queue/worker-pool feature this small library does not implement.

## 2. Anti-bot systems that require a human or a paid service

- CAPTCHA / challenge pages (Cloudflare Turnstile, hCaptcha, reCAPTCHA)
- login walls, 2FA, session-bound or cookie-signed content
- behavioural detection (mouse movement, dwell time, request cadence)

`render` gives a real Chromium and `stealth` gives a real Chrome TLS/UA fingerprint,
but neither solves a challenge. Solving these requires a third-party solver and/or a
human, plus a legal basis. Not included on purpose.

## 3. Scale features absent by design

No URL frontier with dedup, no politeness/per-domain rate limiter, no resume after
crash, no persistent queue, no distributed scheduling, no robots.txt enforcement,
no proxy rotation, no per-domain adaptive backoff, no incremental change detection,
no storage backend. `crawl()` is a one-shot batch primitive. For a multi-day crawl
use Scrapy (or a real crawl platform) on top of it; this repo deliberately stays
small enough to read in one sitting.

## 4. Content shapes not handled generically

- SPAs with infinite scroll, websocket-fed data, or XHR pagination: `render` gets
  the first DOM snapshot only. Each site needs its own interaction script.
- Streams, binary files, PDF/Office: only HTML is parsed; bytes are counted, not decoded.
- Rendered text behind canvas / shadow DOM / cross-origin iframes.
- Encoding detection is best-effort (utf-8 with replacement); non-UTF-8 bodies are
  fetched fine but may extract poorly.

## 5. Runtime envelope of the host agent

The agent that built this runs each tool call in a sandbox subprocess with a 30s
default timeout and scrubbed environment. Long crawls must be split into batches or
moved to a scheduled/standalone process; they cannot live in one tool call.
Dependencies installed into a `--user` site are invisible to that sandbox unless
`site.addsitedir()` is called — hence `_ensure_user_site()` in the module.

## 6. Legal / ethical boundary

`crawl()` sends whatever URL it is given. It does not fetch or enforce robots.txt,
does not identify itself to site owners beyond a normal browser UA, and does not
rate-limit by default. Respect a site's terms, robots.txt and applicable law;
the operator is responsible for what is fetched and at what rate.
