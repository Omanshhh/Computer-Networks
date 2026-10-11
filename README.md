# ConeGuard

Provider-side containment of mass re-origination BGP route leaks, motivated by the 16 April 2021
Vodafone Idea (AS55410) incident. ConeGuard runs on an upstream provider's customer session: it rejects
RPKI-invalid routes, accepts the routes a customer normally announces, and when a burst of routes owned by
many other networks arrives, it quarantines only those routes instead of tearing the whole session down.

Computer Networks project by Sara Agrawal, Omansh Sharma and Aakash Prathap, guided by Thamizharasan S,
School of Computer Science and Engineering (SCOPE), VIT Vellore.

## Headline results

| What | Result |
|---|---|
| Incidents replayed from raw BGP data | 5 (2010 to 2021), published figures reproduced |
| 2021 leak | 34,891 prefixes; escaped via **two** upstreams (AS9498 and AS1273) |
| ROV on the 2021 leak | 23% then, 66% with today's RPKI |
| Path checks (ASPA, RFC 9234) on re-origination leaks | 0 to 1.9% stopped (100% of the path-type DQE leak) |
| ConeGuard on the five incidents | 93.3 to 100% contained within 0 to 53 s, customer's own routes untouched |
| False alarms, 80,104 sessions x 41 normal days | 0.022 per session-year (strict filter: 4.68 days per session-year) |
| Internet-wide simulation, victims without ROA | only ConeGuard helps: 57.9% to 5.0% of ASes at 99% deployment |
| Live demo (FRRouting + containerlab) | ConeGuard keeps Google, Fastly and Vodafone reachable during the replayed leak |

## Layout

| Folder | What it holds |
|---|---|
| `corpus/` | `incidents.yaml`: leaker, upstream, time window and published figures per incident |
| `measure/` | download raw data, replay BGP updates, RPKI validation (RFC 6811), valley-free path checks |
| `guard/` | `engine.py`, the ConeGuard decision engine (standard library only) |
| `replay/` | `evaluate.py` (defence comparison), `false_alarms.py`, `tradeoff.py` (threshold sweep) |
| `sim/` | BGPy scenario and ConeGuard policy for the Internet-wide simulation |
| `lab/` | containerlab topology, FRR configs, `demo.py` (demo controller and web server), `setup_wsl.sh` |
| `web/` | the project website and live dashboard (React, Vite, React Bits animations) |
| `analysis/` | `figures.py` (static figures) and `export_web.py` (data for the website) |
| `tests/` | unit tests for the engine |
| `results/` | measured outputs: per-incident summaries and leaked-prefix tables, false alarms, simulation |

`data/` holds downloaded raw data and is not tracked; it is re-created on the first run.

## Setup (Windows)

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Reproduce the results

```
.venv\Scripts\python -m measure.replay_incident as55410-2021     (also rostelecom-2020, indosat-2014, chinatelecom-2010, verizon-dqe-2019)
.venv\Scripts\python -m replay.evaluate
.venv\Scripts\python -m replay.false_alarms
.venv\Scripts\python -m replay.tradeoff
.venv\Scripts\python -m sim.run --trials 20 --cpus 6 --adoption 0.1 0.5 0.99
.venv\Scripts\python -m analysis.figures
.venv\Scripts\python -m pytest tests
```

The first runs download the public data (about 1 GB of RIS updates, RPKI archives and CAIDA files).
The 2021 replay takes about 8 minutes, the false-alarm study about 20, the simulation about 30.

## Website

```
.venv\Scripts\python -m analysis.export_web
cd web
npm install
npm run build
```

`lab/demo.py` serves the built site from `web/dist`. During development, `npm run dev` serves it on
port 5173 and forwards `/api` to the demo controller on port 8080.

## Live demo (WSL Ubuntu)

One-time setup inside Ubuntu: `bash lab/setup_wsl.sh` (installs Docker and containerlab).

```
cd lab && containerlab deploy -t coneguard.clab.yml --reconfigure && cd ..
python3 lab/demo.py
```

Open http://localhost:8080 in the Windows browser. Pick Airtel's protection (no protection, ROV,
max-prefix limit or ConeGuard), press "Start the leak", and watch the network map and the reachability
tiles. Press "Reset the lab" between runs. Stop with Ctrl+C, then `containerlab destroy -t lab/coneguard.clab.yml`.

## Data sources and credits

- RIPE RIS raw updates: https://data.ris.ripe.net/
- RIPE NCC RPKI archive (daily VRPs per trust anchor): https://ftp.ripe.net/rpki/
- CAIDA AS relationships and customer cones: https://publicdata.caida.org/datasets/as-relationships/
- CAIDA RouteViews prefix-to-AS: https://publicdata.caida.org/datasets/routing/routeviews-prefix2as/
- RIPEstat announced-prefixes and as-overview APIs: https://stat.ripe.net/
- Scroll animations: React Bits (https://reactbits.dev), in `web/src/reactbits/`
- Internet-scale simulation: BGPy (https://github.com/jfuruness/bgpy_pkg)
