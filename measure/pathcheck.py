"""Valley-free path checks: the test that ASPA, RFC 9234 roles and route-leak detectors build on.

A route may travel up (customer to provider) any number of hops, cross at most one peer link,
then only travel down (provider to customer). A path that goes down and then up again, or crosses
two peer links, has a "valley": the signature of a path-preserving route leak.
"""
import bz2

P2C, C2P, P2P = "p2c", "c2p", "p2p"
VALLEY_FREE, VALLEY, UNKNOWN = "valley-free", "valley", "unknown"


class Relationships:
    """CAIDA AS relationships (serial-1): 'a|b|-1' means a is b's provider, 'a|b|0' means peers."""

    def __init__(self):
        self._rel = {}

    @classmethod
    def from_caida(cls, path):
        rels = cls()
        with bz2.open(path, "rt") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                a, b, rel = line.strip().split("|")[:3]
                a, b = int(a), int(b)
                if rel == "-1":
                    rels._rel[(a, b)], rels._rel[(b, a)] = P2C, C2P
                else:
                    rels._rel[(a, b)] = rels._rel[(b, a)] = P2P
        return rels

    def rel(self, a, b):
        """Relationship of a to b: P2C if a is b's provider, C2P if a is b's customer, P2P if peers."""
        return self._rel.get((a, b))

    def __len__(self):
        return len(self._rel) // 2


def classify(path, rels):
    """Classify a collector-observed path [peer, ..., origin] with prepends already collapsed.

    Walks from the origin outward. A link with no known relationship is skipped, so a path is
    VALLEY only on positive evidence, and UNKNOWN when it is valley-free on the links we know.
    """
    going_down = False
    unknown = False
    for i in range(len(path) - 1, 0, -1):
        sender, receiver = path[i], path[i - 1]
        r = rels.rel(sender, receiver)
        if r is None:
            unknown = True
        elif r == C2P:  # sent up to a provider
            if going_down:
                return VALLEY
        elif r == P2P:  # sent across to a peer
            if going_down:
                return VALLEY
            going_down = True
        else:  # sent down to a customer
            going_down = True
    return UNKNOWN if unknown else VALLEY_FREE
