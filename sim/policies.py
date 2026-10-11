"""BGPy additions: the mass re-origination scenario and the ConeGuard policy.

In BGPy, one scenario run seeds one prefix. ConeGuard's burst detection fires within seconds of a mass
leak (see replay.evaluate), after which it quarantines every route from that customer whose prefix belongs
to a network outside the customer's cone. That steady state is what the policy below models.
"""
from dataclasses import dataclass, replace

from bgpy.shared.enums import Relationships
from bgpy.simulation_engine import ROV, Announcement
from bgpy.simulation_framework import PrefixHijack
from yamlable import yaml_info


@yaml_info(yaml_tag="OwnedAnnouncement")
@dataclass(slots=True, frozen=True)
class OwnedAnn(Announcement):
    """An announcement that also carries the prefix's legitimate origin.

    Stands in for what a provider already knows from its own RIB and registries: who normally
    originates the prefix. It is never used to pick routes, only by ConeGuard's ownership check.
    """

    legit_origin: int | None = None


class MassReorigination(PrefixHijack):
    """The attacker re-originates the victim's prefix as its own, like AS55410 in 2021 (RFC 7908 Type 5)."""

    def _get_announcements(self, *, engine=None):
        anns = super()._get_announcements(engine=engine)
        (victim,) = self.victim_asns
        return tuple(replace(ann, legit_origin=victim) for ann in anns)


class ConeGuard(ROV):
    """ROV plus a customer-cone check on customer sessions: drop routes for prefixes owned outside the cone."""

    name: str = "ConeGuard"
    checked_relationships = (Relationships.CUSTOMERS,)

    def _valid_ann(self, ann, recv_rel):
        if recv_rel in self.checked_relationships and not self._owned_within_sender_cone(ann):
            return False
        return super()._valid_ann(ann, recv_rel)

    def _owned_within_sender_cone(self, ann):
        owner = getattr(ann, "legit_origin", None)
        if owner is None:
            return True
        sender = ann.as_path[0]
        if owner == sender:
            return True
        cone = self.as_.as_graph.as_dict[sender].customer_cone_asns or frozenset()
        return owner in cone


class ConeGuardPeers(ConeGuard):
    """ConeGuard applied to peer sessions as well: a peer should only send routes from its own cone."""

    name: str = "ConeGuard + peers"
    checked_relationships = (Relationships.CUSTOMERS, Relationships.PEERS)
