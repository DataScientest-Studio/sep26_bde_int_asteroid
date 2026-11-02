"""
We score objects with the trained model.
"""

import json
import os
import joblib

from dataset import load_data

HERE = os.path.dirname(os.path.abspath(__file__))

_model = None
_features = None
_metrics = None
_frame = None


def load_model():
    """Load the artifacts and the scoring frame. Called once on import."""
    global _model, _features, _metrics, _frame

    path = os.path.join(HERE, "model.joblib")
    if not os.path.exists(path):
        raise RuntimeError("no model at %s - run train.py first" % path)

    _model = joblib.load(path)

    with open(os.path.join(HERE, "features.json")) as f:
        _features = json.load(f)
    with open(os.path.join(HERE, "metrics.json")) as f:
        _metrics = json.load(f)
    _frame = load_data()
    _frame[_features["boolean"]] = _frame[_features["boolean"]].astype(int)

    have = [c for c in _frame.columns
            if c not in _features["id_columns"] + [_features["target"]]]
    if have != _features["features"]:
        raise RuntimeError(
            "dataset.sql no longer matches features.json\n"
            "  expected: %s\n  got:      %s"
            % (_features["features"], have))


def _score(rows):
    return _model.predict_proba(rows[_features["features"]])[:, 1]


def predict_one(spkid):
    """Probability that this object's impact risk gets ruled out.
    Returns None if the object has never been on the risk list."""
    rows = _frame[_frame["spkid"] == spkid]
    if len(rows) == 0:
        return None

    row = rows.iloc[[0]]
    return {
        "spkid": int(row["spkid"].iloc[0]),
        "pdes": str(row["pdes"].iloc[0]),
        "probability_removed": round(float(_score(row)[0]), 4),
        "already_removed": bool(row["removed"].iloc[0]),
    }


def predict_listed():
    """Score every object still on the risk list, most likely to be cleared
    first. This is what the brief asks for: trained on resolved outcomes,
    applied to the objects whose outcome is still open."""
    rows = _frame[_frame["removed"] == 0].copy()
    rows["probability_removed"] = _score(rows).round(4)
    return (rows[["spkid", "pdes", "probability_removed"]]
            .sort_values("probability_removed", ascending=False))


def model_info():
    info = dict(_metrics)
    info["n_scored"] = int((_frame["removed"] == 0).sum())
    return info


load_model()


if __name__ == "__main__":
    print(json.dumps(model_info(), indent=2))
    print()
    print(predict_listed().head(20).to_string(index=False))