"""
Although this has been explored in a notebook, 
we write here the same components in the form of a pipeline.
This will help keep training the data as new data arrives and fills in the database.
"""

import json
import os
from datetime import datetime, timezone

import joblib
import numpy as np
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import (FunctionTransformer, OneHotEncoder, StandardScaler)

from dataset import load_data

HERE = os.path.dirname(os.path.abspath(__file__))

ID_COLS = ["spkid", "pdes"]
TARGET = "removed"


LOG_COLS = ["h_sigma", "n_obs_used", "n_del_obs_used", "n_dop_obs_used",
            "data_arc", "days_since_last_obs", "rms",
            "sigma_a", "sigma_e", "sigma_q", "sigma_i", "sigma_w", "sigma_tp"]

PLAIN_COLS = ["moid", "q", "a", "e", "i", "om", "w", "h", "condition_code"]

BOOL_COLS = ["has_h_sigma", "has_diameter", "has_radar"]

CAT_COLS = ["class"]

ORBITAL = ["moid", "q", "a", "e", "i", "om", "w", "h", "class"]
OBSERVATIONAL = [c for c in LOG_COLS + PLAIN_COLS + BOOL_COLS + CAT_COLS
                 if c not in ORBITAL]


def build_pipeline(use_cols):
    """Build a pipeline restricted to use_cols. Every column must land in a
    branch - a column named nowhere is silently dropped by ColumnTransformer."""
    branches = []

    log = [c for c in LOG_COLS if c in use_cols]
    if log:
        branches.append(("log", Pipeline([
            ("fill", SimpleImputer(strategy="median")),
            ("log", FunctionTransformer(np.log1p)),
            ("scale", StandardScaler()),
        ]), log))

    plain = [c for c in PLAIN_COLS if c in use_cols]
    if plain:
        branches.append(("num", Pipeline([
            ("fill", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]), plain))

    # already 0/1 - nothing to do, but they must be named or they vanish
    flags = [c for c in BOOL_COLS if c in use_cols]
    if flags:
        branches.append(("bool", "passthrough", flags))

    cat = [c for c in CAT_COLS if c in use_cols]
    if cat:
        branches.append(("cat", Pipeline([
            ("fill", SimpleImputer(strategy="most_frequent")),
            ("hot", OneHotEncoder(drop="first", handle_unknown="ignore")),
        ]), cat))

    return Pipeline([
        ("prep", ColumnTransformer(branches)),
        ("model", LogisticRegression(max_iter=1000)),
    ])


def main():
    df = load_data()
    df[BOOL_COLS] = df[BOOL_COLS].astype(int)

    features = df.drop(columns=ID_COLS + [TARGET])
    target = df[TARGET]
    all_cols = list(features.columns)

    print("rows %d   removed %d (%.1f%%)"
          % (len(df), target.sum(), target.mean() * 100))

    X_train, X_test, y_train, y_test = train_test_split(
        features, target, test_size=0.2, stratify=target, random_state=42)

    model = build_pipeline(all_cols)
    model.fit(X_train, y_train)

    p = model.predict_proba(X_test)[:, 1]
    accuracy = float(accuracy_score(y_test, model.predict(X_test)))
    roc_auc = float(roc_auc_score(y_test, p))
    pr_auc = float(average_precision_score(y_test, p))

    baseline = float(y_test.mean())

    print("accuracy %.4f  roc-auc %.4f  pr-auc %.4f  (baseline %.4f)"
          % (accuracy, roc_auc, pr_auc, baseline))

    groups = {}
    for name, cols in [("orbital_only", ORBITAL),
                       ("observational_only", OBSERVATIONAL),
                       ("both", all_cols)]:
        m = build_pipeline(cols)
        m.fit(X_train[cols], y_train)
        groups[name] = round(float(average_precision_score(
            y_test, m.predict_proba(X_test[cols])[:, 1])), 4)
        print("  %-20s pr-auc %.4f" % (name, groups[name]))

    model.fit(features, target)

    joblib.dump(model, os.path.join(HERE, "model.joblib"))

    with open(os.path.join(HERE, "features.json"), "w") as f:
        json.dump({
            "features": all_cols,
            "log": LOG_COLS,
            "plain": PLAIN_COLS,
            "boolean": BOOL_COLS,
            "categorical": CAT_COLS,
            "orbital": ORBITAL,
            "observational": OBSERVATIONAL,
            "target": TARGET,
            "id_columns": ID_COLS,
        }, f, indent=2)

    with open(os.path.join(HERE, "metrics.json"), "w") as f:
        json.dump({
            "model": "LogisticRegression on log1p + scaled features",
            "question": "will an object on the Sentry risk list be removed?",
            "accuracy_test": round(accuracy, 4),
            "roc_auc_test": round(roc_auc, 4),
            "pr_auc_test": round(pr_auc, 4),
            "pr_auc_majority_baseline": round(baseline, 4),
            "pr_auc_by_feature_group": groups,
            "n_rows": int(len(df)),
            "n_removed": int(target.sum()),
            "n_features": len(all_cols),
            "trained_at": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
            "sklearn_version": sklearn.__version__,
        }, f, indent=2)

    reloaded = joblib.load(os.path.join(HERE, "model.joblib"))
    one = features.iloc[[0]]
    same = (reloaded.predict_proba(one)[0, 1] == model.predict_proba(one)[0, 1])
    print("\nsaved to %s" % HERE)
    print("reload check:", same)


if __name__ == "__main__":
    main()