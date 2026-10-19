"""
Based on the data exploration, we have recognized the fields and require some cleaning.
This will help downstream tasks like when the cleaned data is fed into a structured database.
"""

import os
import sys
from pymongo import MongoClient, ReplaceOne
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

#--------------
# Configuration
#--------------

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DATABASE_NAME = os.getenv("MONGO_DB", "bronze")
BATCH_SIZE = 2000  

#-------------------------------------------
# Split the fields from different collection 
#-------------------------------------------

COMET_CLASSES = ["ETc", "HTC", "JFC", "JFc"]

CAD_RAW = ["jd", "dist", "dist_min", "dist_max"] # since higher precision than a float is required
CAD_FLOAT = ["jd", "dist", "dist_min", "dist_max", "v_rel", "v_inf"]
CAD_STRING = ["des", "orbit_id", "cd", "t_sigma_f"]

SBDB_ALREADY_NUMERIC = ["spkid", "n_obs_used", "n_del_obs_used", "n_dop_obs_used"]
SBDB_INTEGER = ["data_arc"]
SBDB_FLOAT = ["H", "H_sigma", "diameter", "albedo", "moid", "ma", "n", "per", "epoch", 
              "rms", "e", "a", "q", "i", "om", "w", "sigma_a", "sigma_e", "sigma_q", 
               "sigma_i", "sigma_w", "sigma_tp"]
SBDB_STRING = ["pdes", "pha", "class", "orbit_id"]

SENTRY_S_ALREADY_NUMERIC = ["n_imp"]
SENTRY_S_INTEGER = ["ts_max"]
SENTRY_S_FLOAT = ["h", "diameter", "v_inf", "ip", "ps_cum", "ps_max", "last_obs_jd"]
SENTRY_S_STRING = ["des", "id"]

#-------------------------------------------------------------------------
# Check to count if any field could not be cast into their respective form
#-------------------------------------------------------------------------

cast_fail = {}

def note_cast_fail(field):
    if field in cast_fail:
        cast_fail[field] = cast_fail[field] + 1
    else:
        cast_fail[field] = 1

#---------------------------------------------------------------------
# Next we write helper functions to cast a field into the form we need
#---------------------------------------------------------------------

def to_float(record, key):
    """
    Converts the value of a given key to float
    """
    value = record.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except(TypeError, ValueError):
        note_cast_fail(key)
        return None

def to_integer(record, key):
    """
    Converts the value of a given key to integer
    """
    value = record.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except(TypeError, ValueError):
        note_cast_fail(key)
        return None

def to_date(record, key):
    """
    Parses an ISO date format
    """
    value = record.get(key)
    if value is None:
        return None
    try:
        parsed = datetime.strptime(value, '%Y-%m-%d')
        return parsed.replace(tzinfo=timezone.utc)
    except(TypeError, ValueError):
        note_cast_fail(key)
        return None

def to_timestamp(record, key):
    """
    Parses a complete timestamp
    """
    value = record.get(key)
    if value is None:
        return None
    try:
        parsed = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        return parsed.replace(tzinfo=timezone.utc)
    except(TypeError, ValueError):
        note_cast_fail(key)
        return None

def trim(value):
    """
    Removes any padding
    """
    if value is None:
        return None
    else:
        return value.strip()

def extract_digits(value):
    """
    Some fields have text and numerical fields combined into a string.
    We are interested only in the digit part which we need to extract.
    """
    if value is None:
        return None 
    keep = ""
    for char in value:
        if char.isdigit():
            keep = keep + char
    return keep 

def year_range(record, key):
    """
    Splits the year range into separate entities
    """
    value = record.get(key)
    if value is None:
        return None, None
    year = value.split('-')
    if len(year) != 2:
        note_cast_fail(key)
        return None, None 
    try:
        return int(year[0]), int(year[1])
    except(ValueError):
        note_cast_fail(key)
        return None, None 

def common(doc):
    """
    This adds the 'id' fields to every collection
    """
    return {
        "_id": doc["_id"],
        "_source_file": doc["_source_file"],
        "_row_index": doc["_row_index"],
        "_snapshot_fetched": doc["_snapshot_fetched"],
    }

#---------------------------------------------
# A couple of fields require special attention 
#---------------------------------------------

def to_condition_code(record):
    """
    This contains null plus '0' to '9', and can carry non-numeric values in some contexts, 
    so anything outside 0-9 becomes None.
    """
    value = record.get('condition_code')
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        note_cast_fail('condition_code')
        return None
    if number < 0 or number > 9:
        note_cast_fail('condition_code')
        return None
    return number

def jd_to_dt(jd):
    """
    Convert a Julian Day number to a datetime.
    """
    if jd is None:
        return None
    days_since_1970 = jd - 2440587.5
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(days=days_since_1970)

#------------------------------------------------------------------------
# Transformation and creation of a second MongoDB layer with cleaned data
#------------------------------------------------------------------------


def make_sentry_r(doc, alias):
    """
    This makes a cleaned sentry_r collection from the previous layer.
    """
    record = doc["record"]
    out = common(doc)

    out["des"] = record.get("des")
    out["removed"] = to_timestamp(record, "removed")
    out["spkid"] = alias.get(record.get("des"))

    return out 

def make_sentry_s(doc, alias):
    """
    This makes a cleaned sentry_s collection.
    Here we drop 'fullname' as it is a duplicate of sbdb.full_name.
    And also drop 'last_obs' as 'last_obs_jd' says the same thing as an unambiguous number.
    """
    record = doc["record"]
    out = common(doc)

    for key in SENTRY_S_FLOAT:
        out[key] = to_float(record, key)
    for key in SENTRY_S_INTEGER:
        out[key] = to_integer(record, key)
    for key in SENTRY_S_ALREADY_NUMERIC:
        out[key] = record.get(key)
    for key in SENTRY_S_STRING:
        out[key] = record.get(key)

    out["range_start"], out["range_end"] = year_range(record, "range")
    out["last_obs_ts"] = jd_to_dt(out["last_obs_jd"])
    out["spkid"] = alias.get(record.get("des"))

    return out

def make_cad(doc, alias):
    """
    This makes a cleaned cad collection.
    'h' is dropped as it is identical to sbdb.H.
    """
    record = doc["record"]
    out = common(doc)

    for key in CAD_FLOAT:
        out[key] = to_float(record, key)
    for key in CAD_STRING:
        out[key] = record.get(key)

    # keep the exact source strings for the four precision-critical fields
    for key in CAD_RAW:
        out[key + "_raw"] = record.get(key)

    out["approach_ts"] = jd_to_dt(out["jd"])
    if out["approach_ts"] is None:
        out["approach_date"] = None
    else:
        out["approach_date"] = out["approach_ts"].date().isoformat()

    out["orbit_id_num"] = extract_digits(record.get("orbit_id"))
    out["spkid"] = alias.get(record.get("des"))

    return out

def make_sbdb(doc, alias):
    """
    This makes sbdb collection.
    'neo' is dropped as it is always 'Y'.
    """
    record = doc["record"]
    out = common(doc)

    for key in SBDB_FLOAT:
        out[key] = to_float(record, key)
    for key in SBDB_INTEGER:
        out[key] = to_integer(record, key)
    for key in SBDB_ALREADY_NUMERIC:
        out[key] = record.get(key)
    for key in SBDB_STRING:
        out[key] = record.get(key)

    out["full_name"] = trim(record.get("full_name"))
    out["condition_code"] = to_condition_code(record)
    out["last_obs"] = to_date(record, "last_obs")

    # added by silver
    out["orbit_id_num"] = extract_digits(record.get("orbit_id"))
    out["is_comet"] = record.get("class") in COMET_CLASSES
    out["epoch_ts"] = jd_to_dt(out["epoch"])

    return out

TRANSFORMS = {
    "sbdb":     ("clean_sbdb",     make_sbdb),
    "sentry_s": ("clean_sentry_s", make_sentry_s),
    "sentry_r": ("clean_sentry_r", make_sentry_r),
    "cad":      ("clean_cad",      make_cad),
}

#-------------------------------------------------
# Mapping object designations for downstream tasks
#-------------------------------------------------

def build_alias(db):
    """
    Build a dictionary from every known designation to its spkid, using the
    newest sbdb snapshot. This is what resolves Sentry and CAD rows, which
    carry no spkid of their own - sbdb is the only one of the four sources that
    publishes a stable object identifier.
    """
    newest = db.snapshots.find_one({"collection": "sbdb"}, sort=[("_id", -1)])
    if newest is None:
        print("No sbdb snapshot found - cannot build the alias map.")
        sys.exit(1)

    print("Building alias map from " + newest["_id"])

    alias = {}
    alias_kind = {}
    rows = db.sbdb.find({"_source_file": newest["_id"]},
                        {"record.spkid": 1, "record.pdes": 1,
                         "record.full_name": 1})
    for row in rows:
        record = row["record"]
        spkid = record.get("spkid")
        if spkid is None:
            continue
        if record.get("pdes") is not None:
            alias[record["pdes"]] = spkid
            alias_kind[record["pdes"]] = "pdes"
        if record.get("full_name") is not None:
            alias[trim(record["full_name"])] = spkid
            alias_kind[trim(record["full_name"])] = "full_name"

    print("  " + str(len(alias)) + " designations mapped")
    return alias, alias_kind, newest["_id"]


def write_alias(db, alias, alias_kind, sbdb_file):
    """
    This collection is for looking an object up by any of its
    names later.

    The key is (alias_type, alias_value), not (spkid, alias_type), because:
    one name should only point to one object.
    """
    collection = db["clean_alias"]
    collection.delete_many({})
    collection.create_index("spkid")

    operations = []
    written = 0

    for alias_value in alias:
        spkid = alias[alias_value]
        alias_type = alias_kind[alias_value]

        document = {
            "_id": alias_type + ":" + alias_value,
            "alias_type": alias_type,
            "alias_value": alias_value,
            "spkid": spkid,
            "_source_file": sbdb_file,
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

    newest = db.snapshots.find_one({"collection": "sentry_s"},
                                   sort=[("_id", -1)])
    if newest is not None:
        operations = []
        rows = db.sentry_s.find({"_source_file": newest["_id"]},
                                {"record.des": 1, "record.id": 1})
        for row in rows:
            record = row["record"]
            sentry_id = record.get("id")
            spkid = alias.get(record.get("des"))
            if sentry_id is None or spkid is None:
                continue
            document = {
                "_id": "sentry_id:" + sentry_id,
                "alias_type": "sentry_id",
                "alias_value": sentry_id,
                "spkid": spkid,
                "_source_file": newest["_id"],
            }
            operations.append(
                ReplaceOne({"_id": document["_id"]}, document, upsert=True)
            )
        if operations:
            collection.bulk_write(operations, ordered=False)
            written = written + len(operations)

    print("clean_alias: " + str(written) + " aliases written")

#-------------------------
# Processing each snapshot
#-------------------------

def process_snapshot(db, name, clean_name, transform,
                     snapshot, alias):
    """
    Transform every first layer row of one snapshot into its clean collection.
    Returns the number of rows written, or None if this snapshot was already
    done on an earlier run.
    """
    file_name = snapshot["_id"]

    if db.clean_runs.find_one({"_id": file_name}, {"_id": 1}) is not None:
        return None

    cast_fail.clear()

    source = db[name]
    target = db[clean_name]
    target.create_index("_source_file")
    target.create_index("spkid")

    rows = 0
    written = 0
    unresolved = 0
    operations = []

    for doc in source.find({"_source_file": file_name}):
        rows = rows + 1
        clean_doc = transform(doc, alias)

        if "spkid" in clean_doc and clean_doc["spkid"] is None:
            unresolved = unresolved + 1

        operations.append(
            ReplaceOne({"_id": clean_doc["_id"]}, clean_doc, upsert=True)
        )
        if len(operations) >= BATCH_SIZE:
            target.bulk_write(operations, ordered=False)
            written = written + len(operations)
            operations = []

    if operations:
        target.bulk_write(operations, ordered=False)
        written = written + len(operations)

    if written != rows:
        raise ValueError("read " + str(rows) + " rows but wrote "
                         + str(written) + " clean rows")

    db.clean_runs.insert_one({
        "_id": file_name,
        "collection": name,
        "clean_collection": clean_name,
        "rows": rows,
        "clean_rows": written,
        "unresolved_spkid": unresolved,
        "casts": dict(cast_fail),
        "fields_requested": snapshot.get("params", {}).get("fields"),
        "processed_at": datetime.now(timezone.utc),
    })

    message = "  " + file_name + ": " + str(written) + " rows"
    if unresolved > 0:
        message = message + ", " + str(unresolved) + " unresolved spkid"
    if len(cast_fail) > 0:
        message = message + ", cast " + str(dict(cast_fail))
    print(message)

    return written

#-------------------------------------------------------------
# Main: Connect to MongoDB to execute the whole transformation
#-------------------------------------------------------------

def main():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)

    try:
        client.admin.command("ping")
        db = client[DATABASE_NAME]
        print("Connected to MongoDB: " + DATABASE_NAME)
        print("")

        alias, alias_kind, sbdb_file = build_alias(db)
        write_alias(db, alias, alias_kind, sbdb_file)
        print("")

        total_written = 0
        total_skipped = 0
        total_failed = 0

        for name in ["sbdb", "sentry_s", "sentry_r", "cad"]:
            clean_name, transform = TRANSFORMS[name]

            snapshots = list(db.snapshots.find(
                {"collection": name}).sort("_id", 1))
            print(name + " -> " + clean_name + ": "
                  + str(len(snapshots)) + " snapshots")

            for snapshot in snapshots:
                try:
                    written = process_snapshot(db, name, clean_name,
                                               transform, snapshot, alias)
                    if written is None:
                        total_skipped = total_skipped + 1
                    else:
                        total_written = total_written + written
                except Exception as error:
                    print("  FAILED " + snapshot["_id"] + ": " + str(error))
                    total_failed = total_failed + 1

        print("")
        print("Summary")
        print("  rows written:       " + str(total_written))
        print("  snapshots skipped:  " + str(total_skipped))
        print("  snapshots failed:   " + str(total_failed))
        print("")

        print("Clean collections:")
        for name in sorted(db.list_collection_names()):
            if name.startswith("clean_"):
                count = db[name].count_documents({})
                print("  " + name + ": " + str(count) + " documents")

        if total_failed > 0:
            sys.exit(1)

    finally:
        client.close()


if __name__ == "__main__":
    main()
