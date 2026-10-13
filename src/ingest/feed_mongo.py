"""
Ingest the raw NASA/JPL API snapshots into MongoDB (the bronze layer).

Layer 
    This layer has timestamped JSON files under RAW_DATA_DIR.
    MongoDB is derived from these files, and rebuildable from these very files.

What it reads
    Every .json file one level under RAW_DATA_DIR/<endpoint>/. 
    The folder name becomes the collection name.

We also introduce a new collection called 'snapshot':
    A snapshot is the complete response from one API endpoint at one moment,
    stored as one timestamped file.
    
What it writes
    One document per API record: one per asteroid per snapshot for SBDB,
    one per close-approach for CAD, one per listed object for Sentry.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient, ReplaceOne

# Configuration

load_dotenv()

RAW_DIR = Path(os.environ["RAW_DATA_DIR"])
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DATABASE_NAME = os.getenv("MONGO_DB", "bronze")
BATCH_SIZE = 2000  # Send these many documents to MongoDB at a time. 


def extract_records(payload):
    """
    Convert the supported API response formats into individual dictionaries.
    """

    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object from the API, got {type(payload).__name__}.")

    fields = payload.get("fields")
    rows = payload.get("data")

    if not isinstance(rows, list):
        raise ValueError("Unsupported API response structure; please check the raw JSON.")

    records = []

    for position, row in enumerate(rows):

        if isinstance(row, dict):
            # sentry already sends one object per row
            records.append(row)

        elif isinstance(row, list):
            # sbdb and cad send values only, with the column names in a separate "fields" list
            if not isinstance(fields, list):
                raise ValueError("The API returned list rows without a fields array.")

            if len(row) != len(fields):
                raise ValueError(f"Row {position} has {len(row)} values but there are {len(fields)} field names.")

            records.append(dict(zip(fields, row)))

        else:
            raise ValueError(f"Unexpected row type: {type(row).__name__}")

    return records


def ingest_file(snapshots, collection, file_path):
    """
    For each loaded raw file, return the number of records written, 
    or None if this file was already loaded during an earlier run.
    """

    file_name = file_path.name

    if snapshots.find_one({"_id": file_name}, {"_id": 1}) is not None:
        return None

    with file_path.open(encoding="utf-8") as file:
        raw = json.load(file)

    # raw is the envelope our capture script wrote: end_point, url, params, fetched, http_status, data
    # raw["data"] is exactly what JPL sent: signature, count, data  (and sometimes fields)

    payload = raw.get("data")
    records = extract_records(payload)

    fetched = raw.get("fetched")
    snapshot_fetched = (
        datetime.fromisoformat(fetched.replace("Z", "+00:00"))
        if fetched
        else None
    )

    ingested_at = datetime.now(timezone.utc)

    operations = []
    written = 0

    for index, record in enumerate(records):

        document = {
            "_id": f"{file_name}:{index}",
            "_source_file": file_name,
            "_row_index": index,
            "_snapshot_fetched": snapshot_fetched,
            "_ingested": ingested_at,
            "record": record,
        }

        operations.append(
            ReplaceOne({"_id": document["_id"]}, document, upsert=True)
        )

        if len(operations) >= BATCH_SIZE:
            collection.bulk_write(operations, ordered=False)
            written = written + len(operations)
            operations = []

    if operations:
        collection.bulk_write(operations, ordered=False)
        written = written + len(operations)
        operations = []

    snapshots.insert_one(
        {
            "_id": file_name,
            "collection": collection.name,
            "end_point": raw.get("end_point"),
            "url": raw.get("url"),
            "params": raw.get("params"),
            "http_status": raw.get("http_status"),
            "fetched": snapshot_fetched,
            "api_signature": payload.get("signature"),
            "fields": payload.get("fields"),
            "count_reported": payload.get("count"),
            "row_count": written,
            "_ingested": ingested_at,
        }
    )

    return written


def main():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)

    try:
        client.admin.command("ping")

        mongo_db = client[DATABASE_NAME]
        snapshots = mongo_db["snapshots"]

        print(f"Connected to MongoDB: {DATABASE_NAME}\n")

        files_loaded = 0
        files_skipped = 0
        files_failed = 0
        records_written = 0

        for folder in sorted(RAW_DIR.iterdir()):

            if not folder.is_dir():
                continue

            if folder.name == "snapshots":
                continue

            collection = mongo_db[folder.name]
            collection.create_index("_source_file")

            files = sorted(folder.glob("*.json"))
            print(f"{folder.name}: found {len(files)} files")

            for file_path in files:
                try:
                    written = ingest_file(snapshots, collection, file_path)

                    if written is None:
                        files_skipped = files_skipped + 1
                        continue

                    files_loaded = files_loaded + 1
                    records_written = records_written + written
                    print(f"  loaded {file_path.name}: {written} records")

                except Exception as error:
                    files_failed = files_failed + 1
                    print(f"  FAILED {file_path.name}: {error}")

        print("\nSummary")
        print(f"Files loaded:    {files_loaded}")
        print(f"Files skipped:   {files_skipped}")
        print(f"Files failed:    {files_failed}")
        print(f"Records written: {records_written}")

        print(f"\nCollections in {DATABASE_NAME}:")
        for name in sorted(mongo_db.list_collection_names()):
            count = mongo_db[name].count_documents({})
            print(f"  {name}: {count} documents")

        if files_failed:
            sys.exit(1)

    finally:
        client.close()


if __name__ == "__main__":
    main()