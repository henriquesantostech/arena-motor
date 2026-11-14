"""Politicians and insiders module (design v2, section 6): alerts for the site, the Mirror shadow book and the
Mirror shadow signals. Only public, legal disclosures are used (House PTRs, SEC Form 4). Statistical patterns are
never accusations; wording is "pattern worth noting".

Mirror shadow book: copies every disclosed purchase of a universe stock (members of Congress; insiders' open-market
buys), entering at the open after the disclosure became public and holding `hold_days` trading days, equal
weight, 0.4% round-trip cost. It is measured against the equal-weight universe. It never trades real or arena
money; it shows whether "copy the disclosures" works after the disclosure delay.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .. import config
from ..archive import Archive, write_json
from .store import utcnow
from .wkb import decision_cutoff, effective_trading_day, info_cutoff, signal_days

HOLD_DAYS = 60
ROUND_TRIP = 0.004


def site_alerts(con, n=60):
    a = con.execute(f"""SELECT kind, person_name, role, ticker, action, size_low, size_high, traded_on, disclosed_at,
                               delay_days, note, source_id FROM alerts
                        QUALIFY ROW_NUMBER() OVER (PARTITION BY alert_id ORDER BY recorded_at) = 1
                        ORDER BY disclosed_at DESC, ticker LIMIT {n}""").df()
    return [{k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in r.items()} for r in a.to_dict("records")]


def mirror_book(con, archive_root, kinds=("congress", "insider"), hold=HOLD_DAYS):
    a = con.execute("""SELECT kind, ticker, action, disclosed_at, note FROM alerts WHERE action = 'buy'
                       QUALIFY ROW_NUMBER() OVER (PARTITION BY alert_id ORDER BY recorded_at) = 1""").df()
    a = a[a["kind"].isin(kinds)]
    p = Archive(archive_root).read("prices")
    opens = p.pivot_table(index="date", columns="ticker", values="open", aggfunc="last").astype(float).sort_index()
    days = list(opens.index)
    trades = []
    for r in a.itertuples():
        d0 = effective_trading_day(r.disclosed_at, days)
        if d0 is None or r.ticker not in opens.columns:
            continue
        i = days.index(d0)
        if i + 1 >= len(days):
            continue
        entry_day = days[i + 1]                       # decided on d0, filled at the next open
        j = min(i + 1 + hold, len(days) - 1)
        exit_day = days[j]
        px0, px1 = opens.at[entry_day, r.ticker], opens.at[exit_day, r.ticker]
        uni = opens.loc[[entry_day, exit_day], [t for t in config.universe_tickers() if t in opens.columns]]
        bench = float((uni.iloc[1] / uni.iloc[0] - 1).mean())
        if np.isfinite(px0) and np.isfinite(px1) and px0 > 0:
            ret = float(px1 / px0 - 1 - ROUND_TRIP)
            trades.append({"kind": r.kind, "ticker": r.ticker, "entry": entry_day, "exit": exit_day,
                           "open_position": j - (i + 1) < hold, "return_net": round(ret, 5),
                           "equal_weight_universe": round(bench, 5), "excess": round(ret - bench, 5)})
    df = pd.DataFrame(trades)
    out = {"rule": f"buy at the open after disclosure, hold {hold} trading days, equal weight, {ROUND_TRIP:.1%} round trip",
           "note": "Split-unadjusted opens; dividends ignored. Shadow only: no influence on any agent.",
           "by_kind": {}}
    for k in kinds:
        d = df[df["kind"] == k] if len(df) else df
        closed = d[~d["open_position"]] if len(d) else d
        out["by_kind"][k] = {"trades": int(len(d)), "closed": int(len(closed)),
                             "mean_excess_closed": round(float(closed["excess"].mean()), 5) if len(closed) else None,
                             "hit_rate_closed": round(float((closed["excess"] > 0).mean()), 3) if len(closed) else None,
                             "mean_excess_all_marked": round(float(d["excess"].mean()), 5) if len(d) else None}
    return out, df


def mirror_signal_rows(con, archive_root, start=None):
    """mirror_congress_60d: distinct members buying minus distinct members selling, disclosed in the last 60 days."""
    a = con.execute("""SELECT person_id, ticker, action, disclosed_at FROM alerts WHERE kind = 'congress'
                       QUALIFY ROW_NUMBER() OVER (PARTITION BY alert_id ORDER BY recorded_at) = 1""").df()
    if not len(a):
        return []
    p = Archive(archive_root).read("prices")
    known = sorted(p.loc[p["ticker"] == config.INDEX_PRICE, "date"].unique())
    done = set(con.execute("""SELECT DISTINCT date FROM signals WHERE signal_id = 'intel.mirror_congress_60d'
                              UNION SELECT DISTINCT date FROM signals_rehearsal
                              WHERE signal_id = 'intel.mirror_congress_60d'""").df()["date"])
    now, rows = utcnow(), []
    for day in signal_days(known, now):
        cut = info_cutoff(day, known)
        if day in done or cut > now or (start and day < start):
            continue
        lo = decision_cutoff((date.fromisoformat(day) - timedelta(days=61)).isoformat())
        w = a[(a["disclosed_at"] <= cut) & (a["disclosed_at"] > lo)]
        if not len(w):
            continue
        b = w[w["action"] == "buy"].groupby("ticker")["person_id"].nunique()
        s = w[w["action"] == "sell"].groupby("ticker")["person_id"].nunique()
        for t in config.universe_tickers():
            rows.append({"date": day, "ticker": t, "signal_id": "intel.mirror_congress_60d",
                         "value": float(b.get(t, 0) - s.get(t, 0)), "published_at": cut, "recorded_at": now,
                         "live": now <= decision_cutoff(day)})
    return rows


def run(store, archive_root=None):
    archive_root = archive_root or store.root.parent
    con = store.connect()
    alerts = site_alerts(con)
    write_json(store.root / "site" / "alerts.json", {"generated_at": utcnow(), "alerts": alerts,
                                                       "wording": "Disclosures, not accusations. Delays shown in days."})
    book, trades = mirror_book(con, archive_root)
    write_json(store.root / "lab" / "mirror_book.json", {"generated_at": utcnow(), **book})
    rows = mirror_signal_rows(con, archive_root)
    strip = lambda r: {k: v for k, v in r.items() if k != "live"}
    n = store.add("signals", [strip(r) for r in rows if r["live"]])
    n += store.add("signals_rehearsal", [strip(r) for r in rows if not r["live"]])
    store.flush()
    return {"alerts": len(alerts), "mirror_trades": int(len(trades)), "mirror_signal_rows": n}
