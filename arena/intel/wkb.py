"""World Knowledge Base: bitemporal queries over the append-only tables (design v2, section 3.2).

Every fact is one row: (subject, predicate, object | value, valid_from, valid_to, published_at, recorded_at,
source, hash, extractor, version, confidence). Nothing is updated in place: a fact ends when a later row with
op='end' closes it.

"As known at T" means: published_at <= T and recorded_at <= T, the latest row per fact key decides, and the
fact holds at T if valid_from <= T and (valid_to is empty or > T).

Two evidence modes:
  strict     recorded_at <= T as well. The only mode that counts as forward evidence.
  rehearsal  published_at <= T only, for sources whose publication time is trustworthy and never revised
             (registry flag pit_trusted). Used for technical rehearsals on backfilled history; always labelled.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .store import stable_id, utcnow

NEW_YORK = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def iso(dt):
    """Any datetime -> ISO UTC text. Naive datetimes are taken as UTC."""
    if isinstance(dt, str):
        return dt
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt.isoformat()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def ny_to_utc(day, hhmmss="23:59:59"):
    h, m, s = map(int, hhmmss.split(":"))
    d = date.fromisoformat(day) if isinstance(day, str) else day
    return iso(datetime.combine(d, time(h, m, s), tzinfo=NEW_YORK))


def decision_cutoff(day):
    """Information usable for the decision taken on trading day D (orders fill at the next open):
    everything published up to the end of D, New York time."""
    return ny_to_utc(day, "23:59:59")


def info_cutoff(day, trading_days):
    """Information a signal dated trading day D may use: published by the end of the previous trading day
    (New York). The value is then ready the morning of D, before the engine's decision for D."""
    prev = [d for d in trading_days if d < day]
    return decision_cutoff(prev[-1]) if prev else decision_cutoff(day_before(day))


def next_weekday(day):
    d = date.fromisoformat(day) + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.isoformat()


def signal_days(trading_days, now):
    """Trading days to date signals for: the known ones plus the next weekday after the last known day
    (today's session), once its information cutoff has passed."""
    if not trading_days:
        return []
    nxt = next_weekday(trading_days[-1])
    return list(trading_days) + ([nxt] if decision_cutoff(trading_days[-1]) <= now else [])


def effective_trading_day(published_at_utc, trading_days):
    """First trading day whose decision can use an item published at this instant."""
    dt = datetime.fromisoformat(published_at_utc.replace("Z", "+00:00")).astimezone(NEW_YORK)
    d = dt.date().isoformat()
    for td in trading_days:
        if td >= d:
            return td
    return None


def fact(subject_id, predicate, *, object_id=None, value=None, value_num=None, valid_from=None, valid_to=None,
         published_at, source_id, source_hash, extractor, extractor_version, confidence=1.0, op="assert",
         recorded_at=None):
    """Builds one fact row with a deterministic id."""
    key_obj = object_id if object_id is not None else value
    return {
        "fact_id": stable_id(subject_id, predicate, key_obj, valid_from, op, source_hash),
        "op": op, "subject_id": subject_id, "predicate": predicate, "object_id": object_id,
        "value": None if value is None else str(value), "value_num": value_num,
        "valid_from": valid_from or published_at, "valid_to": valid_to,
        "published_at": published_at, "recorded_at": recorded_at or utcnow(),
        "source_id": source_id, "source_hash": source_hash, "extractor": extractor,
        "extractor_version": extractor_version, "confidence": confidence,
    }


def _time_filter(T, mode, alias=""):
    a = f"{alias}." if alias else ""
    f = f"{a}published_at <= '{T}'"
    if mode == "strict":
        f += f" AND {a}recorded_at <= '{T}'"
    return f


def facts_as_of(con, T, mode="strict", predicate=None, subject_id=None):
    """Facts that hold at T as known at T."""
    extra = ""
    if predicate:
        extra += f" AND predicate = '{predicate}'"
    if subject_id:
        extra += f" AND subject_id = '{subject_id}'"
    q = f"""
    WITH known AS (
      SELECT *, ROW_NUMBER() OVER (
        PARTITION BY subject_id, predicate, COALESCE(object_id, value)
        ORDER BY recorded_at DESC, published_at DESC, op DESC, fact_id) AS rn
      FROM facts WHERE {_time_filter(T, mode)} {extra}
    )
    SELECT * EXCLUDE (rn) FROM known
    WHERE rn = 1 AND op = 'assert' AND valid_from <= '{T}' AND (valid_to IS NULL OR valid_to > '{T}')
    ORDER BY subject_id, predicate, object_id, value
    """
    return con.execute(q).df()


def events_between(con, start, T, mode="strict", predicate=None):
    """Event facts (valid_from in [start, T]) known at T."""
    extra = f" AND predicate = '{predicate}'" if predicate else ""
    q = f"""SELECT * FROM facts WHERE op = 'assert' AND valid_from >= '{start}' AND valid_from <= '{T}'
            AND {_time_filter(T, mode)} {extra} ORDER BY valid_from, subject_id, fact_id"""
    return con.execute(q).df()


def observations_as_of(con, T, series_like=None, mode="strict"):
    """Latest known value of each (series, entity, obs_date) as known at T (ALFRED-style vintages)."""
    extra = f" AND series_id LIKE '{series_like}'" if series_like else ""
    q = f"""
    WITH known AS (
      SELECT *, ROW_NUMBER() OVER (PARTITION BY series_id, entity_id, obs_date
                                   ORDER BY COALESCE(vintage, published_at) DESC, recorded_at DESC) AS rn
      FROM observations WHERE {_time_filter(T, mode)} AND obs_date <= '{T[:10]}' {extra}
    )
    SELECT * EXCLUDE (rn) FROM known WHERE rn = 1 ORDER BY series_id, entity_id, obs_date
    """
    return con.execute(q).df()


def documents_as_of(con, start, T, mode="strict", source_like=None):
    extra = f" AND source_id LIKE '{source_like}'" if source_like else ""
    q = f"""SELECT * FROM documents WHERE published_at >= '{start}' AND {_time_filter(T, mode)} {extra}
            QUALIFY ROW_NUMBER() OVER (PARTITION BY doc_id ORDER BY recorded_at) = 1
            ORDER BY published_at, doc_id"""
    return con.execute(q).df()


def entities_as_of(con, T):
    q = f"""SELECT * FROM entities WHERE recorded_at <= '{T}'
            QUALIFY ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY recorded_at DESC) = 1
            ORDER BY entity_id"""
    return con.execute(q).df()


def day_before(day, n=1):
    return (date.fromisoformat(day) - timedelta(days=n)).isoformat()
