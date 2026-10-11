import ipaddress

from guard.engine import ACCEPT, ALERT, QUARANTINE, REJECT, Config, ConeGuard
from measure import rpki

CUSTOMER = 64500
OWNERS = {f"10.{i}.0.0/16": {65000 + i % 10} for i in range(100)}  # space owned by 10 other networks


def make_guard(vrps=None, **cfg):
    return ConeGuard(CUSTOMER, cone={CUSTOMER, 64501}, expected={"192.0.2.0/24"},
                     vrps=vrps, owners=lambda p: OWNERS.get(p, set()), config=Config(**cfg))


def test_expected_prefix_is_accepted():
    assert make_guard().announce(0, "192.0.2.0/24", CUSTOMER).action == ACCEPT


def test_rpki_invalid_is_rejected():
    vrps = rpki.VRPSet()
    vrps.add(ipaddress.ip_network("198.51.100.0/24"), 65010, 24)
    assert make_guard(vrps).announce(0, "198.51.100.0/24", CUSTOMER).action == REJECT


def test_rpki_valid_in_cone_is_learned():
    vrps = rpki.VRPSet()
    vrps.add(ipaddress.ip_network("203.0.113.0/24"), 64501, 24)
    g = make_guard(vrps)
    assert g.announce(0, "203.0.113.0/24", 64501).action == ACCEPT
    assert "203.0.113.0/24" in g.expected


def test_single_foreign_prefix_only_alerts():
    assert make_guard().announce(0, "10.0.0.0/16", CUSTOMER).action == ALERT


def test_new_unowned_prefix_is_accepted():
    assert make_guard().announce(0, "100.64.0.0/24", CUSTOMER).action == ACCEPT


def test_mass_leak_triggers_burst_and_quarantines_retroactively():
    g = make_guard(burst_new=25, burst_owners=5)
    actions = [g.announce(t, f"10.{t}.0.0/16", CUSTOMER) for t in range(30)]
    assert all(d.action == ALERT for d in actions[:24])
    assert actions[24].action == QUARANTINE and actions[24].reason == "burst-detected"
    assert len(actions[24].retro) == 24  # the 24 alerted prefixes are pulled back
    assert all(d.action == QUARANTINE for d in actions[25:])
    # the customer's own routes keep flowing during the burst
    assert g.announce(31, "192.0.2.0/24", CUSTOMER).action == ACCEPT


def test_burst_needs_many_owners():
    g = make_guard(burst_new=25, burst_owners=5)
    OWNERS_ONE = {f"10.{i}.0.0/16" for i in range(0, 100, 10)}  # all owned by AS65000
    for t, p in enumerate(sorted(OWNERS_ONE) * 3):
        d = g.announce(t, p, CUSTOMER)
    assert d.action == ALERT  # 30 announcements but only one owner: a migration, not a mass leak


def test_rpki_invalid_routes_count_toward_a_burst():
    vrps = rpki.VRPSet()
    for i in range(20):
        vrps.add(ipaddress.ip_network(f"10.{i}.0.0/16"), 65000 + i % 10, 16)
    g = make_guard(vrps, burst_new=25, burst_owners=5)
    actions = [g.announce(t, f"10.{t}.0.0/16", CUSTOMER) for t in range(30)]
    assert all(d.action == REJECT for d in actions[:20])  # signed space: rejected by ROV
    assert actions[24].reason == "burst-detected"          # 20 invalid + 5 unsigned complete the burst
    assert len(actions[24].retro) == 4                     # only the alerted (exported) ones are pulled back
    assert all(d.action == QUARANTINE for d in actions[25:])


def test_burst_ends_after_calm_period():
    g = make_guard(burst_new=5, burst_owners=2, calm_s=100)
    for t in range(5):
        g.announce(t, f"10.{t}.0.0/16", CUSTOMER)
    assert g.announce(5, "10.5.0.0/16", CUSTOMER).action == QUARANTINE
    assert g.announce(1000, "10.6.0.0/16", CUSTOMER).action == ALERT
