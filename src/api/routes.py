"""
Here we write the routes of the end-points.
Every edn-point:
    validates the arguments
    call the respective function in analytics.py or predict.py
    return what comes back.
"""

from dashboard import analytics
from fastapi import APIRouter, HTTPException, Query

try:
    from ml import predict
    MODEL_ERROR = None
except Exception as error:
    predict = None
    MODEL_ERROR = str(error)

router = APIRouter()

def need_model():
    if predict is None:
        raise HTTPException(503, "model unavailable: %s" % MODEL_ERROR)
    
@router.get("/")
def index():
    # Overview of what this API serves
    return {
        "name": "Asteroid risk tracker",
        "endpoints": {
            "statistics": ["/stats/overview",
                           "/stats/data-quality",
                           "/stats/observation-gaps",
                           "/stats/approaches-timeline",
                           "/stats/size-distribution"],
            "data": ["/risk",
                     "/approaches",
                     "/changes",
                     "/object/{designation}",
                     "/object/{designation}/orbit"],
            "model": ["/predict/{designation}",
                      "/model/info",
                      "/model/scores",
                      "/model/history",
                      "/model/validation"],
            "docs": "/docs",
        },
    }


@router.get("/health")
def health():
    # Is the database reachable, and how fresh is it?
    try:
        row = analytics.run(
            "select max(fetched)::text as latest from sentry_risk").iloc[0]
    except Exception as error:
        raise HTTPException(503, "database unreachable: %s" % error)

    return {
        "status": "ok",
        "database": "reachable",
        "latest_snapshot": row["latest"],
        "model_loaded": predict is not None,
        "model_error": MODEL_ERROR,
    }


@router.get("/stats/overview")
def stats_overview():
    # Headline counts: objects tracked, currently at risk, removed.
    return analytics.overview()


@router.get("/stats/data-quality")
def stats_data_quality():
    # Fetch rate per source, API versions, and which columns JPL does not populate.
    return analytics.data_quality()


@router.get("/stats/observation-gaps")
def stats_observation_gaps():
    # How long since each listed object was last observed.
    return analytics.observation_gaps()


@router.get("/stats/approaches-timeline")
def stats_approaches_timeline(
    granularity: str = Query("month", pattern="^(month|year)$")):
    # Close approaches aggregated over time.
    return analytics.approaches_timeline(granularity)


@router.get("/stats/size-distribution")
def stats_size_distribution():
    # Estimated diameters, binned, risk list against the whole catalogue.
    return analytics.size_distribution()


@router.get("/risk")
def risk(limit: int = Query(25, ge=1, le=200)):
    # Objects currently on the Sentry list, ranked by Palermo scale.
    return analytics.risk_ranking(limit)


@router.get("/approaches")
def approaches(
    days: int = Query(90, ge=1, le=3650),
    max_dist: float = Query(0.05, gt=0, le=1.0),
    limit: int = Query(200, ge=1, le=1000),
):
    # Upcoming close approaches. Distances are in astronomical units.
    # One lunar distance is 0.00257 AU.
    return analytics.upcoming_approaches(days, max_dist, limit)


@router.get("/changes")
def changes(
    date: str = Query(None, description="YYYY-MM-DD. Omit for the most "
                                        "recent day that has any.")
):
    # What moved on the risk list on a given day. 
    # This history exists nowhere else - JPL publishes only today's list.
    return analytics.changes_on(date)


@router.get("/object/{designation}")
def object_detail(designation: str):
    # Everything about one object. 
    # Any designation form works: a catalogue number, a provisional designation, or a common name.
    result = analytics.object_detail(designation)
    if result is None:
        raise HTTPException(404, "no object matches '%s'" % designation)
    return result


@router.get("/object/{designation}/orbit")
def object_orbit(designation: str, limit: int = Query(50, ge=1, le=500)):
    # Every orbit solution held for this object, oldest first.
    result = analytics.orbit_history(designation, limit)
    if result is None:
        raise HTTPException(404, "no object matches '%s'" % designation)
    return result


@router.get("/predict/{designation}")
def predict_object(designation: str):
    # Probability that this object's impact risk gets ruled out.
    need_model()

    spkid = analytics.resolve(designation)
    if spkid is None:
        raise HTTPException(404, "no object matches '%s'" % designation)

    result = predict.predict_one(spkid)
    if result is None:
        raise HTTPException(
            404,
            "'%s' resolved to %d but has never been on the risk list, "
            "so there is nothing to predict" % (designation, spkid))
    return result


@router.get("/model/info")
def model_info():
    # What the model is, and how it scored.
    need_model()
    return predict.model_info()


@router.get("/model/scores")
def model_scores(limit: int = Query(25, ge=1, le=200)):
    # The latest scoring run, and the objects whose score moved most.
    return analytics.prediction_scores(limit)


@router.get("/model/history")
def model_history():
    # Every scoring run, oldest first.
    return analytics.prediction_history()


@router.get("/model/validation")
def model_validation():
    # Predictions recorded before the outcome, against what happened.
    return analytics.prediction_outcomes()