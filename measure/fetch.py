"""Download the raw public data an incident replay needs.

Everything is cached under data/ so each file is fetched once.
Sources:
  RIPE RIS update dumps   https://data.ris.ripe.net/<collector>/YYYY.MM/updates.YYYYMMDD.HHMM.gz
  RPKI VRP archive        https://ftp.ripe.net/rpki/<tal>.tal/YYYY/MM/DD/roas.csv.xz
  CAIDA prefix-to-AS      https://publicdata.caida.org/datasets/routing/routeviews-prefix2as/
  RIPEstat                https://stat.ripe.net/data/announced-prefixes/
"""
import bz2
import datetime as dt
import json
import os
import pathlib
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
TALS = ["afrinic", "apnic", "arin", "lacnic", "ripencc"]


def _download(url, dest, max_stalls=5):
    """Download to dest via a .part file, resuming with HTTP Range whenever the connection drops.

    Keeps retrying while attempts make progress; gives up after `max_stalls` attempts in a row that don't.
    """
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.{os.getpid()}.part")  # per process, so parallel runs don't collide
    stalls = 0
    while True:
        have = tmp.stat().st_size if tmp.exists() else 0
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with requests.get(url, stream=True, timeout=300, headers=headers) as r:
                if r.status_code == 416:  # nothing left to fetch
                    break
                r.raise_for_status()
                mode = "ab" if have and r.status_code == 206 else "wb"
                with open(tmp, mode) as f:
                    for chunk in r.iter_content(1 << 16):
                        f.write(chunk)
            break
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError):
            progressed = tmp.exists() and tmp.stat().st_size > have
            stalls = 0 if progressed else stalls + 1
            if stalls >= max_stalls:
                raise
            time.sleep(1 + stalls * 2)
    try:
        tmp.replace(dest)
    except PermissionError:  # another process finished the same file first and has it open
        if not dest.exists():
            raise
        tmp.unlink(missing_ok=True)
    return dest


def ris_updates(collector, start, end, workers=4):
    """RIS writes one update file per 5 minutes, named by the start of its interval."""
    t = start.replace(minute=start.minute - start.minute % 5, second=0, microsecond=0)
    jobs = []
    while t < end:
        name = f"updates.{t:%Y%m%d.%H%M}.gz"
        jobs.append((f"https://data.ris.ripe.net/{collector}/{t:%Y.%m}/{name}", DATA / "ris" / collector / name))
        t += dt.timedelta(minutes=5)
    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(lambda job: _download(*job), jobs))


def vrps(day):
    """Validated ROA payloads from all five RIR trust anchors, as archived on `day`."""
    paths = []
    for tal in TALS:
        url = f"https://ftp.ripe.net/rpki/{tal}.tal/{day:%Y/%m/%d}/roas.csv.xz"
        paths.append(_download(url, DATA / "rpki" / f"{day:%Y-%m-%d}" / f"{tal}.roas.csv.xz"))
    return paths


def latest_vrp_day(max_back=10):
    """Most recent day for which the RIPE archive has a complete VRP snapshot."""
    day = dt.date.today()
    for _ in range(max_back):
        urls = [f"https://ftp.ripe.net/rpki/{tal}.tal/{day:%Y/%m/%d}/roas.csv.xz" for tal in TALS]
        if all(requests.head(u, timeout=60).ok for u in urls):
            return day
        day -= dt.timedelta(days=1)
    raise RuntimeError("no complete VRP snapshot found in the RIPE archive")


def pfx2as(day):
    """CAIDA RouteViews prefix-to-AS snapshot closest to the start of `day`."""
    index = f"https://publicdata.caida.org/datasets/routing/routeviews-prefix2as/{day:%Y/%m}/"
    names = sorted(set(re.findall(rf"routeviews-rv2-{day:%Y%m%d}-\d{{4}}\.pfx2as\.gz", requests.get(index, timeout=60).text)))
    if not names:
        raise RuntimeError(f"no pfx2as snapshot for {day}")
    return _download(index + names[0], DATA / "pfx2as" / names[0])


def as_rel(day):
    """CAIDA AS-relationship snapshot (serial-1) for the month containing `day`."""
    name = f"{day:%Y%m}01.as-rel.txt.bz2"
    url = f"https://publicdata.caida.org/datasets/as-relationships/serial-1/{name}"
    return _download(url, DATA / "as-rel" / name)


def customer_cone(asn, day):
    """ASNs in `asn`'s customer cone (itself included) from CAIDA's ppdc-ases file for that month."""
    name = f"{day:%Y%m}01.ppdc-ases.txt.bz2"
    path = _download(f"https://publicdata.caida.org/datasets/as-relationships/serial-1/{name}", DATA / "as-rel" / name)
    with bz2.open(path, "rt") as f:
        for line in f:
            if line.startswith(f"{asn} "):
                return {int(a) for a in line.split()}
    return {asn}


def announced_prefixes(asn, start, end):
    """Prefixes `asn` originated between start and end, according to RIPEstat."""
    dest = DATA / "ripestat" / f"AS{asn}_{start:%Y%m%dT%H%M}_{end:%Y%m%dT%H%M}.json"
    if not dest.exists():
        r = requests.get(
            "https://stat.ripe.net/data/announced-prefixes/data.json",
            params={"resource": f"AS{asn}", "starttime": start.isoformat(), "endtime": end.isoformat()},
            timeout=300,
        )
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(r.text)
    return {p["prefix"] for p in json.loads(dest.read_text())["data"]["prefixes"]}
