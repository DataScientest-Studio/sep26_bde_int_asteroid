"""
Here we feed the cleaned data from MongoDB into PostgreSQL database.
"""

import os
import sys
from dotenv import load_dotenv
from pymongo import MongoClient
import psycopg2
from psycopg2.extras import execute_values, Json

#---------------
# Configuration
#---------------

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB = os.getenv("MONGO_DB", "asteroid")

POSTGRES = {
        "host": os.getenv("PG_HOST", "localhost"),
        "port": os.getenv("PG_PORT", "5432"),
        "database": os.getenv("PG_DB", "asteroid"),
        "user": os.getenv("PG_USER", "asteroid"),
        "password": os.getenv("PG_PASSWORD"),
}

MONGO_COLLECTION = ['cad', 'sbdb', 'sentry_s', 'sentry_r']
POSTGRES_TABLES = ('source_log, object_dimension, object_alias, orbit, sentry_risk, '
                   'risk_removal, close_approach, risk_change')

#--------------------------------------------------------------------------------------
# Helper functions
# These will check if any value is null or not and insert rows into respective columns
#--------------------------------------------------------------------------------------

def check(value):
    if value == 'Y':
        return True
    elif value == 'N':
        return False
    else:
        return None

def insert(cur, table, columns, rows):
    if not rows:
        return print(f"{table}: 0 rows")
    else:
        sql = "INSERT INTO %s (%s) VALUES %%s" % (table, ", ".join(columns))
        execute_values(cur, sql, rows, page_size=1000)
        print("  %-18s %d rows" % (table, len(rows)))


#------------------------------
# Insert data into 'source_log'
#------------------------------

def load_source_log(db, cur):
    rows = []
    for doc in db.snapshots.find({"collection": {"$in": MONGO_COLLECTION}}):
        signature = doc.get("api_signature") or {}
        rows.append((doc["_id"],
                     doc["collection"],
                     doc.get("fetched"),
                     Json(doc.get("params")),
                     signature.get("version"),
                     doc.get("row_count")))
    insert(cur, "source_log",["source_file", "collection", "fetched", "params","api_version", "row_count"], rows)

#------------------------------------
# Insert data into 'object_dimension'
#------------------------------------

def load_object_dimension(db, cur):
    """
    One row per object seen. Reading 'oldest-first' snapshots  means the
    last write per 'spkid' is the newest description of it.
    """

    latest = {}
    first_seen = {}
    last_seen = {}

    for d in db.clean_sbdb.find().sort("_snapshot_fetched", 1):
        spkid = d["spkid"]
        when = d["_snapshot_fetched"]
        if spkid not in first_seen:
            first_seen[spkid] = when
        last_seen[spkid] = when
        latest[spkid] = (d["pdes"], d["full_name"], d["class"], d["is_comet"],
                         d.get("H"), d.get("H_sigma"), d.get("diameter"),
                         d.get("albedo"), d["_source_file"])

    rows = []
    for spkid in latest:
        pdes, full_name, klass, is_comet, h, h_sigma, diameter, albedo, src = latest[spkid]
        rows.append((spkid, pdes, full_name, klass, is_comet, h, h_sigma,
                     diameter, albedo, first_seen[spkid], last_seen[spkid], src))

    insert(cur, "object_dimension",
           ["spkid", "pdes", "full_name", "class", "is_comet", "h", "h_sigma",
            "diameter", "albedo", "first_seen", "last_seen", "source_file"], rows)

#--------------------------------
# Insert data into 'object_alias'
#--------------------------------

def load_object_alias(db, cur):
    rows = []
    for d in db.clean_alias.find():
        rows.append((d["alias_type"], d["alias_value"],
                     d["spkid"], d["_source_file"]))
    insert(cur, "object_alias", ["alias_type", "alias_value", "spkid", "source_file"], rows)

#-------------------------
# Insert data into 'orbit'
#-------------------------

def load_orbit(db, cur):
    first = {}
    for d in db.clean_sbdb.find().sort("_snapshot_fetched", 1):
        key = (d["spkid"], d["orbit_id_num"])
        if key in first:
            continue
        first[key] = d

    by_object = {}
    for key in first:
        by_object.setdefault(key[0], []).append(key)

    rows = []
    for spkid in by_object:
        keys = sorted(by_object[spkid],
                      key=lambda k: first[k]["_snapshot_fetched"])
        for position in range(len(keys)):
            d = first[keys[position]]
            if position + 1 < len(keys):
                valid_to = first[keys[position + 1]]["_snapshot_fetched"]
                is_current = False
            else:
                valid_to = None
                is_current = True

            rows.append((spkid, d["orbit_id_num"], d["epoch"], d.get("epoch_ts"),
                         d.get("e"), d.get("a"), d.get("q"), d.get("i"),
                         d.get("om"), d.get("w"), d.get("ma"), d.get("n"),
                         d.get("per"), d.get("moid"), check(d.get("pha")),
                         d.get("rms"), d.get("condition_code"),
                         d.get("n_obs_used"), d.get("n_del_obs_used"),
                         d.get("n_dop_obs_used"), d.get("data_arc"),
                         d.get("last_obs"), d.get("sigma_a"), d.get("sigma_e"),
                         d.get("sigma_q"), d.get("sigma_i"), d.get("sigma_w"),
                         d.get("sigma_tp"), d["_snapshot_fetched"], valid_to,
                         is_current, d["_source_file"]))

    insert(cur, "orbit",
           ["spkid", "orbit_id_num", "epoch", "epoch_ts", "e", "a", "q", "i",
            "om", "w", "ma", "n", "per", "moid", "pha", "rms",
            "condition_code", "n_obs_used", "n_del_obs_used",
            "n_dop_obs_used", "data_arc", "last_obs", "sigma_a", "sigma_e",
            "sigma_q", "sigma_i", "sigma_w", "sigma_tp", "valid_from",
            "valid_to", "is_current", "source_file"], rows)

#-------------------------------
# Insert data into 'sentry_risk'
#-------------------------------

def load_sentry_risk(db, cur):
    rows = []
    for d in db.clean_sentry_s.find():
        rows.append((d["des"], d["_source_file"], d.get("spkid"), d.get("id"),
                     d.get("h"), d.get("diameter"), d.get("v_inf"),
                     d.get("ip"), d.get("ps_cum"), d.get("ps_max"),
                     d.get("ts_max"), d.get("n_imp"), d.get("last_obs_jd"),
                     d.get("last_obs_ts"), d.get("range_start"),
                     d.get("range_end"), d["_snapshot_fetched"]))
    insert(cur, "sentry_risk",
           ["des", "source_file", "spkid", "sentry_id", "h", "diameter",
            "v_inf", "ip", "ps_cum", "ps_max", "ts_max", "n_imp",
            "last_obs_jd", "last_obs_ts", "range_start", "range_end",
            "fetched"], rows)

#--------------------------------
# Insert data into 'risk_removal'
#--------------------------------

def load_risk_removal(db, cur):
    """
    The removed list is cumulative.
    """

    first = {}
    for d in db.clean_sentry_r.find().sort("_snapshot_fetched", 1):
        des = d["des"]
        if des in first:
            continue
        first[des] = (des, d.get("spkid"), d.get("removed"),
                      d["_snapshot_fetched"], d["_source_file"])

    insert(cur, "risk_removal",
           ["des", "spkid", "removed", "first_listed", "source_file"],
           list(first.values()))

#----------------------------------
# Insert data into 'close_approach'
#----------------------------------

def load_close_approach(db, cur):
    """
    Oldest-first, so a later snapshot's recomputation of the same
    (object, date, orbit solution) overwrites the earlier one.
    """
    seen = {}
    for d in db.clean_cad.find().sort("_snapshot_fetched", 1):
        key = (d["des"], d["approach_date"], d["orbit_id_num"])
        seen[key] = (d["des"], d["approach_date"], d["orbit_id_num"],
                     d.get("spkid"), d["jd"], d.get("jd_raw"),
                     d["approach_ts"], d.get("cd"), d.get("dist"),
                     d.get("dist_min"), d.get("dist_max"), d.get("dist_raw"),
                     d.get("dist_min_raw"), d.get("dist_max_raw"),
                     d.get("v_rel"), d.get("v_inf"), d.get("t_sigma_f"),
                     d["_source_file"])

    insert(cur, "close_approach",
           ["des", "approach_date", "orbit_id_num", "spkid", "jd", "jd_raw",
            "approach_ts", "cd_raw", "dist", "dist_min", "dist_max",
            "dist_raw", "dist_min_raw", "dist_max_raw", "v_rel", "v_inf",
            "t_sigma_f", "source_file"], list(seen.values()))

#-------------------------------
# Insert data into 'risk_change'
#-------------------------------

def load_risk_change(db, cur):
    """
    Compare each Sentry snapshot with the one before it. An object missing
    from the newer snapshot sets left_sentry.
    """
    snaps = []
    for run in db.clean_runs.find({"collection": "sentry_s"}).sort("_id", 1):
        rows = {}
        when = None
        for d in db.clean_sentry_s.find({"_source_file": run["_id"]}):
            rows[d["des"]] = d
            when = d["_snapshot_fetched"]
        if rows:
            snaps.append((when, rows))

    out = []
    for position in range(1, len(snaps)):
        prev_time, prev_rows = snaps[position - 1]
        curr_time, curr_rows = snaps[position]

        for des in prev_rows:
            before = prev_rows[des]
            after = curr_rows.get(des)

            if after is None:
                out.append((des, curr_time, before.get("spkid"), prev_time,
                            before.get("ip"), None, None,
                            before.get("ps_cum"), None, None,
                            before.get("n_imp"), None, None, True))
                continue

            if (before.get("ip") == after.get("ip")
                    and before.get("ps_cum") == after.get("ps_cum")
                    and before.get("n_imp") == after.get("n_imp")):
                continue

            out.append((des, curr_time, after.get("spkid"), prev_time,
                        before.get("ip"), after.get("ip"),
                        delta(after.get("ip"), before.get("ip")),
                        before.get("ps_cum"), after.get("ps_cum"),
                        delta(after.get("ps_cum"), before.get("ps_cum")),
                        before.get("n_imp"), after.get("n_imp"),
                        delta(after.get("n_imp"), before.get("n_imp")),
                        False))

    insert(cur, "risk_change",
           ["des", "fetched", "spkid", "prev_fetched", "ip_before",
            "ip_after", "d_ip", "ps_cum_before", "ps_cum_after", "d_ps_cum",
            "n_imp_before", "n_imp_after", "d_n_imp", "left_sentry"], out)


def delta(after, before):
    if after is None or before is None:
        return None
    return after - before

#-----
# Main
#-----

def main():
    mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
    conn = psycopg2.connect(**POSTGRES)

    try:
        mongo.admin.command("ping")
        db = mongo[MONGO_DB]
        cur = conn.cursor()
        print("mongo %s -> postgres %s\n" % (MONGO_DB, POSTGRES["database"]))

        cur.execute("TRUNCATE " + POSTGRES_TABLES)

        load_source_log(db, cur)
        load_object_dimension(db, cur)
        load_object_alias(db, cur)
        load_orbit(db, cur)
        load_sentry_risk(db, cur)
        load_risk_removal(db, cur)
        load_close_approach(db, cur)
        load_risk_change(db, cur)

        conn.commit()
        print("\nCOMMITED")

    except Exception as error:
        conn.rollback()
        print("\nROLLED BACK\n%s" % error)
        sys.exit(1)

    finally:
        conn.close()
        mongo.close()

if __name__ == "__main__":
    main()
