"""Polite HTTP for every adapter: descriptive User-Agent with contact, per-host rate limits, retries,
and every response body stored in the immutable raw archive before anything parses it.

Public logs never print response content, only status and counts.
"""
import os
import random
import threading
import time
from urllib.parse import urlparse

import requests

from .. import config

CONTACT = os.environ.get("ARENA_CONTACT") or "250372676+henriquesantostech@users.noreply.github.com"
USER_AGENT = (f"arena-of-agents/0.2 (paper-money research; +https://github.com/henriquesantostech/arena-motor; "
              f"{CONTACT})")
# SEC asks for "Company Name contact@email" style headers; this keeps the same information.
SEC_USER_AGENT = f"Arena of Agents research {CONTACT}"

# Minimum seconds between two requests to the same host (well under each provider's published limit).
MIN_INTERVAL = {
    "www.sec.gov": 0.15, "data.sec.gov": 0.15, "efts.sec.gov": 0.2,   # SEC: max 10/s
    "api.stlouisfed.org": 0.6,                                         # FRED: 120/min
    "api.bls.gov": 1.0, "apps.bea.gov": 1.2,
    "wikimedia.org": 0.1, "query.wikidata.org": 1.0, "www.wikidata.org": 0.2,
    "api.gdeltproject.org": 5.5,                                       # GDELT DOC: 1 per 5 s
    "finnhub.io": 1.1,                                                 # 60/min
    "api.open.fda.gov": 0.3, "clinicaltrials.gov": 0.3,
    "hn.algolia.com": 0.3, "www.federalregister.gov": 0.3,
    "api.congress.gov": 0.8, "api.open.fec.gov": 0.8, "lda.gov": 0.6, "lda.senate.gov": 0.6,
}
DEFAULT_INTERVAL = 0.5

_last = {}
_lock = threading.Lock()
_session = None


class FetchError(RuntimeError):
    pass


def session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})
    return _session


def _wait(host):
    interval = next((v for k, v in MIN_INTERVAL.items() if host == k or host.endswith("." + k)), DEFAULT_INTERVAL)
    with _lock:
        now = time.monotonic()
        wait = _last.get(host, 0) + interval - now
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.monotonic()


def get(url, *, params=None, headers=None, timeout=60, tries=4, ok_404=False):
    """GET with rate limit and retries. Returns the requests.Response (status 200, or 404 if ok_404)."""
    host = urlparse(url).netloc
    h = dict(headers or {})
    if host.endswith("sec.gov"):
        h.setdefault("User-Agent", SEC_USER_AGENT)
    last_err = None
    for attempt in range(tries):
        _wait(host)
        try:
            r = session().get(url, params=params, headers=h, timeout=timeout)
        except requests.RequestException as e:
            last_err = type(e).__name__
        else:
            if r.status_code == 200 or (ok_404 and r.status_code == 404):
                return r
            last_err = f"HTTP {r.status_code}"
            if r.status_code in (400, 401, 403, 404, 410):
                break
            if r.status_code == 429:
                time.sleep(float(r.headers.get("Retry-After", 10)) if str(r.headers.get("Retry-After", "")).isdigit() else 10)
        time.sleep(min(30, 2 ** attempt + random.random()))
    raise FetchError(f"{host}: {last_err}")


def fetch(store, source_id, url, *, params=None, headers=None, timeout=60, day=None, ok_404=False):
    """GET and archive the raw bytes. Returns (response, sha, raw_path)."""
    r = get(url, params=params, headers=headers, timeout=timeout, ok_404=ok_404)
    full = r.url if params else url
    if r.status_code != 200:
        return r, None, None
    sha, path = store.put_raw(source_id, _strip_keys(full), r.content, r.headers.get("Content-Type", ""), day=day)
    return r, sha, path


def _strip_keys(url):
    """Never store API keys in the archive's URL column."""
    import re
    return re.sub(r"(api_key|apikey|registrationkey|UserID|token|key)=[^&]+", r"\1=REDACTED", url, flags=re.I)


def universe():
    return config.UNIVERSE["companies"]
