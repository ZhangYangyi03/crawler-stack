import gzip, json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from crawler_stack import crawl, extract, capabilities

HTML = b"<html><head><title>Hi</title></head><body><article><p>hello world</p></article><a href='/a'>a</a></body></html>"

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_GET(self):
        body = b"<html><head><title>Before</title></head><body><div id='x'>loading</div><script>document.title='After';document.getElementById('x').textContent='rendered';</script></body></html>" if self.path.startswith("/js") else HTML
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass

@pytest.fixture(scope="module")
def server():
    s = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}/"
    s.shutdown()

def test_empty():
    r = crawl([])
    assert r["count"] == 0 and r["results"] == [] and r["rps"] == 0.0

def test_bad_mode():
    with pytest.raises(ValueError):
        crawl(["x"], mode="nope")

def test_extract():
    d = extract(HTML)
    assert d["title"] == "Hi"
    assert "/a" in d["links"]
    assert "hello world" in d["text"]

def test_extract_no_deps(monkeypatch):
    import crawler_stack
    monkeypatch.setattr(crawler_stack, "_import", lambda n: None)
    d = crawler_stack.extract(HTML)
    assert d["title"] == "Hi" and "hello" in d["text"]

def test_fast(server):
    r = crawl([server] * 10, mode="fast", concurrency=5)
    assert r["count"] == 10
    assert all(x.get("status") == 200 for x in r["results"])
    assert r["results"][0]["title"] == "Hi"

def test_stealth(server):
    r = crawl([server] * 4, mode="stealth", concurrency=4)
    assert all(x.get("status") == 200 for x in r["results"])

def test_render(server):
    if not capabilities().get("playwright"):
        pytest.skip("playwright not installed")
    r = crawl([server + "js"], mode="render")
    assert r["results"][0].get("title") == "After"

def test_error_isolated(server):
    r = crawl([server, "http://127.0.0.1:1/nope", server], mode="fast")
    assert r["count"] == 3
    assert r["results"][0].get("status") == 200
    assert "error" in r["results"][1]
    assert r["results"][2].get("status") == 200

def test_capabilities_shape():
    c = capabilities()
    assert set(c) >= {"aiohttp", "curl_cffi", "playwright", "selectolax"}
    assert all(isinstance(v, bool) for v in c.values())
