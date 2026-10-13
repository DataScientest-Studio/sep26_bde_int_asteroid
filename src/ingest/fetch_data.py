"""
Here we fetch relevant data for the project from their respective NASA/JPL APIs.

The APIs we need based on our project goal are:

    - Sentry: Gives the object-Earth impact risk assessment data
        - Mode-S: Summary table
        - Mode-R: Removed-objects table
    - CAD: Asteroid and comet close approaches to the planets in the past and future
    - SBDB: Small-Body DataBase query tool
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime, timezone
import requests
from dotenv import load_dotenv

# Configuration

load_dotenv()

EMAIL = os.environ["JPL_CONTACT_EMAIL"]
RAW_DIR = Path(os.environ["RAW_DATA_DIR"])

USER = f"Project: Asteroid-risk-tracker, Version: 0.1, Contact: ({EMAIL})"

END_POINTS = [
            ("sentry_s", "https://ssd-api.jpl.nasa.gov/sentry.api", {}, "daily"),
            ("sentry_r", "https://ssd-api.jpl.nasa.gov/sentry.api", {"removed": "1"}, "daily"),
            ("cad", "https://ssd-api.jpl.nasa.gov/cad.api", {
                "date-min": "1950-01-01",
                "date-max": "2100-01-01",
                "dist-max": "0.05",
                "sort": "date",
                }, "weekly"),
            ("sbdb", "https://ssd-api.jpl.nasa.gov/sbdb_query.api", {
                "sb-group": "neo",
                "fields": ("spkid,neo,pha,pdes,full_name,class,H,H_sigma,diameter,albedo,moid,ma,n,per,"
                "epoch,orbit_id,last_obs,data_arc,n_obs_used,n_del_obs_used,n_dop_obs_used,"
                "condition_code,rms,sigma_a,sigma_e,sigma_q,sigma_i,sigma_w,sigma_tp,e,a,q,i,om,w"),
            }, "weekly"),
]

def fetch(name, url, params):
    response = requests.get(url, params=params, headers={"User-Agent": USER}, timeout=60)
    response.raise_for_status()
    data = response.json()

    if "error" in data:
        raise RuntimeError(f"{name} ended up with {data['error']}")

    now = datetime.now(timezone.utc)
    record = {
            "end_point": name,
            "url": url,
            "params": params,
            "fetched": now.isoformat(),
            "data": data,
            "http_status": response.status_code
    }

    folder = RAW_DIR/name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/f"{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(record, indent=2))

    print(f"{name}: count={data.get('count')} -> {path.name}")

if __name__ == "__main__":
    schedule = sys.argv[1] if len(sys.argv) > 1 else "daily"
    only = sys.argv[2] if len(sys.argv) > 2 else None

    for name, url, params, tag in END_POINTS:
        if tag != schedule:
            continue
        if only is not None and name != only:
            continue
        fetch(name, url, params)
        time.sleep(3)