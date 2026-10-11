"""Compare defences on every replayed incident: how much of the leak each stops, how fast, and at what cost.

Needs results/<incident>/<collector>/ from measure.replay_incident.

    python -m replay.evaluate
"""
import argparse
import datetime as dt
import json
import pathlib

import pandas as pd
import yaml

from guard.engine import ALERT, BLOCKED, Config, ConeGuard
from measure import extract, fetch, rpki

ROOT = pathlib.Path(__file__).resolve().parent.parent
UTC = dt.timezone.utc


def utc(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=UTC)


def load(incident_id, collector):
    out = ROOT / "results" / incident_id / collector
    leaked = pd.read_csv(out / "leaked_prefixes.csv", dtype={"upstreams": str, "victim_origins": str})
    leaked = leaked.fillna({"upstreams": "", "victim_origins": ""})
    leaked["first_seen"] = pd.to_datetime(leaked["first_seen"], utc=True)
    return leaked.sort_values("first_seen").reset_index(drop=True), json.loads((out / "summary.json").read_text())


def run_guard(inc, leaked, expected, vrps, owners, cone, cfg):
    """Feed the leaked announcements to a ConeGuard on the leaker's session, in the order they were seen."""
    leaker, role = inc["leaker"], inc.get("role", "origin")
    guard = ConeGuard(leaker, cone, expected, vrps, owners, cfg)
    first_action, trigger, t0 = {}, None, leaked["first_seen"].iloc[0].timestamp()
    for row in leaked.itertuples():
        ts = row.first_seen.timestamp()
        origin = leaker if role == "origin" else int(row.victim_origins.split()[0])
        decision = guard.announce(ts, row.prefix, origin)
        first_action.setdefault(row.prefix, decision.action)
        if trigger is None and guard.burst_since is not None:
            trigger = guard.burst_since
    n = len(leaked)
    blocked = sum(guard.status.get(p) in BLOCKED for p in leaked["prefix"])
    exported_first = sum(a not in BLOCKED for a in first_action.values())
    return {
        "contained_pct": round(100 * blocked / n, 1),
        "never_exported_pct": round(100 * (n - exported_first) / n, 1),
        "exported_then_pulled": exported_first - (n - blocked),
        "trigger_after_s": round(trigger - t0) if trigger else None,
    }


def evaluate(incident_id, inc, collector, cfg):
    leaked, s = load(incident_id, collector)
    day = utc(inc["start"]).date()
    leaker = inc["leaker"]
    expected = fetch.announced_prefixes(leaker, *(utc(t).replace(tzinfo=None) for t in inc["baseline"]))
    pfx2as = extract.load_pfx2as(fetch.pfx2as(day))
    cone = fetch.customer_cone(leaker, day)

    def owners(prefix):
        return extract.legit_origins(prefix, pfx2as) - {leaker}

    try:
        vrps_then = rpki.VRPSet.from_ripe_archive(fetch.vrps(day))
    except Exception:
        vrps_then = None
    vrps_now = rpki.VRPSet.from_ripe_archive(fetch.vrps(dt.date.fromisoformat(s["rov_now_day"])))

    n = len(leaked)
    rows = [
        {"defence": "No defence", "stops_pct": 0.0, "cost": "-"},
        {"defence": "ROV, RPKI as it was then",
         "stops_pct": s["rov_then_invalid_pct"], "cost": "none" if vrps_then else "no RPKI archive for that day"},
        {"defence": "ROV, today's RPKI", "stops_pct": s["rov_now_invalid_pct"], "cost": "none"},
        {"defence": "Path checks (ASPA, RFC 9234, leak detectors)", "stops_pct": s["path_valley_pct"], "cost": "none"},
    ]
    for k in ("2x", "10x"):
        m = s["max_prefix"][k]
        rows.append({"defence": f"Max-prefix at {k} normal",
                     "stops_pct": m.get("contained_pct", 0.0),
                     "when": m.get("trips_at"),
                     "cost": f"session torn down: all {s['baseline_v4']} of the customer's own IPv4 routes lost"})
    rows.append({"defence": "Strict customer prefix filter", "stops_pct": 100.0,
                 "cost": "needs a complete, current list; rejects legitimate new routes otherwise"})
    for label, vrps in (("then", vrps_then), ("now", vrps_now)):
        if label == "then" and vrps is None:
            continue
        g = run_guard(inc, leaked, expected, vrps, owners, cone, cfg)
        when = f"+{g['trigger_after_s']}s after first leak" if g["trigger_after_s"] is not None else "never triggered"
        rows.append({"defence": f"ConeGuard, RPKI {label}", "stops_pct": g["contained_pct"], "when": when,
                     "cost": f"customer's own routes untouched; {g['exported_then_pulled']} prefixes exported briefly, then pulled",
                     "never_exported_pct": g["never_exported_pct"]})
    df = pd.DataFrame(rows)
    df.insert(0, "incident", incident_id)
    df.insert(1, "leaked_prefixes", n)
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("incidents", nargs="*")
    ap.add_argument("--collector", default="rrc00")
    ap.add_argument("--burst-new", type=int, default=Config.burst_new)
    ap.add_argument("--burst-owners", type=int, default=Config.burst_owners)
    ap.add_argument("--window", type=int, default=Config.window_s)
    args = ap.parse_args()
    corpus = yaml.safe_load((ROOT / "corpus" / "incidents.yaml").read_text())
    ids = args.incidents or [i for i in corpus if (ROOT / "results" / i / args.collector / "summary.json").exists()]
    cfg = Config(window_s=args.window, burst_new=args.burst_new, burst_owners=args.burst_owners)
    table = pd.concat([evaluate(i, corpus[i], args.collector, cfg) for i in ids], ignore_index=True)
    table.to_csv(ROOT / "results" / "defences.csv", index=False)
    with pd.option_context("display.max_colwidth", 70, "display.width", 250):
        for i, part in table.groupby("incident", sort=False):
            print(f"\n=== {i} ({part['leaked_prefixes'].iloc[0]:,} leaked prefixes)")
            print(part[["defence", "stops_pct", "when", "cost"]].fillna("").to_string(index=False))


if __name__ == "__main__":
    main()
