"""
Here each function has a purpose which is to fulfill the statistics requirements of an endpoint.
Every function returns dictionary/lists, and not the plots themselves. 
This data is then used for visualization via Streamlit.
This is delivered by the each endpoint via FastAPI.

The endpoints are selected based on the data exploration.
"""

import os
import json 
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text

PATH = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(PATH, "..", "..", ".env")

load_dotenv(ENV)

# from section 13: refitted against the objects with a measured diameter.
# diameter varies as the inverse square root of albedo, so this constant
# matters more than it looks.
ALBEDO = 0.14

host = os.getenv('PG_HOST')
username = os.getenv('PG_USER')
password = os.getenv('PG_PASSWORD')
port = os.getenv('PG_PORT')
database = os.getenv('PG_DB')

engine = create_engine(f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{database}")


def run(sql):
    return pd.read_sql(sql, engine)

def run_params(sql, params):
    return pd.read_sql(text(sql), engine, params=params)

def records(sql):
    """
    For each SQL query, it returns the records in JSON format
    """
    return run(sql).to_dict("records")

def records_params(sql, params):
    """
    For each SQL query, it returns the records in JSON format along with the parameters
    """
    return run_params(sql, params).to_dict("records")

#---------
# Overview
#---------
"""
This gives a brief overview of the dataset
"""

def overview():
    totals = run("""
        select
          (select count(*) from object_dimension) as objects_tracked,
          (select count(distinct des) from sentry_risk where fetched = (select max(fetched) from sentry_risk)) as on_risk_list,
          (select count(*) from risk_removal) as removed_from_list,
          (select count(*) from close_approach) as close_approaches,
          (select count(*) from source_log) as snapshots_fetched,
          (select count(*) from risk_change) as risk_changes_logged,
          (select max(fetched) from sentry_risk) as latest_snapshot
    """).iloc[0]

    by_class = records("""
        select class, count(*) as objects from object_dimension
        group by class
        order by objects desc
    """)

    return {
        "objects_tracked": int(totals["objects_tracked"]),
        "on_risk_list": int(totals["on_risk_list"]),
        "removed_from_list": int(totals["removed_from_list"]),
        "close_approaches": int(totals["close_approaches"]),
        "snapshots_fetched": int(totals["snapshots_fetched"]),
        "risk_changes_logged": int(totals["risk_changes_logged"]),
        "latest_snapshot": str(totals["latest_snapshot"]),
        "by_class": by_class,
    }


#-------------
# Data quality
#-------------
"""
This endpoint shows if the pipeline is being truthful.
It shows:
    how often each source was fetched
    what version it returned
    and which columns JPL simply does not populate.
"""

def data_quality():
    sources = records("""
        select collection,
               count(*) as fetches,
               max(fetched)::text as latest_fetch,
               max(api_version) as api_version,
               round(avg(row_count)) as avg_rows_returned
        from source_log
        group by collection
        order by collection
    """)

    # Here, JPL publishes a diameter or albedo only where a radar or thermal measurement exists.
    nulls = run("""
        select
          round(100.0 * avg(case when diameter is null then 1 else 0 end), 1) as diameter_null_pct,
          round(100.0 * avg(case when albedo   is null then 1 else 0 end), 1) as albedo_null_pct,
          round(100.0 * avg(case when h        is null then 1 else 0 end), 1) as h_null_pct
        from object_dimension
    """).iloc[0]

    orbit_nulls = run("""
        select
          round(100.0 * avg(case when moid is null then 1 else 0 end), 1) as moid_null_pct,
          round(100.0 * avg(case when rms  is null then 1 else 0 end), 1) as rms_null_pct,
          round(100.0 * avg(case when ma   is null then 1 else 0 end), 1) as ma_null_pct
        from orbit
        where is_current = true
    """).iloc[0]

    return {
        "sources": sources,
        "object_nulls_pct": {k: float(v) for k, v in nulls.items()},
        "orbit_nulls_pct": {k: float(v) for k, v in orbit_nulls.items()},
        "note": ("diameter and albedo are null because no radar or thermal "
                 "measurement exists; mean anomaly is null because the field "
                 "was added to the fetch after those orbit rows were written"),
    }


#-----------------
# Observation gaps
#-----------------
"""
Most objects on the risk list have not been observed for years. 
"""

def observation_gaps():
    rows = records("""
        select
          case
            when gap <= 30   then 'last 30 days'
            when gap <= 365  then '30 days to 1 year'
            when gap <= 1825 then '1 to 5 years'
            else 'over 5 years'
          end as bucket,
          count(*) as objects
        from (
          select (select max(fetched) from sentry_risk)::date
                 - last_obs_ts::date as gap
          from sentry_risk
          where fetched = (select max(fetched) from sentry_risk)
            and last_obs_ts is not null
        ) as g
        group by bucket
    """)

    order = ["last 30 days", "30 days to 1 year", "1 to 5 years", "over 5 years"]
    by_bucket = {r["bucket"]: int(r["objects"]) for r in rows}

    longest = records("""
        select r.des,
               dim.full_name,
               r.last_obs_ts::date::text as last_observed,
               (select max(fetched) from sentry_risk)::date
                 - r.last_obs_ts::date   as days_since_last_obs,
               r.h,
               r.ps_cum
        from sentry_risk r
        left join object_dimension dim on dim.spkid = r.spkid
        where r.fetched = (select max(fetched) from sentry_risk)
          and r.last_obs_ts is not null
        order by r.last_obs_ts
        limit 10
    """)

    return {
        "buckets": [{"bucket": b, "objects": by_bucket.get(b, 0)}
                    for b in order], "longest_unobserved": longest,
    }


#--------------------
# Approaches timeline 
#--------------------

"""
The close-approach table is far too large to return raw.
So this aggregate helps in visualising.
"""

def approaches_timeline(granularity="month"):
    if granularity not in ("month", "year"):
        raise ValueError("granularity must be 'month' or 'year'")

    rows = records("""
        select date_trunc('%s', approach_date)::date::text as period,
               count(*)            as approaches,
               round(min(dist)::numeric, 5) as closest_au
        from close_approach
        group by period
        order by period
    """ % granularity)

    return {"granularity": granularity, "series": rows}

#-------------------
# Size distribution
#-------------------

"""
The diameter is estimated from brightness using the refitted albedo above.
So these are estimates for all except a few hundred objects.
"""

def size_distribution():
    rows = records("""
        select
          case
            when d_est < 0.01  then '<10 m'
            when d_est < 0.03  then '10-30 m'
            when d_est < 0.14  then '30-140 m'
            when d_est < 0.3   then '140-300 m'
            when d_est < 1     then '300 m-1 km'
            when d_est < 3     then '1-3 km'
            else '>3 km'
          end as size_bin,
          count(*) filter (where on_list) as on_risk_list,
          count(*)                        as all_objects
        from (
          select (1329 / sqrt(%s)) * power(10, -dim.h / 5) as d_est,
                 dim.spkid in (select spkid from sentry_risk
                               where spkid is not null) as on_list
          from object_dimension dim
          where dim.h is not null
        ) as sized
        group by size_bin
    """ % ALBEDO)

    order = ["<10 m", "10-30 m", "30-140 m", "140-300 m",
             "300 m-1 km", "1-3 km", ">3 km"]
    found = {r["size_bin"]: r for r in rows}

    return {
        "albedo_assumed": ALBEDO,
        "bins": [found.get(b, {"size_bin": b, "on_risk_list": 0,
                               "all_objects": 0}) for b in order],
        "note": ("diameters are estimated from absolute magnitude with an "
                 "assumed albedo; the smallest bins reflect the detection "
                 "limit, not how many such objects exist"),
    }

#-------------
# Risk ranking 
#-------------

"""
Sorted by Palermo scale, not by raw impact probability.
"""
def risk_ranking(limit=25):
    rows = records("""
        select r.des,
               dim.full_name,
               dim.class,
               r.ps_cum,
               r.ps_max,
               r.ip,
               r.n_imp,
               r.h,
               r.v_inf,
               r.range_start,
               r.range_end,
               r.last_obs_ts::date::text as last_observed
        from sentry_risk r
        left join object_dimension dim on dim.spkid = r.spkid
        where r.fetched = (select max(fetched) from sentry_risk)
        order by r.ps_cum desc nulls last
        limit %d
    """ % int(limit))

    return {
        "sorted_by": "ps_cum",
        "note": ("Palermo scale is log10 of the risk relative to the "
                 "background rate of random impacts; every value below zero "
                 "is below that background"),
        "objects": rows,
    }

#----------------
# Name resolution 
#----------------

"""
Three alias types exist: pdes and full_name for every object
And sentry_id only for objects that have been on the risk list.
"""

def resolve(designation):
    """Designation of any form -> spkid, or None.
    Returns the spkid only; callers decide what to fetch with it."""
    q = designation.strip()

    if q.isdigit():
        rows = run_params(
            "select distinct spkid from object_alias where alias_value = :q",
            {"q": q})
    else:
        rows = run_params(
            "select distinct spkid from object_alias "
            "where lower(alias_value) = lower(:q)",
            {"q": q})

        if len(rows) == 0:
            rows = run_params(
                "select distinct spkid from object_alias "
                "where alias_type = 'full_name' "
                "  and lower(alias_value) like lower(:pattern)",
                {"pattern": "%" + q + "%"})

    if len(rows) == 0:
        return None
    return int(rows["spkid"].iloc[0])

#--------------
# Object detail 
#--------------

"""
This gives an object, its current orbit,
its risk entry if listed, its removal record if cleared, and its next approaches.
"""

def object_detail(designation):
    spkid = resolve(designation)
    if spkid is None:
        return None

    obj = run_params("""
        select spkid, pdes, full_name, class, is_comet, h, h_sigma,
               diameter, albedo,
               first_seen::text, last_seen::text
        from object_dimension
        where spkid = :spkid
    """, {"spkid": spkid})
    if len(obj) == 0:
        return None

    orbit = records_params("""
        select orbit_id_num, epoch, e, a, q, i, om, w, moid, pha, rms,
               condition_code, n_obs_used, n_del_obs_used, n_dop_obs_used,
               data_arc, last_obs::text, valid_from::text
        from orbit
        where spkid = :spkid and is_current = true
    """, {"spkid": spkid})

    # the current risk entry, if it is on the list today
    risk = records_params("""
        select des, ip, ps_cum, ps_max, ts_max, n_imp, v_inf,
               range_start, range_end, last_obs_ts::text, fetched::text
        from sentry_risk
        where spkid = :spkid
          and fetched = (select max(fetched) from sentry_risk)
    """, {"spkid": spkid})

    removal = records_params("""
        select des, removed::text, first_listed::text
        from risk_removal
        where spkid = :spkid
    """, {"spkid": spkid})

    approaches = records_params("""
        select approach_date::text, dist, dist_min, dist_max, v_rel,
               orbit_id_num
        from close_approach
        where spkid = :spkid
          and approach_date >= current_date
        order by approach_date
        limit 10
    """, {"spkid": spkid})

    changes = records_params("""
        select fetched::text, prev_fetched::text,
               ip_before, ip_after, d_ip,
               ps_cum_before, ps_cum_after, d_ps_cum,
               n_imp_before, n_imp_after, left_sentry
        from risk_change
        where spkid = :spkid
        order by fetched desc
        limit 20
    """, {"spkid": spkid})

    return {
        "object": obj.to_dict("records")[0],
        "current_orbit": orbit[0] if orbit else None,
        "current_risk": risk[0] if risk else None,
        "removal": removal[0] if removal else None,
        "status": ("removed" if removal else
                   "on_risk_list" if risk else "not_listed"),
        "upcoming_approaches": approaches,
        "risk_history": changes,
    }

#--------------
# Orbit history 
#--------------

"""
Most objects hold a single solution, so this returns a handful of rows.
The limit is there because the history deepens every month the pipeline runs.
"""
def orbit_history(designation, limit=50):
    spkid = resolve(designation)
    if spkid is None:
        return None

    rows = records_params("""
        select orbit_id_num, epoch, epoch_ts::text,
               e, a, q, i, om, w, moid, rms, condition_code,
               n_obs_used, data_arc, last_obs::text,
               valid_from::text, valid_to::text, is_current
        from orbit
        where spkid = :spkid
        order by valid_from
        limit :limit
    """, {"spkid": spkid, "limit": int(limit)})

    return {"spkid": spkid, "solutions": len(rows), "history": rows}


#--------------------
# Upcoming approaches 
#--------------------

def upcoming_approaches(days=90, max_dist=0.05, limit=200):
    rows = records_params("""
        select c.approach_date::text,
               c.des,
               dim.full_name,
               dim.class,
               dim.h,
               c.dist,
               round((c.dist / 0.00257)::numeric, 2) as dist_lunar,
               c.dist_min,
               c.v_rel,
               c.t_sigma_f
        from close_approach c
        left join object_dimension dim on dim.spkid = c.spkid
        where c.approach_date >= current_date
          and c.approach_date <= current_date + (:days || ' days')::interval
          and c.dist <= :max_dist
        order by c.approach_date
        limit :limit
    """, {"days": int(days), "max_dist": float(max_dist),
          "limit": int(limit)})

    return {
        "window_days": int(days),
        "max_distance_au": float(max_dist),
        "max_distance_lunar": round(float(max_dist) / 0.00257, 1),
        "count": len(rows),
        "approaches": rows,
    }

#------------------
# Changes on a date
#------------------

"""
JPL publishes only today's list, so this history exists nowhere else.
"""

def changes_on(date=None):
    """Risk changes recorded on a date. With no date, the most recent day that has any."""
    if date is None:
        latest = run("""
            select max(fetched)::date::text as d from risk_change
        """)
        date = latest["d"].iloc[0]
        if date is None:
            return {"date": None, "count": 0, "changes": []}

    rows = records_params("""
        select k.des,
               dim.full_name,
               dim.class,
               k.fetched::text,
               k.prev_fetched::text,
               k.ip_before, k.ip_after, k.d_ip,
               k.ps_cum_before, k.ps_cum_after, k.d_ps_cum,
               k.n_imp_before, k.n_imp_after, k.d_n_imp,
               k.left_sentry
        from risk_change k
        left join object_dimension dim on dim.spkid = k.spkid
        where k.fetched::date = cast(:the_date as date)
        order by k.left_sentry desc, abs(coalesce(k.d_ps_cum, 0)) desc
    """,{"the_date": date})

    return {
        "date": str(date),
        "count": len(rows),
        "left_sentry": int(sum(1 for r in rows if r["left_sentry"])),
        "updated": int(sum(1 for r in rows if not r["left_sentry"])),
        "changes": rows,
    }

if __name__ == "__main__":
    for name, fn in [("overview", overview),
                     ("data_quality", data_quality),
                     ("observation_gaps", observation_gaps),
                     ("approaches_timeline", approaches_timeline),
                     ("size_distribution", size_distribution),
                     ("risk_ranking", risk_ranking),
                     ("upcoming_approaches", upcoming_approaches),
                     ("changes_on", changes_on)]:
        print("=" * 60)
        print(name)
        print("=" * 60)
        print(json.dumps(fn(), indent=2, default=str)[:1200])
        print()

    print("=" * 60)
    print("resolve")
    print("=" * 60)
    for q in ["433", "Apophis", "2004 MN4", "101955", "Bennu", "nonsense"]:
        print("%-12s -> %s" % (q, resolve(q)))
    print()

    print("=" * 60)
    print("object_detail('Apophis')")
    print("=" * 60)
    print(json.dumps(object_detail("Apophis"), indent=2, default=str)[:1500])
    print()

    print("=" * 60)
    print("orbit_history('Apophis')")
    print("=" * 60)
    print(json.dumps(orbit_history("Apophis"), indent=2, default=str)[:1200])