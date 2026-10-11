"""Replay BGP update dumps and track what a leaking AS announced and who carried it.

The replay keeps, for every (collector peer, prefix), whether that peer's current best route
goes via the leaker. That gives the leaked prefix set, how far it spread, which upstream
carried it, and how long it lingered.

Two kinds of leak are supported:
  role="origin"   the leaker re-originates other networks' prefixes (AS55410 2021): it is the path's origin
  role="transit"  the leaker passes on routes with the real origin kept (Verizon/DQE 2019): it is mid-path
"""
import gzip
import ipaddress
from collections import Counter, defaultdict


FIELDS = ["timestamp", "elem_type", "peer_ip", "peer_asn", "prefix", "as_path"]


def parse_path(as_path):
    """AS_PATH string -> (ASNs with prepends collapsed, origin ASN or None if the path ends in an AS_SET)."""
    if not as_path:
        return [], None
    tokens = as_path.split()
    path = []
    for tok in tokens:
        if tok.isdigit() and (not path or path[-1] != int(tok)):
            path.append(int(tok))
    origin = int(tokens[-1]) if tokens[-1].isdigit() else None
    return path, origin


def iter_updates(paths, batch_size=50_000):
    from pybgpkit_parser import Parser  # imported here so the rest of the module needs only the stdlib

    for path in paths:
        for batch in Parser(url=str(path)).iter_tuple_batches(FIELDS, batch_size=batch_size):
            yield from batch


class LeakReplay:
    def __init__(self, leaker, baseline, role="origin"):
        assert role in ("origin", "transit")
        self.leaker = leaker
        self.role = role
        self.baseline = set(baseline)       # prefixes the leaker legitimately originates
        self.first_seen = {}                # leaked prefix -> first announcement time
        self.peers_ever = defaultdict(set)  # leaked prefix -> peers that ever routed it to the leaker
        self.upstream_ever = defaultdict(set)  # leaked prefix -> ASNs seen directly before the leaker
        self.path_tails = Counter()         # raw AS_PATH endings, e.g. "9498 55410 55410 55410"
        self.origins = defaultdict(Counter)  # leaked prefix -> origin ASes on its leaked routes
        self.prefix_paths = defaultdict(set)  # leaked prefix -> distinct leaked AS paths (prepends collapsed)
        self.holding = {}                   # (peer, prefix) -> upstream, for routes currently via the leaker
        self.peers_per_prefix = Counter()   # leaked prefix -> peers currently holding it
        self.prefixes_per_peer = Counter()  # peer -> leaked prefixes it currently holds
        self.peers_total = set()
        self.updates = 0
        self._token = str(leaker)
        self._suffix = f" {leaker}"

    def _via_leaker(self, as_path):
        if as_path is None or self._token not in as_path:
            return False
        originated = as_path.endswith(self._suffix) or as_path == self._token
        if self.role == "origin":
            return originated
        return not originated and f" {self._token} " in f" {as_path} "

    def _release(self, key):
        if self.holding.pop(key, False) is not False:
            peer, prefix = key
            self._dec(self.peers_per_prefix, prefix)
            self._dec(self.prefixes_per_peer, peer)

    @staticmethod
    def _dec(counter, k):
        counter[k] -= 1
        if not counter[k]:
            del counter[k]

    def feed(self, ts, elem_type, peer_ip, peer_asn, prefix, as_path):
        self.updates += 1
        self.peers_total.add(peer_ip)
        by_leaker = self._via_leaker(as_path)
        if prefix not in self.first_seen and not by_leaker:
            return  # this prefix has never been routed to the leaker: nothing to track
        key = (peer_ip, prefix)
        if elem_type.upper().startswith("W") or not by_leaker or prefix in self.baseline:
            self._release(key)
            return
        path, _ = parse_path(as_path)
        i = path.index(self.leaker)
        upstream = path[i - 1] if i > 0 else None  # None: the collector peer is the leaker itself
        if key not in self.holding:
            self.peers_per_prefix[prefix] += 1
            self.prefixes_per_peer[peer_ip] += 1
        self.holding[key] = upstream
        self.first_seen.setdefault(prefix, ts)
        self.peers_ever[prefix].add(peer_ip)
        self.upstream_ever[prefix].add(upstream)
        self.origins[prefix][path[-1]] += 1
        self.prefix_paths[prefix].add(tuple(path))
        self.path_tails[" ".join(as_path.split()[-4:])] += 1

    def counts(self):
        return {"active_prefixes": len(self.peers_per_prefix), "active_pairs": len(self.holding),
                "active_peers": len(self.prefixes_per_peer), "cumulative_leaked": len(self.first_seen)}

    def snapshot(self):
        via = defaultdict(set)
        for (peer, prefix), upstream in self.holding.items():
            via[upstream].add(prefix)
        return {**self.counts(), "active_via": {up: len(p) for up, p in via.items()},
                "active_prefix_set": set(self.peers_per_prefix)}

    def run(self, paths, checkpoints=(), on_minute=None):
        """Replay all files; return snapshots at each checkpoint time (epoch seconds)."""
        pending = sorted(checkpoints)
        snaps = {}
        minute = None
        for ts, elem_type, peer_ip, peer_asn, prefix, as_path in iter_updates(paths):
            while pending and ts >= pending[0]:
                snaps[pending.pop(0)] = self.snapshot()
            m = int(ts // 60)
            if on_minute and m != minute:
                if minute is not None:
                    on_minute(minute * 60, self)
                minute = m
            self.feed(ts, elem_type, peer_ip, peer_asn, prefix, as_path)
        for t in pending:
            snaps[t] = self.snapshot()
        return snaps


def load_pfx2as(path):
    """CAIDA prefix2as: 'addr<TAB>len<TAB>asns' where asns may be '1_2' (MOAS) or '1,2' (AS set)."""
    table = {}
    with gzip.open(path, "rt") as f:
        for line in f:
            addr, plen, asns = line.split()
            table[f"{addr}/{plen}"] = {int(a) for a in asns.replace(",", "_").split("_") if a.isdigit()}
    return table


def legit_origins(prefix, pfx2as):
    """Origin ASes for the prefix, falling back to the most specific covering prefix."""
    if prefix in pfx2as:
        return pfx2as[prefix]
    net = ipaddress.ip_network(prefix, strict=False)
    for plen in range(net.prefixlen - 1, 7, -1):
        covering = str(net.supernet(new_prefix=plen))
        if covering in pfx2as:
            return pfx2as[covering]
    return set()
