"""How often does each defence fire on normal days? Replays daily routing snapshots for every customer session.

A customer session from AS C to its provider carries the prefixes originated by C's customer cone.
Each day is compared with what the session carried over the previous `history` days:

  strict prefix filter   legitimate new prefixes it would reject (its list is the history)
  max-prefix at k x      sessions whose size exceeds k x their largest size in the history window
  ConeGuard              bursts: at least `burst_new` new foreign prefixes from `burst_owners` distinct owners

A new prefix is "foreign" when a network outside the cone originated it during the history window.
Daily snapshots merge a whole day into one step, while ConeGuard looks at a 5-minute window, so the
ConeGuard alarm counts here are upper bounds.

    python -m replay.false_alarms --start 2026-08-01 --end 2026-10-10
"""
import argparse
import bz2
import datetime as dt
import gzip
import json
import pathlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import scipy.sparse as sp

from measure import fetch

ROOT = pathlib.Path(__file__).resolve().parent.parent
BURST_NEW = [5, 10, 25, 50, 100, 250]
BURST_OWNERS = [2, 5, 10, 25]
MAX_PREFIX = [1.5, 2, 3, 10]


def snapshot(path):
    with gzip.open(path, "rt") as f:
        for line in f:
            addr, plen, asns = line.split()
            yield f"{addr}/{plen}", {int(a) for a in asns.replace(",", "_").split("_") if a.isdigit()}


def customer_sessions(day):
    """{customer AS: its customer cone} for every AS that has at least one provider."""
    rel = fetch.as_rel(day)
    has_provider = set()
    with bz2.open(rel, "rt") as f:
        for line in f:
            if not line.startswith("#"):
                a, b, r = line.strip().split("|")[:3]
                if r == "-1":
                    has_provider.add(int(b))
    name = f"{day:%Y%m}01.ppdc-ases.txt.bz2"
    path = fetch._download(f"https://publicdata.caida.org/datasets/as-relationships/serial-1/{name}", fetch.DATA / "as-rel" / name)
    cones = {}
    with bz2.open(path, "rt") as f:
        for line in f:
            if line.startswith("#"):
                continue
            asns = [int(a) for a in line.split()]
            if asns[0] in has_provider:
                cones[asns[0]] = set(asns)
    return cones


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2026-08-01")
    ap.add_argument("--end", default="2026-10-10")
    ap.add_argument("--history", type=int, default=30, help="days of history that form the expected set")
    args = ap.parse_args()
    start, end, H = dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end), args.history
    days = [start + dt.timedelta(d) for d in range((end - start).days + 1)]
    assert len(days) > H, "need more days than the history window"

    print(f"downloading {len(days)} daily prefix-to-AS snapshots")
    with ThreadPoolExecutor(4) as pool:
        files = list(pool.map(fetch.pfx2as, days))

    cones = customer_sessions(days[H])
    sessions = list(cones)
    ancestors = defaultdict(list)  # member AS -> sessions whose cone contains it
    for c, members in cones.items():
        for m in members:
            ancestors[m].append(c)
    members = sorted({m for ms in cones.values() for m in ms})
    col = {a: i for i, a in enumerate(members)}
    row = {c: i for i, c in enumerate(sessions)}
    rows, cols = zip(*((row[c], col[m]) for c, ms in cones.items() for m in ms))
    cone_matrix = sp.csr_matrix((np.ones(len(rows), dtype=np.float32), (rows, cols)), shape=(len(sessions), len(members)))
    print(f"{len(sessions):,} customer sessions, {cone_matrix.nnz:,} cone memberships")

    last_seen = {}  # prefix -> {origin: index of the last day it originated the prefix}
    sizes = []      # per day: prefixes carried by each session
    daily = []      # per evaluated day: {session: [new, foreign, owner set]}
    for di, (day, path) in enumerate(zip(days, files)):
        origin_count = np.zeros(len(members), dtype=np.float32)
        events = []
        for prefix, origins in snapshot(path):
            hist = last_seen.setdefault(prefix, {})
            for o in origins:
                if o in col:
                    origin_count[col[o]] += 1
                seen = hist.get(o)
                if di >= H and (seen is None or di - seen > H):
                    prev = {a for a, d in hist.items() if di - d <= H} | (origins - {o})
                    events.append((o, prev))
            for o in origins:
                hist[o] = di
        sizes.append(cone_matrix @ origin_count)
        if di >= H:
            per = {}
            for o, prev in events:
                for c in ancestors.get(o, ()):
                    cone = cones[c]
                    if prev and not prev.isdisjoint(cone):
                        continue  # moved within the cone: the session already carried it
                    rec = per.setdefault(c, [0, 0, set()])
                    rec[0] += 1
                    outside = prev - cone
                    if outside:
                        rec[1] += 1
                        rec[2] |= outside
            daily.append(per)
            print(f"{day}: {len(events):,} new (origin, prefix) pairs, {len(per):,} sessions with new prefixes")

    n_days = len(days) - H
    session_days = len(sessions) * n_days
    out = {"period": f"{days[H]} to {end}", "history_days": H, "sessions": len(sessions),
           "evaluated_days": n_days, "session_days": session_days}

    strict_days = sum(len(per) for per in daily)
    strict_rejected = sum(rec[0] for per in daily for rec in per.values())
    out["strict_filter"] = {"session_days_with_rejections_pct": round(100 * strict_days / session_days, 3),
                            "legitimate_prefixes_rejected": strict_rejected,
                            "rejections_per_session_per_year": round(strict_rejected / len(sessions) * 365 / n_days, 2)}

    out["max_prefix"] = {}
    stack = np.vstack(sizes)
    for k in MAX_PREFIX:
        trips = 0
        for di in range(H, len(days)):
            peak = stack[di - H:di].max(axis=0)
            trips += int(((peak > 0) & (stack[di] > k * peak)).sum())
        out["max_prefix"][f"{k}x"] = {"false_teardowns": trips, "session_days_pct": round(100 * trips / session_days, 4),
                                      "per_session_per_year": round(trips / len(sessions) * 365 / n_days, 4)}

    grid = []
    for bn in BURST_NEW:
        for bo in BURST_OWNERS:
            alarms = sum(1 for per in daily for rec in per.values() if rec[1] >= bn and len(rec[2]) >= bo)
            grid.append({"burst_new": bn, "burst_owners": bo, "false_alarms": alarms,
                         "session_days_pct": round(100 * alarms / session_days, 4),
                         "per_session_per_year": round(alarms / len(sessions) * 365 / n_days, 4)})
    out["coneguard"] = grid

    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "false_alarms.json").write_text(json.dumps(out, indent=2))
    pd.DataFrame(grid).to_csv(ROOT / "results" / "false_alarms_coneguard.csv", index=False)
    print(json.dumps({k: v for k, v in out.items() if k != "coneguard"}, indent=2))
    print(pd.DataFrame(grid).to_string(index=False))


if __name__ == "__main__":
    main()
