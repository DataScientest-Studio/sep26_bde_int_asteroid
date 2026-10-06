import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime, timezone
import requests
from dotenv import load_dotenv

load_dotenv()

EMAIL = os.environ["JPL_CONTACT_EMAIL"]
RAW_DIR = Path(os.environ["RAW_DATA_DIR"])

USER = f"Project: Asteroid-risk-tracker, Version: 0.1, Contact: ({EMAIL})"

END_POINTS = [
            ("sentry_s", "https://ssd-api.jpl.nasa.gov/sentry.api", {}, "daily"),
            ("sentry_v", "https://ssd-api.jpl.nasa.gov/sentry.api", {"all": "1"}, "daily"),
            ("sentry_r", "https://ssd-api.jpl.nasa.gov/sentry.api", {"removed": "1"}, "daily"),
            ("scout", "https://ssd-api.jpl.nasa.gov/scout.api", {}, "daily"),
            ("cad", "https://ssd-api.jpl.nasa.gov/cad.api", {}, "daily"),
            ("sbdb", "https://ssd-api.jpl.nasa.gov/sbdb_query.api", {
                "sb-group": "neo",
                "fields": "spkid,pdes,full_name,class,neo,pha,H,diameter,albedo,moid,e,a,q,i,epoch",
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
    for name, url, params, tag in END_POINTS:
        if tag != schedule:
            continue
        fetch(name, url, params)
        time.sleep(3)