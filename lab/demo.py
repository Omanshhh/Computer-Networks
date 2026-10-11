"""Live demo: replay the 2021 Vodafone Idea leak on the containerlab network and switch defences on Airtel.

Run inside WSL after `containerlab deploy -t coneguard.clab.yml`:
    python3 lab/demo.py            then open http://localhost:8080

Modes (Airtel's protection on its Vodafone session):
  none        no protection, as in April 2021
  rov         route origin validation with the RPKI as it was on 16 April 2021
  maxprefix   tear the session down above 2x Vodafone's normal prefix count
  coneguard   ConeGuard: RPKI + quarantine of foreign prefixes once a mass leak is detected
Uses only the Python standard library, so it runs on WSL's system Python.
"""
import csv
import glob
import http.server
import json
import pathlib
import socketserver
import subprocess
import sys
import threading
import time
from collections import deque

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from guard.engine import ALERT, BLOCKED, Config, ConeGuard  # noqa: E402
from measure import extract, rpki  # noqa: E402

LAB = "clab-coneguard"
VODAFONE, AIRTEL = 55410, 9498
VODAFONE_NEIGHBOR = "10.0.1.1"
VODAFONE_OWN = 8                      # prefixes Vodafone originates in the lab
MAX_PREFIX = 2 * VODAFONE_OWN
TARGETS = {"Google": "172.217.179.10", "Fastly": "167.82.163.10", "Vodafone": "118.185.0.10"}
VICTIM_PREFIXES = ("172.217.179.0/24", "167.82.163.0/24")
LEAK_SIZE, LEAK_RATE = 3000, 300      # first 3,000 prefixes of the real leak, 300 per second
PAGE = pathlib.Path(__file__).with_name("dashboard.html")  # fallback when the React site isn't built
SITE = ROOT / "web" / "dist"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
         ".json": "application/json", ".woff2": "font/woff2", ".woff": "font/woff", ".svg": "image/svg+xml",
         ".pdf": "application/pdf", ".png": "image/png", ".ico": "image/x-icon"}


def sh(node, cmd, stdin=None, timeout=60):
    out = subprocess.run(["docker", "exec", "-i", f"{LAB}-{node}", "sh", "-c", cmd],
                         input=stdin, capture_output=True, text=True, timeout=timeout)
    return out.stdout


def vtysh(node, *cmds):
    return sh(node, "vtysh " + " ".join(f"-c '{c}'" for c in cmds))


def vtysh_config(node, lines):
    """Apply many config lines at once through a file (much faster than one vtysh call per line)."""
    sh(node, "cat > /tmp/apply.conf && vtysh -f /tmp/apply.conf >/dev/null 2>&1", stdin="\n".join(lines) + "\n")


def leaked_prefixes():
    with open(ROOT / "results" / "as55410-2021" / "rrc00" / "leaked_prefixes.csv") as f:
        rows = sorted(csv.DictReader(f), key=lambda r: r["first_seen"])
    return [r["prefix"] for r in rows if ":" not in r["prefix"]][:LEAK_SIZE]


def load_cone():
    import bz2
    path = ROOT / "data" / "as-rel" / "20210401.ppdc-ases.txt.bz2"
    with bz2.open(path, "rt") as f:
        for line in f:
            if line.startswith(f"{VODAFONE} "):
                return {int(a) for a in line.split()}
    return {VODAFONE}


class Demo:
    def __init__(self):
        print("loading the 2021 leak, RPKI and ownership data ...")
        self.leak = leaked_prefixes()
        self.vrps = rpki.VRPSet.from_ripe_archive(sorted(glob.glob(str(ROOT / "data" / "rpki" / "2021-04-16" / "*.xz"))))
        self.pfx2as = extract.load_pfx2as(next((ROOT / "data" / "pfx2as").glob("routeviews-rv2-20210416-*.pfx2as.gz")))
        self.cone = load_cone()
        # What the session normally carries: Vodafone's announcements in the two days before the leak
        baseline = next((ROOT / "data" / "ripestat").glob("AS55410_20210414*.json"))
        self.expected = {p["prefix"] for p in json.loads(baseline.read_text())["data"]["prefixes"]}
        self.lock = threading.Lock()
        self.mode = "none"
        self.leaking = False
        self.injected = []
        self.events = deque(maxlen=60)
        self.history = deque(maxlen=240)
        self.state = {}
        self.reset_guard()
        print(f"ready: {len(self.leak)} leaked prefixes, {self.vrps.count:,} VRPs, Vodafone expected set {len(self.expected)}")

    # ---- lab control ---------------------------------------------------------------------------
    def vodafone_routes(self):
        """Routes Vodafone sends Airtel before Airtel's policy (soft-reconfiguration), or None if unreadable."""
        out = vtysh("airtel", f"show bgp ipv4 unicast neighbors {VODAFONE_NEIGHBOR} received-routes json")
        try:
            return json.loads(out).get("receivedRoutes", {})
        except json.JSONDecodeError:
            return None

    def owners(self, prefix):
        return extract.legit_origins(prefix, self.pfx2as) - {VODAFONE}

    def reset_guard(self):
        self.guard = ConeGuard(VODAFONE, self.cone, self.expected, self.vrps, self.owners,
                               Config(window_s=300, burst_new=25, burst_owners=5))
        self.seen, self.blocked, self.counts = set(), [], {"alert": 0, "quarantine": 0, "reject": 0}

    def log(self, msg):
        self.events.appendleft({"t": time.strftime("%H:%M:%S"), "msg": msg})

    def set_mode(self, mode):
        with self.lock:
            self.mode = mode
            self.clear_protection()
            if mode == "maxprefix":
                vtysh_config("airtel", ["router bgp 9498", "address-family ipv4 unicast",
                                        f"neighbor {VODAFONE_NEIGHBOR} maximum-prefix {MAX_PREFIX}"])
            self.log(f"Airtel protection set to: {MODES[mode]}")

    def clear_protection(self):
        vtysh_config("airtel", ["no ip prefix-list CG-QUARANTINE", "ip prefix-list CG-QUARANTINE seq 1 permit 255.255.255.255/32",
                                "router bgp 9498", "address-family ipv4 unicast",
                                f"no neighbor {VODAFONE_NEIGHBOR} maximum-prefix"])
        if self.session_state() == "Established":
            vtysh("airtel", f"clear bgp ipv4 unicast {VODAFONE_NEIGHBOR} soft in")
        else:  # torn down by max-prefix: bring it back up
            vtysh("airtel", f"clear bgp ipv4 unicast {VODAFONE_NEIGHBOR}")
        self.reset_guard()

    def session_state(self):
        try:
            summary = json.loads(vtysh("airtel", "show bgp ipv4 unicast summary json") or "{}")
        except json.JSONDecodeError:
            return "?"
        return summary.get("peers", {}).get(VODAFONE_NEIGHBOR, {}).get("state", "?")

    def start_leak(self):
        if self.leaking:
            return
        self.leaking = True
        self.log(f"Vodafone starts re-originating {len(self.leak):,} prefixes it does not own (real 2021 order)")
        threading.Thread(target=self._leak, daemon=True).start()

    def _leak(self):
        for i in range(0, len(self.leak), LEAK_RATE):
            if not self.leaking:
                return
            batch = self.leak[i:i + LEAK_RATE]
            vtysh_config("vodafone", [f"ip route {p} blackhole tag 666" for p in batch])
            self.injected.extend(batch)
            time.sleep(1)

    def stop_leak(self):
        self.leaking = False
        time.sleep(1.1)  # let an in-flight batch land so it is withdrawn too
        config = vtysh("vodafone", "show running-config")
        leaked = [line.strip() for line in config.splitlines() if line.strip().startswith("ip route") and "tag 666" in line]
        if leaked:
            vtysh_config("vodafone", [f"no {line}" for line in leaked])
            self.log(f"Vodafone withdraws the {len(leaked):,} leaked routes")
        self.injected = []

    def reset(self):
        self.stop_leak()
        self.set_mode("none")
        time.sleep(2)  # let the withdrawals settle so the chart starts clean
        self.history.clear()
        self.log("Lab reset")

    # ---- ConeGuard controller --------------------------------------------------------------------
    def control(self):
        """Watch what Vodafone sends Airtel (pre-policy) and quarantine what the engine blocks."""
        while True:
            time.sleep(0.5)
            with self.lock:
                if self.mode not in ("rov", "coneguard"):
                    continue
                routes = self.vodafone_routes()
                if routes is None:
                    continue  # unreadable this round; never mistake that for a mass withdrawal
                now = time.time()
                new_blocks = []
                for prefix in routes.keys() - self.seen:
                    self.seen.add(prefix)
                    if self.mode == "rov":
                        if self.vrps.validate(prefix, VODAFONE) == rpki.INVALID:
                            new_blocks.append(prefix)
                            self.counts["reject"] += 1
                        continue
                    in_burst = self.guard.burst_since is not None
                    d = self.guard.announce(now, prefix, VODAFONE)
                    if d.action in BLOCKED:
                        new_blocks.append(prefix)
                        self.counts["reject" if d.action == "reject" else "quarantine"] += 1
                    elif d.action == ALERT:
                        self.counts["alert"] += 1
                    if d.retro:
                        new_blocks.extend(d.retro)
                        self.counts["alert"] -= len(d.retro)
                        self.counts["quarantine"] += len(d.retro)
                    if not in_burst and self.guard.burst_since is not None:
                        self.log(f"ConeGuard: mass leak detected from AS{VODAFONE} after {len(self.seen)} new prefixes; "
                                 f"quarantining foreign routes, Vodafone's own routes keep flowing")
                for prefix in self.seen - routes.keys():
                    self.seen.discard(prefix)
                    self.guard.withdraw(now, prefix)
                if new_blocks:
                    start = len(self.blocked) + 10
                    self.blocked.extend(new_blocks)
                    vtysh_config("airtel", [f"ip prefix-list CG-QUARANTINE seq {start + i} permit {p}" for i, p in enumerate(new_blocks)])
                    vtysh("airtel", f"clear bgp ipv4 unicast {VODAFONE_NEIGHBOR} soft in")

    # ---- status -----------------------------------------------------------------------------------
    def probe(self, ip):
        try:
            out = sh("user", f"wget -T 1 -qO- http://{ip} 2>/dev/null", timeout=5)
        except subprocess.TimeoutExpired:
            return False  # no answer in time counts as unreachable
        return "reachable" in out

    def status(self):
        while True:
            try:
                summary = json.loads(vtysh("airtel", "show bgp ipv4 unicast summary json") or "{}")
                peer = summary.get("peers", {}).get(VODAFONE_NEIGHBOR, {})
                reach = {name: self.probe(ip) for name, ip in TARGETS.items()}
                accepted = peer.get("pfxRcd", 0) if peer.get("state") == "Established" else 0
                with self.lock:
                    self.state = {
                        "mode": self.mode, "modes": MODES, "leaking": self.leaking, "injected": len(self.injected),
                        "session": peer.get("state", "?"), "accepted": accepted,
                        "received": len(self.seen) if self.mode in ("rov", "coneguard") else None,
                        "burst": self.guard.burst_since is not None, "counts": dict(self.counts),
                        "reach": reach, "events": list(self.events),
                        "victims": {p: {"seen": p in self.seen, "blocked": p in self.blocked,
                                        "status": self.guard.status.get(p)} for p in VICTIM_PREFIXES},
                    }
                    self.history.append({"t": time.time(), "accepted": accepted, "injected": len(self.injected),
                                         **{k: int(v) for k, v in reach.items()}})
                    self.state["history"] = list(self.history)
            except Exception as e:  # keep the dashboard alive through transient docker/vtysh errors
                print(f"status error: {e}", file=sys.stderr)  # for the operator, not the audience's event log
            time.sleep(1)


MODES = {"none": "No protection (as in 2021)", "rov": "ROV with 2021 RPKI",
         "maxprefix": f"Max-prefix limit ({MAX_PREFIX})", "coneguard": "ConeGuard"}


def serve(demo, port=8080):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, body, ctype, cache=True):
            data = body if isinstance(body, bytes) else body.encode()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            if not cache:
                self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/state", "/api/state"):
                with demo.lock:
                    self._send(json.dumps(demo.state), "application/json", cache=False)
            elif SITE.is_dir():
                # the built React site (web/dist); unknown paths get index.html
                target = (SITE / path.lstrip("/")).resolve()
                if not target.is_file() or SITE.resolve() not in target.parents:
                    target = SITE / "index.html"
                # index.html and results.json change on every build; the hashed assets never do
                fresh = target.suffix == ".html" or target.name == "results.json"
                self._send(target.read_bytes(), TYPES.get(target.suffix, "application/octet-stream"), cache=not fresh)
            else:
                self._send(PAGE.read_text(), "text/html; charset=utf-8")

        def do_POST(self):
            action = self.path.split("?")[0].strip("/").removeprefix("api/")
            if action == "leak":
                demo.start_leak()
            elif action == "stop":
                demo.stop_leak()
            elif action == "reset":
                demo.reset()
            elif action.startswith("mode/") and action[5:] in MODES:
                demo.set_mode(action[5:])
            self._send("{}", "application/json")

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("0.0.0.0", port), Handler) as httpd:
        print(f"dashboard: http://localhost:{port}")
        httpd.serve_forever()


if __name__ == "__main__":
    demo = Demo()
    demo.reset()
    threading.Thread(target=demo.control, daemon=True).start()
    threading.Thread(target=demo.status, daemon=True).start()
    serve(demo)
