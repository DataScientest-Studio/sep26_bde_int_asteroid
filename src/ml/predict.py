"""
Score objects with the promoted model.

    from ml.predict import predict_one, predict_listed, model_info

The artifacts are loaded once, on import. If train.py promotes a new model,
the API process must be restarted (or call reload()).
"""

import json
import os

import joblib

from dataset import load_data

HERE = os.path.dirname(os.path.abspath(__file__))
CURRENT = os.path.join(HERE, "output", "current")

_model = None
_features = None
_metrics = None
_version = None
_frame = None


def reload():
    """Load the artifacts and the scoring frame. Called once on import."""
    global _model, _features, _metrics, _version, _frame

    if not os.path.exists(os.path.join(CURRENT, "model.joblib")):
        raise RuntimeError(
            "no promoted model in %s - run train.py first" % CURRENT)

    _model = joblib.load(os.path.join(CURRENT, "model.joblib"))

    with open(os.path.join(CURRENT, "features.json")) as f:
        _features = json.load(f)
    with open(os.path.join(CURRENT, "metrics.json")) as f:
        _metrics = json.load(f)
    with open(os.path.join(CURRENT, "VERSION")) as f:
        _version = f.read().strip()

    # 5,000 rows - cheap to hold in memory, and it avoids a database round
    # trip per request.
    _frame = load_data()
    _frame[_features["boolean"]] = _frame[_features["boolean"]].astype(int)

    # the contract check. if the query gained, lost or reordered a column
    # since the model was trained, refuse rather than predict on scrambled
    # input - the model would not raise, it would just be wrong.
    have = [c for c in _frame.columns
            if c not in _features["id_columns"] + [_features["target"]]]
    if have != _features["features"]:
        raise RuntimeError(
            "dataset.sql no longer matches features.json.\n"
            "  expected: %s\n  got:      %s" % (_features["features"], have))


def _score(rows):
    X = rows[_features["features"]]
    return _model.predict_proba(X)[:, 1]


def predict_one(spkid):
    """Probability that this object's impact risk gets ruled out."""
    rows = _frame[_frame["spkid"] == spkid]
    if len(rows) == 0:
        return None

    row = rows.iloc[[0]]
    return {
        "spkid": int(row["spkid"].iloc[0]),
        "pdes": str(row["pdes"].iloc[0]),
        "probability_removed": round(float(_score(row)[0]), 4),
        "already_removed": bool(row["removed"].iloc[0]),
        "model_version": _version,
    }


def predict_listed():
    """Score every object still on the risk list, most likely to be cleared
    first. This is what the brief asks for: the model is trained on resolved
    outcomes and scores the objects whose outcome is still open."""
    rows = _frame[_frame["removed"] == 0].copy()
    rows["probability_removed"] = _score(rows).round(4)

    out = rows[["spkid", "pdes", "probability_removed"]]
    return out.sort_values("probability_removed", ascending=False)


def model_info():
    info = dict(_metrics)
    info["version"] = _version
    info["n_features"] = len(_features["features"])
    return info


reload()


if __name__ == "__main__":
    print(json.dumps(model_info(), indent=2))
    print()
    print(predict_listed().head(20).to_string(index=False))