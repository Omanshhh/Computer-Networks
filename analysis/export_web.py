"""Export the numbers the website shows into web/public/results.json, and copy the PDFs next to it.

    python -m analysis.export_web
"""
import json
import pathlib
import shutil

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
PUBLIC = ROOT / "web" / "public"

INCIDENTS = [
    ("as55410-2021", "Vodafone Idea", 2021, 55410, "re-origination"),
    ("rostelecom-2020", "Rostelecom", 2020, 12389, "re-origination"),
    ("indosat-2014", "Indosat", 2014, 4761, "re-origination"),
    ("chinatelecom-2010", "China Telecom", 2010, 23724, "re-origination"),
    ("verizon-dqe-2019", "Verizon / DQE", 2019, 396531, "path-preserving"),
]
DEFENCES = [
    ("ROV, RPKI as it was then", "rovThen"), ("ROV, today's RPKI", "rovNow"),
    ("Path checks (ASPA, RFC 9234, leak detectors)", "pathChecks"),
    ("Max-prefix at 2x normal", "maxPrefix2x"), ("Max-prefix at 10x normal", "maxPrefix10x"),
    ("ConeGuard, RPKI now", "coneguard"),
]
CODE = [("measure/fetch.py", "Downloads public data, resuming dropped transfers"),
        ("measure/extract.py", "Replays BGP updates and tracks every leaked route"),
        ("measure/rpki.py", "RPKI origin validation (RFC 6811)"),
        ("measure/pathcheck.py", "Valley-free path checks behind ASPA and RFC 9234"),
        ("guard/engine.py", "The ConeGuard decision engine"),
        ("replay/evaluate.py", "Compares every defence on every incident"),
        ("replay/false_alarms.py", "Counts false alarms on 41 normal days"),
        ("sim/policies.py", "ConeGuard policy for the BGPy simulator"),
        ("lab/demo.py", "Live demo controller and web server")]


def lines(path):
    return sum(1 for line in (ROOT / path).read_text(encoding="utf-8").splitlines() if line.strip())


def main():
    defences = pd.read_csv(RESULTS / "defences.csv")
    incidents = []
    for key, name, year, asn, kind in INCIDENTS:
        s = json.loads((RESULTS / key / "rrc00" / "summary.json").read_text())
        part = defences[defences["incident"] == key].set_index("defence")
        row = {"id": key, "name": name, "year": year, "asn": asn, "kind": kind,
               "leaked": s["leaked_prefixes"], "normal": s["baseline_v4"], "firstLeak": s["first_leak_utc"],
               "victims": s["victim_ases"]}
        for label, field in DEFENCES:
            value = part.loc[label, "stops_pct"] if label in part.index else None
            row[field] = None if value is None or pd.isna(value) else float(value)
        when = part.loc["ConeGuard, RPKI now", "when"]
        row["triggerSeconds"] = int(str(when).split("s")[0].lstrip("+")) if isinstance(when, str) and when.startswith("+") else None
        incidents.append(row)

    tl = pd.read_csv(RESULTS / "as55410-2021" / "rrc00" / "timeline.csv")
    timeline = [{"t": t[11:16], "seen": int(c), "active": int(a)}
                for t, c, a in zip(tl["time"], tl["cumulative_leaked"], tl["active_prefixes"])]

    leaked = pd.read_csv(RESULTS / "as55410-2021" / "rrc00" / "leaked_prefixes.csv", dtype={"upstreams": str}).fillna("")
    ups = leaked["upstreams"].str.split()
    gates = {"airtel": int(ups.apply(lambda u: "9498" in u).sum()), "vodafoneGlobal": int(ups.apply(lambda u: "1273" in u).sum()),
             "onlyVodafoneGlobal": int(ups.apply(lambda u: "1273" in u and "9498" not in u).sum()), "total": len(leaked)}

    fa = json.loads((RESULTS / "false_alarms.json").read_text())
    per_year = lambda pct: round(pct / 100 * 365, 4)
    cg = pd.read_csv(RESULTS / "false_alarms_coneguard.csv")
    false_alarms = {
        "sessions": fa["sessions"], "days": fa["evaluated_days"],
        "strictFilter": per_year(fa["strict_filter"]["session_days_with_rejections_pct"]),
        "maxPrefix2x": per_year(fa["max_prefix"]["2x"]["session_days_pct"]),
        "coneguard": [{"n": int(r.burst_new), "k": int(r.burst_owners), "perYear": per_year(r.session_days_pct)} for r in cg.itertuples()],
    }
    tradeoff = pd.read_csv(RESULTS / "tradeoff.csv")
    tradeoff = [{"n": int(r.burst_new), "worstSeconds": int(r.worst_trigger_s), "perYear": round(r.per_session_per_year, 4)}
                for r in tradeoff[tradeoff.burst_owners == 5].itertuples()]

    sim = pd.read_csv(RESULTS / "sim" / "data.csv")
    sim = sim[(sim.outcome == "ATTACKER_SUCCESS") & (sim.in_adopting_asns == "Any")]
    simulation = {"adoption": sorted({int(round(p * 100)) for p in sim.percent_adopt}), "withRoa": {}, "withoutRoa": {}}
    for label, part in sim.groupby("scenario_config_label"):
        policy, roa = label.split(" | ")
        series = part.sort_values("percent_adopt")
        simulation["withRoa" if "with ROA" in roa else "withoutRoa"][policy] = {
            "value": [round(v, 1) for v in series["value"]], "err": [round(v, 1) for v in series["yerr"]]}

    code = [{"path": p, "what": w, "lines": lines(p)} for p, w in CODE]
    tests = sum(1 for line in (ROOT / "tests" / "test_engine.py").read_text().splitlines() if line.startswith("def test_"))

    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "results.json").write_text(json.dumps({
        "incidents": incidents, "timeline2021": timeline, "gates2021": gates, "falseAlarms": false_alarms,
        "tradeoff": tradeoff, "simulation": simulation, "code": code, "tests": tests}, indent=1))
    # The paper and report are not in the repository; copy them only when they exist locally.
    files = PUBLIC / "files"
    files.mkdir(exist_ok=True)
    copied = []
    for src, name in ((ROOT / "paper" / "coneguard.pdf", "coneguard-paper.pdf"), (ROOT / "report" / "report.pdf", "coneguard-report.pdf")):
        if src.exists():
            shutil.copy(src, files / name)
            copied.append(name)
    print(f"wrote {PUBLIC / 'results.json'}; copied {', '.join(copied) or 'no PDFs'}")


if __name__ == "__main__":
    main()
