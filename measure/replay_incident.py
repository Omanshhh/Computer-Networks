"""Replay one incident from corpus/incidents.yaml and write results/<incident>/<collector>/.

    python -m measure.replay_incident as55410-2021
"""
import argparse
import datetime as dt
import ipaddress
import json
import pathlib
from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import requests
import yaml

from . import extract, fetch, pathcheck, rpki

ROOT = pathlib.Path(__file__).resolve().parent.parent
UTC = dt.timezone.utc
MAX_PREFIX_FACTORS = [1.5, 2, 3, 5, 10]


def utc(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=UTC)


def hms(ts):
    return dt.datetime.fromtimestamp(ts, UTC).strftime("%H:%M:%S")


def is_v4(prefix):
    return ipaddress.ip_network(prefix, strict=False).version == 4


def as_names(asns):
    cache_path = fetch.DATA / "ripestat" / "as_names.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    for asn in asns:
        if str(asn) not in cache:
            r = requests.get("https://stat.ripe.net/data/as-overview/data.json", params={"resource": f"AS{asn}"}, timeout=60)
            holder = r.json()["data"].get("holder") if r.ok else None
            cache[str(asn)] = holder or "?"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=1))
    return {asn: cache[str(asn)] for asn in asns}


def replay(incident_id, inc, collector):
    out = ROOT / "results" / incident_id / collector
    out.mkdir(parents=True, exist_ok=True)
    start, end = utc(inc["start"]), utc(inc["end"])
    leaker, upstream, role = inc["leaker"], inc.get("upstream"), inc.get("role", "origin")

    print(f"[{collector}] fetching data")
    baseline = fetch.announced_prefixes(leaker, *(utc(t).replace(tzinfo=None) for t in inc["baseline"]))
    files = fetch.ris_updates(collector, start.replace(tzinfo=None), end.replace(tzinfo=None))
    now_day = fetch.latest_vrp_day()
    try:
        vrps_then = rpki.VRPSet.from_ripe_archive(fetch.vrps(start.date()))
    except requests.HTTPError:
        vrps_then = None  # no archived VRP list for that day (RPKI began in 2011; early years only have raw repos)
    vrps_now = rpki.VRPSet.from_ripe_archive(fetch.vrps(now_day))
    pfx2as = extract.load_pfx2as(fetch.pfx2as(start.date()))
    rels = pathcheck.Relationships.from_caida(fetch.as_rel(start.date()))
    print(f"[{collector}] {len(files)} update files, VRPs {start.date()}={vrps_then.count if vrps_then else 'n/a'} "
          f"{now_day}={vrps_now.count:,}, {len(rels):,} AS links")

    timeline = []

    def on_minute(t, r):
        timeline.append({"time": dt.datetime.fromtimestamp(t, UTC), **r.counts()})

    r = extract.LeakReplay(leaker, baseline, role=role)
    checkpoints = {utc(t).timestamp(): t for t in inc.get("checkpoints", [])}
    snaps = r.run(files, checkpoints=checkpoints, on_minute=on_minute)
    print(f"[{collector}] replayed {r.updates:,} updates")

    path_class = {path: pathcheck.classify(path, rels) for paths in r.prefix_paths.values() for path in paths}
    rows = []
    for prefix, first in r.first_seen.items():
        if role == "origin":
            victims = extract.legit_origins(prefix, pfx2as) - {leaker}
            route_origin = leaker
        else:
            victims = set(r.origins[prefix]) - {leaker}
            route_origin = r.origins[prefix].most_common(1)[0][0]
        classes = [path_class[p] for p in r.prefix_paths[prefix]]
        rows.append({
            "prefix": prefix,
            "first_seen": dt.datetime.fromtimestamp(first, UTC),
            "peers": len(r.peers_ever[prefix]),
            "upstreams": " ".join(str(u) for u in sorted(r.upstream_ever[prefix], key=str)),
            "victim_origins": " ".join(map(str, sorted(victims))),
            "rov_then": vrps_then.validate(prefix, route_origin) if vrps_then else "n/a",
            "rov_now": vrps_now.validate(prefix, route_origin),
            # Path checks stop a prefix only if every path it spread along has a valley; one clean path
            # and it still reaches the Internet.
            "path_check": pathcheck.VALLEY_FREE if pathcheck.VALLEY_FREE in classes else
                          pathcheck.VALLEY if all(c == pathcheck.VALLEY for c in classes) else pathcheck.UNKNOWN,
            "paths": len(classes),
            "paths_with_valley": classes.count(pathcheck.VALLEY),
        })
    leaked = pd.DataFrame(rows).sort_values("first_seen")
    leaked.to_csv(out / "leaked_prefixes.csv", index=False)
    pd.DataFrame(timeline).to_csv(out / "timeline.csv", index=False)

    n = len(leaked)
    victim_counts = Counter(int(a) for v in leaked["victim_origins"] for a in v.split())
    top = victim_counts.most_common(15)
    names = as_names([a for a, _ in top])
    via_up = leaked["upstreams"].str.split().apply(lambda u: str(upstream) in u).sum() if upstream else None

    # Max-prefix counterfactual on the leaker's IPv4 session: when would a limit of k x baseline trip,
    # and how many leaked prefixes were already out by then? Collectors see a subset of what the
    # upstream received, so the true trip time is no later than this estimate.
    base_v4 = sum(is_v4(p) for p in baseline)
    leaked_v4 = leaked[leaked["prefix"].map(is_v4)].reset_index(drop=True)
    max_prefix = {}
    for k in MAX_PREFIX_FACTORS:
        limit = max(int(k * base_v4), base_v4 + 1)
        over = limit - base_v4  # leaked prefixes accepted before the limit is crossed
        if over < len(leaked_v4):
            trip = leaked_v4["first_seen"].iloc[over]
            max_prefix[f"{k}x"] = {"limit": limit, "trips_at": trip.strftime("%H:%M:%S"),
                                   "leaked_before_trip": over, "contained_pct": round(100 * (1 - over / len(leaked_v4)), 1)}
        else:
            max_prefix[f"{k}x"] = {"limit": limit, "trips_at": None}

    def pct(col, keys):
        c = leaked[col].value_counts()
        return {k: {"count": int(c.get(k, 0)), "pct": round(100 * c.get(k, 0) / n, 1)} for k in keys}

    rov_keys = (rpki.VALID, rpki.INVALID, rpki.NOTFOUND)
    path_keys = (pathcheck.VALLEY, pathcheck.VALLEY_FREE, pathcheck.UNKNOWN)

    checkpoint_rows = {}
    for ts, label in checkpoints.items():
        s = snaps[ts]
        active = s["active_prefix_set"]
        active_victims = {int(a) for v in leaked[leaked["prefix"].isin(active)]["victim_origins"] for a in v.split()}
        checkpoint_rows[label[11:16]] = {"prefixes": s["active_prefixes"], "victim_ases": len(active_victims),
                                         "via_upstream": s["active_via"].get(upstream, 0), "peers": s["active_peers"]}

    summary = {
        "incident": incident_id, "collector": collector, "role": role, "updates_replayed": r.updates,
        "baseline_v4": base_v4, "baseline_v6": len(baseline) - base_v4,
        "leaked_prefixes": n, "leaked_v4": len(leaked_v4), "leaked_v6": n - len(leaked_v4),
        "first_leak_utc": leaked["first_seen"].iloc[0].strftime("%H:%M:%S") if n else None,
        "path_tail": r.path_tails.most_common(3),
        "via_upstream_pct": round(100 * via_up / n, 1) if upstream and n else None,
        "upstream_counts": Counter(u for us in leaked["upstreams"] for u in us.split()).most_common(5),
        "peers_total": len(r.peers_total), "peers_with_leak": len(set().union(*r.peers_ever.values())) if n else 0,
        "victim_ases": len(victim_counts),
        "top_victims": [{"asn": a, "name": names[a], "prefixes": c} for a, c in top],
        "rov_then_day": str(start.date()) if vrps_then else None,
        "rov_then": pct("rov_then", rov_keys) if vrps_then else None,
        "rov_now_day": str(now_day), "rov_now": pct("rov_now", rov_keys),
        "path_check": pct("path_check", path_keys),
        "distinct_leaked_paths": dict(Counter(path_class.values())),
        "max_prefix": max_prefix, "checkpoints": checkpoint_rows,
    }
    summary["rov_then_has_roa_pct"] = round(100 - summary["rov_then"][rpki.NOTFOUND]["pct"], 1) if vrps_then else None
    summary["rov_now_has_roa_pct"] = round(100 - summary["rov_now"][rpki.NOTFOUND]["pct"], 1)
    summary["rov_then_invalid_pct"] = summary["rov_then"][rpki.INVALID]["pct"] if vrps_then else None
    summary["rov_now_invalid_pct"] = summary["rov_now"][rpki.INVALID]["pct"]
    summary["path_valley_pct"] = summary["path_check"][pathcheck.VALLEY]["pct"]
    summary["path_any_valley_pct"] = round(100 * (leaked["paths_with_valley"] > 0).mean(), 1) if n else None
    summary["lingering"] = checkpoint_rows
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    plot_timeline(pd.DataFrame(timeline), inc, out / "timeline.png")
    return summary


def plot_timeline(tl, inc, path):
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(tl["time"], tl["cumulative_leaked"], label="distinct leaked prefixes seen so far", color="#888888")
    ax.plot(tl["time"], tl["active_prefixes"], label="leaked prefixes still routed to the leaker by at least one peer", color="#c0392b")
    ax.set_ylabel("prefixes")
    ax.set_xlabel("time (UTC)")
    ax.set_title(f"{inc['name']} (AS{inc['leaker']})")
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M", tz=UTC))
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def print_report(summary, expected):
    print(f"\n=== {summary['incident']} @ {summary['collector']} ===")
    print(f"{'metric':<22} {'published':<62} reproduced")
    for key, claim in expected.items():
        print(f"{key:<22} {claim[:60]:<62} {summary.get(key)}")
    print("\nROV of leaked routes:")
    for when in ("then", "now"):
        r = summary[f"rov_{when}"]
        if r is None:
            print(f"  {when}: no archived VRP list for that day")
            continue
        print(f"  {when} ({summary[f'rov_{when}_day']}): " + ", ".join(f"{k} {v['count']:,} ({v['pct']}%)" for k, v in r.items()))
    print("Path checks (valley-free test behind ASPA / RFC 9234 / leak detectors), per leaked prefix:")
    print("  every path has a valley (stopped): " + ", ".join(f"{k} {v['count']:,} ({v['pct']}%)" for k, v in summary["path_check"].items()))
    print(f"  at least one path has a valley: {summary['path_any_valley_pct']}%")
    print("\nMax-prefix counterfactual (IPv4 session, baseline", summary["baseline_v4"], "):")
    for k, v in summary["max_prefix"].items():
        print(f"  {k:>4}: limit {v['limit']:>6,} -> " + (f"trips {v['trips_at']}, {v['leaked_before_trip']:,} leaked first, {v['contained_pct']}% contained" if v["trips_at"] else "never trips"))
    print("\nTop victims:", ", ".join(f"AS{v['asn']} {v['name'][:25]} ({v['prefixes']})" for v in summary["top_victims"][:8]))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("incident")
    ap.add_argument("--collectors", nargs="*", help="override the collectors listed in the corpus")
    args = ap.parse_args()
    inc = yaml.safe_load((ROOT / "corpus" / "incidents.yaml").read_text())[args.incident]
    for collector in args.collectors or inc["collectors"]:
        summary = replay(args.incident, inc, collector)
        print_report(summary, inc.get("expected", {}))


if __name__ == "__main__":
    main()
