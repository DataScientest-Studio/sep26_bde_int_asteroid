"""
Streamlit dashboard talks to the API over HTTP.
This keeps the database credentials server-side and makes the frontend replaceable.
"""

import os
import pandas as pd
import requests
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
st.set_page_config(page_title="Asteroid Risk Tracker", layout="wide")

@st.cache_data(ttl=300)
def get(path, **params):
    try:
        r = requests.get(API + path, params=params, timeout=30)
    except requests.exceptions.RequestException as error:
        st.error("Cannot reach the API at %s.\n\nIs uvicorn running?\n\n%s"
                 % (API, error))
        st.stop()
    if r.status_code in (404, 503):
        return None
    if r.status_code != 200:
        st.error("%s returned %d\n\n%s" % (path, r.status_code, r.text[:400]))
        st.stop()
    return r.json()

PAGES = ["Overview", "Risk list", "What changed?", "Observation gaps",
         "Close approaches", "Size distribution", "Object lookup",
         "Prediction", "Does the model work?", "Data quality"]

page = st.sidebar.radio("Page", PAGES)

health = get("/health")
st.sidebar.divider()
st.sidebar.caption("Latest snapshot: %s" % health["latest_snapshot"][:10])
st.sidebar.caption("Model: %s" % ("loaded" if health["model_loaded"] else "not available"))

# Overview 

if page == "Overview":
    st.title("Asteroid close-approach and risk tracker")
    st.caption("Data from NASA/JPL, with the day-by-day history of the Sentry risk list reconstructed from daily snapshots.")

    d = get("/stats/overview")

    a, b, c, e = st.columns(4)
    a.metric("Objects tracked", "{:,}".format(d["objects_tracked"]))
    b.metric("On the risk list", "{:,}".format(d["on_risk_list"]))
    c.metric("Objects removed from list", "{:,}".format(d["removed_from_list"]))
    e.metric("Changes recorded", "{:,}".format(d["risk_changes_logged"]))

    st.subheader("What the catalogue contains")
    classes = pd.DataFrame(d["by_class"]).set_index("class")
    st.bar_chart(classes["objects"])
    st.caption("APO, ATE and AMO are near-Earth asteroid classes. APO and ATE cross Earth's orbit; AMO approaches without crossing.")

# Risk list 

elif page == "Risk list":
    st.title("Current risk list")
    limit = st.slider("Objects to show", 10, 200, 25, step=5)

    d = get("/risk", limit=limit)
    st.info(d["note"])
    st.dataframe(pd.DataFrame(d["objects"]), use_container_width=True)
    st.caption("Sorted by cumulative Palermo scale, not by raw impact probability. "
               "The probability leaders are metre-scale objects "
               "whose orbits are poorly determined - that is high uncertainty, not high danger.")

# What changed?

elif page == "What changed?":
    st.title("What changed on the risk list?")
    st.caption("JPL publishes only today's list. This history exists nowhere else: "
               "it is rebuilt by comparing each daily snapshot with the one before it.")

    chosen = st.date_input("Date", value=None)
    d = get("/changes", date=str(chosen) if chosen else None)

    if d["count"] == 0:
        st.warning("No changes recorded on %s." % d["date"])
    else:
        a, b, c = st.columns(3)
        a.metric("Changes", d["count"])
        b.metric("Left the list", d["left_sentry"])
        c.metric("Risk updated", d["updated"])
        st.dataframe(pd.DataFrame(d["changes"]), use_container_width=True)

# Observation gaps 

elif page == "Observation gaps":
    st.title("How long since anyone looked?")

    d = get("/stats/observation-gaps")
    buckets = pd.DataFrame(d["buckets"]).set_index("bucket")
    st.bar_chart(buckets["objects"])
    st.caption("An object stays on the risk list until fresh observations rule an impact out. "
               "Most are not being observed, "
               "so the list states information about our ignorance, than danger.")

    st.subheader("Longest unobserved")
    st.dataframe(pd.DataFrame(d["longest_unobserved"]),
                 use_container_width=True)

# Close approaches 

elif page == "Close approaches":
    st.title("Close approaches")

    gran = st.radio("Group by", ["month", "year"], horizontal=True)
    d = get("/stats/approaches-timeline", granularity=gran)
    st.line_chart(pd.DataFrame(d["series"]).set_index("period")["approaches"])

    st.subheader("Coming up")
    col1, col2 = st.columns(2)
    days = col1.slider("Within days", 7, 365, 90)
    lunar = col2.slider("Closer than (lunar distances)", 1, 50, 20)

    u = get("/approaches", days=days, max_dist=lunar * 0.00257)
    st.caption("%d approaches within %d days and %.1f lunar distances."
               % (u["count"], u["window_days"], u["max_distance_lunar"]))
    st.dataframe(pd.DataFrame(u["approaches"]), use_container_width=True)

# Size distribution 

elif page == "Size distribution":
    st.title("How big are they?")

    d = get("/stats/size-distribution")
    bins = pd.DataFrame(d["bins"]).set_index("size_bin")
    st.bar_chart(bins[["all_objects", "on_risk_list"]])
    st.caption("Diameter is estimated from brightness assuming an albedo of "
               "%s, because under 3%% of objects have a measured one. The "
               "smallest bins reflect our detection limit, not how many such "
               "objects exist." % d["albedo_assumed"])

# Object lookup 

elif page == "Object lookup":
    st.title("Look up an object")
    q = st.text_input("Catalogue number, designation or name", "Apophis")

    if q:
        d = get("/object/" + q)
        if d is None:
            st.warning("Nothing matches '%s'." % q)
        else:
            obj = d["object"]
            st.subheader(obj["full_name"] or obj["pdes"])
            st.caption("Status: %s" % d["status"].replace("_", " "))

            a, b, c = st.columns(3)
            a.metric("Class", obj["class"])
            b.metric("Absolute magnitude", obj["h"])
            c.metric("MOID (AU)",
                     d["current_orbit"]["moid"] if d["current_orbit"] else "-")

            if d["current_risk"]:
                st.subheader("Current risk assessment")
                st.json(d["current_risk"])

            if d["upcoming_approaches"]:
                st.subheader("Upcoming approaches")
                st.dataframe(pd.DataFrame(d["upcoming_approaches"]),
                             use_container_width=True)

            if d["risk_history"]:
                st.subheader("Risk history")
                st.dataframe(pd.DataFrame(d["risk_history"]),
                             use_container_width=True)

# Prediction

elif page == "Prediction":
    st.title("Will this object be cleared?")
    st.caption("The model is trained on objects whose outcome is known - "
               "still listed versus already removed - and scores the ones still open.")

    q = st.text_input("Designation", "Apophis")
    if q:
        d = get("/predict/" + q)
        if d is None:
            st.warning("No prediction for '%s'. Either it has never been on "
                       "the risk list, or the model is not loaded." % q)
        else:
            st.metric("Probability of being cleared",
                      "{:.1%}".format(d["probability_removed"]))
            st.caption("Already removed: %s" % d["already_removed"])

    st.divider()
    st.subheader("Most likely to be cleared next")
    s = get("/model/scores", limit=25)
    if s and s["most_likely_to_be_cleared"]:
        st.dataframe(pd.DataFrame(s["most_likely_to_be_cleared"]),
                     use_container_width=True)
    else:
        st.info("No scores logged yet - score.py has not run.")

# Validation 

elif page == "Does the model work?":
    st.title("Does the model work?")
    st.caption("Every row below is a prediction recorded BEFORE the outcome existed.")

    d = get("/model/validation")

    if not d or not d["summary"]:
        st.info("No predictions logged yet. score.py writes them weekly.")
    else:
        st.caption("Baseline scoring date: %s" % d["baseline_date"])
        cols = st.columns(len(d["summary"]))
        for col, row in zip(cols, d["summary"]):
            col.metric("Model said %s" % row["model_said"],
                       "{:.1f}%".format(row["removal_rate_pct"]),
                       "%d of %d removed since"
                       % (row["removed_since"], row["objects_scored"]))
        st.warning(d["note"])

        if d["confirmed"]:
            st.subheader("Confirmed outcomes")
            st.dataframe(pd.DataFrame(d["confirmed"]),
                         use_container_width=True)

    st.divider()
    st.subheader("How the model was evaluated?")
    info = get("/model/info")
    if info is None:
        st.info("The model is not loaded.")
    else:
        a, b, c = st.columns(3)
        a.metric("PR-AUC", info["pr_auc_test"])
        b.metric("Accuracy", info["accuracy_test"])
        c.metric("Majority baseline", info["pr_auc_majority_baseline"])

        groups = info.get("pr_auc_by_feature_group")
        if groups:
            st.bar_chart(pd.Series(groups))
            st.caption("The orbit alone outperforms observational effort, "
                       "which answers the obvious objection that the model "
                       "is simply restating the removal rule.")

# Data quality 

elif page == "Data quality":
    st.title("Is the pipeline healthy?")

    d = get("/stats/data-quality")
    st.subheader("Sources")
    st.dataframe(pd.DataFrame(d["sources"]), use_container_width=True)

    st.subheader("Missing values")
    a, b = st.columns(2)
    a.json(d["object_nulls_pct"])
    b.json(d["orbit_nulls_pct"])
    st.info(d["note"])