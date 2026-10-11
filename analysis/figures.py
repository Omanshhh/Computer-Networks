"""Paper figures from the results/ folder. Writes PNG (300 dpi) and PDF to paper/figures/.

    python -m analysis.figures
"""
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
OUT = ROOT / "paper" / "figures"

# Reference palette (validated with the dataviz validator, light mode): categorical slots in fixed order.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
QUIET = "#c3c2b7"
INCIDENTS = [("as55410-2021", "Vodafone Idea 2021"), ("rostelecom-2020", "Rostelecom 2020"),
             ("indosat-2014", "Indosat 2014"), ("chinatelecom-2010", "China Telecom 2010"),
             ("verizon-dqe-2019", "Verizon/DQE 2019\n(path-preserving)")]

plt.rcParams.update({
    "font.family": ["Segoe UI", "Arial", "DejaVu Sans"], "font.size": 7.5, "axes.edgecolor": AXIS,
    "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED, "axes.titlesize": 8,
    "axes.titleweight": "bold", "axes.titlecolor": INK, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": "white", "axes.facecolor": "white", "legend.frameon": False, "text.color": INK,
})


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.png", dpi=300, bbox_inches="tight")
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


def timeline():
    tl = pd.read_csv(RESULTS / "as55410-2021" / "rrc00" / "timeline.csv")
    tl["time"] = pd.to_datetime(tl["time"], utc=True)
    fig, ax = plt.subplots(figsize=(3.45, 2.1))
    ax.plot(tl["time"], tl["cumulative_leaked"] / 1000, color=SERIES[1], lw=2)
    ax.plot(tl["time"], tl["active_prefixes"] / 1000, color=SERIES[0], lw=2)
    last = tl.iloc[-1]
    ax.annotate("distinct leaked prefixes seen", (last["time"], last["cumulative_leaked"] / 1000), xytext=(-4, -10),
                textcoords="offset points", ha="right", color=INK2, fontsize=7)
    ax.annotate("still routed to AS55410\nby at least one peer", (last["time"], last["active_prefixes"] / 1000),
                xytext=(-4, 5), textcoords="offset points", ha="right", color=INK2, fontsize=7)
    start = pd.Timestamp("2021-04-16 13:48:58", tz="UTC")
    ax.axvline(start, color=MUTED, lw=0.8)
    ax.annotate("13:48:58 first leaked route;\nConeGuard contains it 1 s later",
                xy=(start, 22), xytext=(pd.Timestamp("2021-04-16 14:10", tz="UTC"), 22), fontsize=7, color=INK2,
                va="center", arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.8})
    ax.set_ylabel("prefixes (thousands)")
    ax.set_xlabel("16 April 2021 (UTC), RIPE RIS rrc00")
    ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=[0, 30], tz="UTC"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz="UTC"))
    ax.set_ylim(0, 37)
    ax.set_xlim(tl["time"].iloc[0], tl["time"].iloc[-1])
    save(fig, "fig_timeline_as55410")


def rov_then_now():
    rows = []
    for key, label in INCIDENTS:
        s = json.loads((RESULTS / key / "rrc00" / "summary.json").read_text())
        rows.append((label.replace("\n", " "), s["rov_then_invalid_pct"], s["rov_now_invalid_pct"]))
    fig, ax = plt.subplots(figsize=(3.45, 2.3))
    for i, (label, then, now) in enumerate(rows):
        y = len(rows) - 1 - i
        if then is not None:
            ax.plot([then, now], [y, y], color=QUIET, lw=2, zorder=1)
            ax.scatter([then], [y], s=42, color=SERIES[1], zorder=2, edgecolor="white", linewidth=1.5)
            ax.text(then - 2, y + 0.18, f"{then:.0f}%", ha="right", fontsize=8, color=INK2)
        else:
            ax.text(1, y + 0.18, "no RPKI archive", fontsize=8, color=MUTED)
        ax.scatter([now], [y], s=42, color=SERIES[0], zorder=2, edgecolor="white", linewidth=1.5, marker="D")
        ax.text(now + 2, y + 0.18, f"{now:.0f}%", fontsize=8, color=INK2)
    ax.set_yticks(range(len(rows)), [r[0].replace(" (path-preserving)", "*") for r in reversed(rows)])
    ax.set_xlim(0, 100)
    ax.set_xlabel("leaked prefixes ROV would drop (%)    * path-preserving")
    ax.scatter([], [], color=SERIES[1], s=42, label="RPKI on the day of the incident")
    ax.scatter([], [], color=SERIES[0], s=42, marker="D", label="RPKI today (11 Oct 2026)")
    ax.legend(loc="lower right", fontsize=6.5)
    ax.grid(axis="y", visible=False)
    save(fig, "fig_rov_then_now")


def defences():
    table = pd.read_csv(RESULTS / "defences.csv")
    names = [("ROV, RPKI as it was then", "ROV (RPKI then)"), ("ROV, today's RPKI", "ROV (RPKI today)"),
             ("Path checks (ASPA, RFC 9234, leak detectors)", "Path checks (ASPA, OTC)"),
             ("Max-prefix at 2x normal", "Max-prefix 2x *"), ("Max-prefix at 10x normal", "Max-prefix 10x *"),
             ("ConeGuard, RPKI now", "ConeGuard")]
    fig, axes = plt.subplots(1, len(INCIDENTS), figsize=(7.2, 2.6), sharey=True)
    for ax, (key, label) in zip(axes, INCIDENTS):
        part = table[table["incident"] == key].set_index("defence")
        values = [float(part.loc[n, "stops_pct"]) if n in part.index and pd.notna(part.loc[n, "stops_pct"]) else None
                  for n, _ in names]
        for i, v in enumerate(values):
            y = len(names) - 1 - i
            color = SERIES[0] if names[i][1] == "ConeGuard" else QUIET
            if v is None:
                ax.text(2, y, "n/a", va="center", fontsize=7.5, color=MUTED)
                continue
            ax.barh(y, v, height=0.62, color=color)
            ax.text(min(v, 100) + 3 if v < 70 else v - 3, y, f"{v:.0f}", va="center",
                    ha="left" if v < 70 else "right", fontsize=7.5, color=INK if v < 70 or color == QUIET else "white")
        ax.set_title(label, fontsize=8.5)
        ax.set_xlim(0, 100)
        ax.set_xticks([0, 50, 100])
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(range(len(names)), [n[1] for n in reversed(names)])
    fig.supxlabel("leaked prefixes stopped (%)   * tears down the session: the customer's own routes are lost too",
                  fontsize=8, color=INK2)
    fig.tight_layout(w_pad=0.6)
    save(fig, "fig_defences")


def false_alarms():
    fa = json.loads((RESULTS / "false_alarms.json").read_text())
    cg = pd.read_csv(RESULTS / "false_alarms_coneguard.csv")
    per_year = lambda pct: pct / 100 * 365  # session-days with an event -> days per session-year

    def cg_rate(bn, bo):
        return per_year(cg[(cg.burst_new == bn) & (cg.burst_owners == bo)]["session_days_pct"].iloc[0])

    bars = [("Strict filter\n(legit routes rejected)", per_year(fa["strict_filter"]["session_days_with_rejections_pct"])),
            ("Max-prefix 2x\n(session torn down)", per_year(fa["max_prefix"]["2x"]["session_days_pct"])),
            ("ConeGuard N=25\n(new foreign held)", cg_rate(25, 5)),
            ("ConeGuard N=50", cg_rate(50, 5)),
            ("ConeGuard N=100", cg_rate(100, 5))]
    fig, ax = plt.subplots(figsize=(3.45, 2.4))
    for i, (label, v) in enumerate(bars):
        y = len(bars) - 1 - i
        ax.barh(y, v, height=0.6, color=SERIES[0] if label.startswith("ConeGuard") else QUIET)
        ax.text(v * 1.2, y, f"{v:.3g}", va="center", fontsize=7, color=INK2)
    ax.set_xscale("log")
    ax.set_xlim(5e-4, 30)
    ax.set_yticks(range(len(bars)), [b[0] for b in reversed(bars)], fontsize=7)
    ax.set_xlabel(f"false-alarm days per session-year (log)\n"
                  f"{fa['sessions']:,} sessions x {fa['evaluated_days']} normal days", fontsize=7)
    ax.grid(axis="y", visible=False)
    save(fig, "fig_false_alarms")


def tradeoff():
    t = pd.read_csv(RESULTS / "tradeoff.csv")
    t = t[t.burst_owners == 5].sort_values("burst_new")
    fig, ax = plt.subplots(figsize=(3.45, 2.2))
    ax.plot(t["per_session_per_year"], t["worst_trigger_s"], color=SERIES[0], lw=2, marker="o", ms=6,
            markeredgecolor="white", markeredgewidth=1.5)
    # settings that land on the same point share one label (e.g. 100 and 250)
    for (x, y), group in t.groupby([t["per_session_per_year"].round(2), "worst_trigger_s"], sort=False):
        label = " and ".join(str(b) for b in group["burst_new"])
        ax.annotate(label, (group["per_session_per_year"].iloc[0], y), xytext=(6, 4),
                    textcoords="offset points", fontsize=7, color=INK2)
    ax.set_xlabel("false alarms per customer session per year")
    ax.set_ylabel("slowest reaction across\nthe five incidents (s)")
    ax.set_title("Burst threshold N (K = 5 owners)", fontsize=8, loc="left")
    save(fig, "fig_tradeoff")


def simulation():
    path = RESULTS / "sim" / "data.csv"
    if not path.exists():
        print("skip simulation figure: results/sim/data.csv not found")
        return
    d = pd.read_csv(path)
    d = d[(d.outcome == "ATTACKER_SUCCESS") & (d.in_adopting_asns == "Any")]
    d["policy"] = d["scenario_config_label"].str.split(" | ", regex=False).str[0]
    d["roa"] = d["scenario_config_label"].str.contains("with ROA")
    names = {"ROV": "ROV", "ASPA": "ASPA", "OnlyToCustomers": "RFC 9234 OTC", "Peerlock Lite": "Peerlock-lite",
             "ConeGuard": "ConeGuard", "ConeGuard + peers": "ConeGuard + peers"}
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.2), sharey=True)
    for ax, roa in zip(axes, (False, True)):
        part = d[d.roa == roa]
        series = {p: s.sort_values("percent_adopt") for p, s in part.groupby("policy")}
        baseline = max(s["value"].max() for s in series.values())
        # defences with identical results are drawn once, under one label
        groups = {}
        for policy in names:
            if policy in series:
                key = tuple(series[policy]["value"].round(1))
                groups.setdefault(key, []).append(policy)
        for key, members in groups.items():
            s = series[members[0]]
            no_effect = all(abs(v - baseline) < 0.05 for v in key)
            color = QUIET if no_effect else SERIES[0] if members == ["ConeGuard"] else \
                SERIES[1] if members == ["ConeGuard + peers"] else SERIES[2]
            label = ", ".join(names[m] for m in members) + (" (no effect)" if no_effect else "")
            ax.errorbar(s["percent_adopt"] * 100, s["value"], yerr=s["yerr"], color=color, marker="o", ms=5, lw=2,
                        elinewidth=0.8, capsize=2, markeredgecolor="white", markeredgewidth=1, label=label,
                        zorder=1 if no_effect else 2)
        ax.set_title("Victim without an RPKI ROA (77% of the 2021 leak)" if not roa else "Victim with an RPKI ROA",
                     fontsize=8, loc="left")
        ax.set_xlabel("ASes deploying the defence (%)")
        ax.set_xlim(0, 103)
        ax.legend(fontsize=6.5, loc="upper left", bbox_to_anchor=(0, -0.26), ncol=1)
    axes[0].set_ylabel("ASes whose traffic\nreaches the leaker (%)")
    axes[0].set_ylim(0, 90)
    fig.tight_layout()
    save(fig, "fig_simulation")


if __name__ == "__main__":
    timeline()
    rov_then_now()
    defences()
    false_alarms()
    tradeoff()
    simulation()
