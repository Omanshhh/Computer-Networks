"""Sensitivity sweep: ConeGuard's containment and reaction time on real incidents vs. its false-alarm rate.

Needs results/<incident>/<collector>/ (measure.replay_incident) and results/false_alarms_coneguard.csv
(replay.false_alarms).

    python -m replay.tradeoff
"""
import datetime as dt
import pathlib

import pandas as pd
import yaml

from guard.engine import Config
from measure import extract, fetch, rpki

from .evaluate import load, run_guard, utc

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main(collector="rrc00"):
    corpus = yaml.safe_load((ROOT / "corpus" / "incidents.yaml").read_text())
    alarms = pd.read_csv(ROOT / "results" / "false_alarms_coneguard.csv")
    ids = [i for i in corpus if (ROOT / "results" / i / collector / "summary.json").exists()]
    rows = []
    vrps_now = None
    for incident_id in ids:
        inc = corpus[incident_id]
        leaked, s = load(incident_id, collector)
        day = utc(inc["start"]).date()
        leaker = inc["leaker"]
        expected = fetch.announced_prefixes(leaker, *(utc(t).replace(tzinfo=None) for t in inc["baseline"]))
        pfx2as = extract.load_pfx2as(fetch.pfx2as(day))
        cone = fetch.customer_cone(leaker, day)
        if vrps_now is None:
            vrps_now = rpki.VRPSet.from_ripe_archive(fetch.vrps(dt.date.fromisoformat(s["rov_now_day"])))

        def owners(prefix, pfx2as=pfx2as, leaker=leaker):
            return extract.legit_origins(prefix, pfx2as) - {leaker}

        for a in alarms.itertuples():
            g = run_guard(inc, leaked, expected, vrps_now, owners, cone,
                          Config(burst_new=a.burst_new, burst_owners=a.burst_owners))
            rows.append({"incident": incident_id, "burst_new": a.burst_new, "burst_owners": a.burst_owners, **g})
        print(f"{incident_id}: {len(alarms)} settings")

    per_incident = pd.DataFrame(rows)
    per_incident.to_csv(ROOT / "results" / "tradeoff_per_incident.csv", index=False)
    summary = (per_incident.groupby(["burst_new", "burst_owners"])
               .agg(min_contained_pct=("contained_pct", "min"), mean_contained_pct=("contained_pct", "mean"),
                    worst_trigger_s=("trigger_after_s", "max"), never_triggered=("trigger_after_s", lambda s: s.isna().sum()))
               .reset_index()
               .merge(alarms, on=["burst_new", "burst_owners"]))
    summary.to_csv(ROOT / "results" / "tradeoff.csv", index=False)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
