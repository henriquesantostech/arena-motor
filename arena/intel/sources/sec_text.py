"""SEC 10-K/10-Q text similarity ("Lazy Prices", Cohen, Malloy & Nguyen 2020).

For every universe company: the EDGAR submissions list (one JSON per company) gives each 10-K/10-Q with its
acceptance time, period and main document. The main document is fetched once, reduced to a word-count vector
(lower-case words of 3+ letters; markup, numbers and the hidden iXBRL header removed) and kept in the table
text_vectors with the document's SHA-256 and permanent URL (raw text by reference, like the GDELT files: the
public SEC archive is the permanent copy). When the same form for the period one year earlier is known, the cosine
similarity of the two vectors becomes the observation text:lazy_sim for the company, published at the filing's
dissemination time.

Backfill starts in 2024 so that 2025 filings have a prior-year match. Fair access: declared User-Agent, well under
10 requests per second, a wall-time budget per night with resume (filings already vectorised are skipped).
"""
import json
import math
import re
from collections import Counter
from datetime import date

from .. import http
from ..entities import company_id
from ..store import sha256
from .edgar import accepted_utc, cik_map, disseminated_utc

SOURCE_ID = "sec_text"
VERSION = "1"
FORMS = {"10-K", "10-Q"}
START = "2024-01-01"
WORD = re.compile(r"[a-z]{3,}")


def words(html: str) -> Counter:
    t = re.sub(r"(?is)<ix:header>.*?</ix:header>", " ", html)
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = re.sub(r"&[a-z#0-9]+;", " ", t.lower())
    return Counter(WORD.findall(t))


def cosine(a: dict, b: dict) -> float:
    if not a or not b:
        return float("nan")
    small, big = (a, b) if len(a) < len(b) else (b, a)
    dot = sum(v * big.get(k, 0) for k, v in small.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else float("nan")


def prior_match(rows, form, period):
    """The same form whose period ended 330-400 days before (closest to 365)."""
    p = date.fromisoformat(period)
    best = None
    for r in rows:
        if r["form"] != form or not r["period"]:
            continue
        gap = (p - date.fromisoformat(r["period"])).days
        if 330 <= gap <= 400 and (best is None or abs(gap - 365) < abs(best[0] - 365)):
            best = (gap, r)
    return best[1] if best else None


def _filings(ctx, cik):
    try:
        r, _, _ = http.fetch(ctx.store, SOURCE_ID, f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
    except http.FetchError:
        return []
    if r.status_code != 200:
        return []
    rec = r.json().get("filings", {}).get("recent", {})
    out = []
    for i, form in enumerate(rec.get("form", [])):
        if form not in FORMS or rec["filingDate"][i] < START or not rec["primaryDocument"][i]:
            continue
        acc = rec["accessionNumber"][i]
        out.append({"accession": acc, "form": form, "period": rec["reportDate"][i] or None,
                    "accepted": accepted_utc(rec["acceptanceDateTime"][i]),
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/"
                           f"{rec['primaryDocument'][i]}"})
    return out


def ingest(ctx):
    ciks = cik_map(ctx)
    known = {}
    if ctx.store.has("text_vectors"):
        tv = ctx.store.read("text_vectors")
        for r in tv.itertuples():
            known.setdefault(r.entity_id, []).append({"doc_id": r.doc_id, "form": r.form, "period": r.period,
                                                      "vector": r.vector})
    have = {d["doc_id"] for v in known.values() for d in v}
    order = ctx.store.state("sec_text_order", 0)
    tickers = [c["ticker"] for c in http.universe() if ciks.get(c["ticker"])]
    tickers = tickers[order % len(tickers):] + tickers[:order % len(tickers)]   # fair rotation across nights
    n_vec = n_obs = n_co = 0
    vec_rows, obs_rows = [], []
    for t in tickers:
        if ctx.out_of_time():
            break
        n_co += 1
        eid = company_id(t)
        rows = known.setdefault(eid, [])
        for f in sorted(_filings(ctx, ciks[t]), key=lambda f: f["accepted"]):
            doc_id = f"sec:{f['accession']}"
            if doc_id in have or ctx.out_of_time():
                continue
            try:
                r = http.get(f["url"], timeout=90)
            except http.FetchError:
                continue
            body = r.content
            sha = sha256(body)
            ctx.store.add("fetches", [{"fetch_id": sha, "source_id": SOURCE_ID, "url": f["url"], "fetched_at": ctx.now,
                                       "status": "by_reference", "bytes": float(len(body)), "path": None,
                                       "content_type": r.headers.get("Content-Type", "")}])
            wc = words(body.decode("utf-8", errors="ignore"))
            vec = json.dumps(dict(sorted(wc.items())), separators=(",", ":"))
            pub = disseminated_utc(f["accepted"], f["form"])
            vec_rows.append({"doc_id": doc_id, "entity_id": eid, "form": f["form"], "period": f["period"],
                             "published_at": pub, "recorded_at": ctx.now, "n_words": float(sum(wc.values())),
                             "text_sha": sha, "url": f["url"], "vector": vec})
            have.add(doc_id)
            n_vec += 1
            prev = prior_match(rows, f["form"], f["period"]) if f["period"] else None
            rows.append({"doc_id": doc_id, "form": f["form"], "period": f["period"], "vector": vec})
            if prev:
                sim = cosine(dict(wc), json.loads(prev["vector"]))
                if sim == sim:
                    obs_rows.append({"series_id": "text:lazy_sim", "entity_id": eid, "obs_date": f["period"],
                                     "value": round(sim, 6), "vintage": f["accession"], "published_at": pub,
                                     "recorded_at": ctx.now, "source_id": SOURCE_ID, "source_hash": sha})
                    n_obs += 1
    ctx.store.add("text_vectors", vec_rows)
    ctx.store.add("observations", obs_rows)
    ctx.store.set_state("sec_text_order", (order + n_co) % max(1, len(tickers)))
    return {"companies": n_co, "documents": n_vec, "similarities": n_obs}


def backfill(ctx):
    return ingest(ctx)
