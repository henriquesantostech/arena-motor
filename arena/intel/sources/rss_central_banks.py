"""Federal Reserve and ECB RSS feeds: statements, press releases, speeches. Public; titles and links only are
stored as documents (full text stays in the raw archive). PIT: the item's pubDate, clamped to when we saw it."""
from .common import add_rss

SOURCE_ID = "central_bank_rss"
FEEDS = [
    ("https://www.federalreserve.gov/feeds/press_all.xml", "cb:fed:press", ["org:FED"]),
    ("https://www.federalreserve.gov/feeds/speeches.xml", "cb:fed:speech", ["org:FED"]),
    ("https://www.ecb.europa.eu/rss/press.html", "cb:ecb:press", ["org:ECB"]),
    ("https://www.ecb.europa.eu/rss/pub.html", "cb:ecb:publication", ["org:ECB"]),
]


def ingest(ctx):
    from .. import http
    n, failed = 0, 0
    for url, kind, ents in FEEDS:
        try:
            n += add_rss(ctx, SOURCE_ID, url, kind, ents)
        except http.FetchError:
            failed += 1
    return {"documents": n, "feeds_failed": failed}
