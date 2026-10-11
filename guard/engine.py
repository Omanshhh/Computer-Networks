"""ConeGuard: a provider-side guard for one customer BGP session.

Max-prefix tears the whole session down when a customer floods it, cutting the customer's genuine
routes too. A strict prefix filter needs an up-to-date list of everything the customer may announce,
and rejects legitimate new announcements when that list is stale. ConeGuard sits between the two:

  1. RPKI-invalid routes are rejected (standard route origin validation).
  2. Routes the session normally carries (the expected set) are accepted.
  3. A new prefix that a network outside the customer's cone currently owns is "foreign". On its own it
     is accepted with an alert, since migrations and DDoS-protection services do this legitimately.
  4. Many foreign prefixes from many different owners within a short window is a mass leak: the session
     enters burst mode, and every unexpected prefix is quarantined (kept out of export), including the
     ones alerted during the window that triggered it. Expected prefixes keep flowing throughout.
"""
from collections import deque
from dataclasses import dataclass, field

from measure import rpki

ACCEPT, ALERT, QUARANTINE, REJECT = "accept", "alert", "quarantine", "reject"
BLOCKED = (QUARANTINE, REJECT)


@dataclass
class Config:
    window_s: int = 300        # sliding window for burst detection
    burst_new: int = 25        # foreign prefixes in the window that start a burst ...
    burst_owners: int = 5      # ... coming from at least this many distinct owners
    calm_s: int = 1800         # burst mode ends after this long without a new foreign prefix


@dataclass
class Decision:
    action: str
    reason: str
    retro: list = field(default_factory=list)  # earlier alerted prefixes quarantined by this decision


class ConeGuard:
    def __init__(self, customer, cone, expected, vrps, owners, config=None):
        """
        customer  ASN of the customer on this session
        cone      ASNs in the customer's customer cone (including itself)
        expected  prefixes this session normally carries
        vrps      rpki.VRPSet, or None to skip origin validation
        owners    function prefix -> set of ASNs that originate it elsewhere (the provider's own RIB)
        """
        self.customer = customer
        self.cone = set(cone) | {customer}
        self.expected = set(expected)
        self.vrps = vrps
        self.owners = owners
        self.cfg = config or Config()
        self.window = deque()      # (time, prefix, owners) of recent foreign announcements
        self.burst_since = None
        self.last_foreign = None
        self.status = {}           # prefix -> current action, for prefixes outside the expected set

    def announce(self, ts, prefix, origin):
        others = self.owners(prefix) - self.cone
        if self.vrps is not None:
            rov = self.vrps.validate(prefix, origin)
            if rov == rpki.INVALID:
                # Rejected either way, but an RPKI-invalid origination is also evidence of a mass leak.
                _, retro = self._record_foreign(ts, prefix, others or {origin})
                return self._set(prefix, Decision(REJECT, "rpki-invalid", retro))
            if rov == rpki.VALID and origin in self.cone:
                self.expected.add(prefix)
                return Decision(ACCEPT, "rpki-valid-in-cone")
        if prefix in self.expected:
            return Decision(ACCEPT, "expected")

        if not others and origin in self.cone:
            if self._in_burst(ts):
                return self._set(prefix, Decision(QUARANTINE, "unexpected-during-burst"))
            return self._set(prefix, Decision(ACCEPT, "new-unowned"))

        was_in_burst, retro = self._record_foreign(ts, prefix, others or {origin})
        if was_in_burst:
            return self._set(prefix, Decision(QUARANTINE, "foreign-during-burst"))
        if self.burst_since == ts:
            return self._set(prefix, Decision(QUARANTINE, "burst-detected", retro))
        return self._set(prefix, Decision(ALERT, "foreign"))

    def _record_foreign(self, ts, prefix, owners):
        """Add a foreign announcement to the window; enter burst mode if it completes a burst.

        Returns (whether the session was already in burst mode, prefixes pulled back by a new burst).
        """
        was_in_burst = self._in_burst(ts)
        self.last_foreign = ts
        self.window.append((ts, prefix, frozenset(owners)))
        while self.window and self.window[0][0] < ts - self.cfg.window_s:
            self.window.popleft()
        if was_in_burst or not self._burst_detected():
            return was_in_burst, []
        self.burst_since = ts
        retro = [p for _, p, _ in self.window if self.status.get(p) == ALERT]
        for p in retro:
            self.status[p] = QUARANTINE
        return False, retro

    def withdraw(self, ts, prefix):
        self.status.pop(prefix, None)

    def _set(self, prefix, decision):
        self.status[prefix] = decision.action
        return decision

    def _burst_detected(self):
        if len(self.window) < self.cfg.burst_new:
            return False
        owners = set()
        for _, _, o in self.window:
            owners |= o
            if len(owners) >= self.cfg.burst_owners:
                return True
        return False

    def _in_burst(self, ts):
        if self.burst_since is None:
            return False
        if self.last_foreign is not None and ts - self.last_foreign > self.cfg.calm_s:
            self.burst_since = None
            return False
        return True
