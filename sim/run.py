"""Internet-wide simulation: how much of a mass re-origination leak each defence stops as adoption grows.

Uses BGPy on CAIDA's current AS topology. Each trial picks a random transit AS as the leaker and a
random edge AS as the victim; the metric is the share of ASes whose traffic ends up at the leaker.
Runs every defence twice: victim with an RPKI ROA (like ~23% of the 2021 leak) and without one.

    python -m sim.run --trials 100 --cpus 8
"""
import argparse
import pathlib

from bgpy.shared.enums import ASGroups, InAdoptingASNs, Outcomes, Plane
from bgpy.simulation_engine import ASPA, BGP, ROV, OnlyToCustomers, PeerlockLite
from bgpy.simulation_framework import ScenarioConfig, Simulation
from bgpy.simulation_framework.graph_data_aggregator.graph_category import GraphCategory
from frozendict import frozendict

from .policies import ConeGuard, ConeGuardPeers, MassReorigination, OwnedAnn

ROOT = pathlib.Path(__file__).resolve().parent.parent
POLICIES = [ROV, ASPA, OnlyToCustomers, PeerlockLite, ConeGuard, ConeGuardPeers]
ADOPTION = (0.1, 0.2, 0.5, 0.8, 0.99)


def scenario_configs():
    configs = []
    for with_roa in (True, False):
        for Policy in POLICIES:
            label = f"{Policy.name} | victim {'with' if with_roa else 'without'} ROA"
            configs.append(ScenarioConfig(
                ScenarioCls=MassReorigination,
                AnnCls=OwnedAnn,
                AdoptPolicyCls=Policy,
                BasePolicyCls=BGP,
                attacker_subcategory_attr=ASGroups.TRANSIT.value,
                override_roas=None if with_roa else (),
                csv_label=label,
                scenario_label=label,
            ))
    return tuple(configs)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trials", type=int, default=100)
    ap.add_argument("--cpus", type=int, default=8)
    ap.add_argument("--adoption", type=float, nargs="+", default=list(ADOPTION), help="fractions of ASes that deploy")
    ap.add_argument("--out", default=str(ROOT / "results" / "sim"))
    args = ap.parse_args()

    categories = tuple(
        GraphCategory(plane=Plane.DATA, as_group=ASGroups.ALL_WOUT_IXPS, outcome=o, in_adopting_asns=InAdoptingASNs.ANY)
        for o in (Outcomes.ATTACKER_SUCCESS, Outcomes.VICTIM_SUCCESS, Outcomes.DISCONNECTED)
    )
    sim = Simulation(
        sim_name="mass_reorigination",
        percent_adoptions=tuple(args.adoption),
        scenario_configs=scenario_configs(),
        num_trials=args.trials,
        parse_cpus=args.cpus,
        output_dir=pathlib.Path(args.out),
        graph_categories=categories,
        as_graph_constructor_kwargs=frozendict({
            "as_graph_collector_kwargs": frozendict({}),
            "as_graph_kwargs": frozendict({
                "store_customer_cone_size": True,
                "store_customer_cone_asns": True,  # ConeGuard needs each AS's customer cone
                "store_provider_cone_size": False,
                "store_provider_cone_asns": False,
            }),
            "tsv_path": None,
        }),
    )
    sim.run(GraphFactoryCls=None)
    print(f"wrote {sim.csv_path}")


if __name__ == "__main__":
    main()
