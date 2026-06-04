from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen

from server import ProposalAIHandler, PUBLIC_DIR


def test_sitemap_head_reports_real_content_length():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), ProposalAIHandler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        req = Request(f"http://127.0.0.1:{port}/sitemap.xml", method="HEAD")
        with urlopen(req, timeout=5) as response:
            assert response.status == 200
            assert response.headers["Content-Type"] == "application/xml; charset=utf-8"
            assert int(response.headers["Content-Length"]) == (PUBLIC_DIR / "sitemap.xml").stat().st_size
            assert int(response.headers["Content-Length"]) > 0
    finally:
        httpd.shutdown()
        httpd.server_close()
