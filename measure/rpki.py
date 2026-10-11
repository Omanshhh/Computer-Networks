"""Route Origin Validation (RFC 6811) against archived VRPs."""
import csv
import io
import ipaddress
import lzma
from collections import defaultdict

VALID, INVALID, NOTFOUND = "valid", "invalid", "notfound"


def _key(net, plen):
    bits = net.max_prefixlen
    mask = ((1 << bits) - 1) ^ ((1 << (bits - plen)) - 1)
    return net.version, int(net.network_address) & mask, plen


class VRPSet:
    """VRPs indexed by exact prefix, so covering VRPs are found with one lookup per prefix length."""

    def __init__(self):
        self._vrps = defaultdict(set)  # (version, network int, prefixlen) -> {(asn, maxlen)}
        self.count = 0

    @classmethod
    def from_ripe_archive(cls, paths):
        """Load roas.csv.xz files from ftp.ripe.net/rpki (columns: URI, ASN, IP Prefix, Max Length, ...)."""
        vrps = cls()
        for path in paths:
            with lzma.open(path, "rt", encoding="utf-8") as f:
                for row in csv.DictReader(io.StringIO(f.read())):
                    net = ipaddress.ip_network(row["IP Prefix"], strict=False)
                    maxlen = int(row["Max Length"]) if row["Max Length"] else net.prefixlen
                    vrps.add(net, int(row["ASN"].upper().removeprefix("AS")), maxlen)
        return vrps

    def add(self, net, asn, maxlen):
        entry = (asn, maxlen)
        bucket = self._vrps[_key(net, net.prefixlen)]
        if entry not in bucket:
            bucket.add(entry)
            self.count += 1

    def covering(self, prefix):
        net = ipaddress.ip_network(prefix, strict=False)
        for plen in range(net.prefixlen, -1, -1):
            yield from self._vrps.get(_key(net, plen), ())

    def validate(self, prefix, origin):
        """RFC 6811: Valid if a covering VRP matches origin and length, Invalid if covered but none match."""
        plen = ipaddress.ip_network(prefix, strict=False).prefixlen
        covered = False
        for asn, maxlen in self.covering(prefix):
            covered = True
            if asn == origin and asn != 0 and plen <= maxlen:
                return VALID
        return INVALID if covered else NOTFOUND
