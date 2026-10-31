"""
Although this has been explored in a notebook, 
we write here the same components in the form of a pipeline.
This will help keep training the data as new data arrives and fills in the database.
"""

import os
import json
import shutil
import sys
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

PY_FILE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(PY_FILE, "output")
CURRENT = os.path.join(OUTPUT, "current")

ID_COLUMNS = ["spkid", "pdes"]
TARGET = "removed"

LOG_COLS = ["h_sigma", "n_obs_used", "n_del_obs_used", "n_dop_obs_used",
            "data_arc", "days_since_last_obs", "rms",
            "sigma_a", "sigma_e", "sigma_q", "sigma_i", "sigma_w", "sigma_tp"]

PLAIN_COLS = ["moid", "q", "a", "e", "i", "om", "w", "h", "condition_code"]

BOOL_COLS = ["has_h_sigma", "has_diameter", "has_radar"]

CAT_COLS = ["class"]

GATE = 0.95 # a gatekeeper to filter bad performance of model with new incoming data

def build_pipeline():
    prep = ColumnTransformer([
        ("log", Pipeline([("fill", SimpleImputer(strategy="median")), ("log", FunctionTransformer(np.log1p)), ("scale", StandardScaler()),]), LOG_COLS),
        ("num", Pipeline([("fill", SimpleImputer(strategy="median")), ("scale", StandardScaler()),]), PLAIN_COLS),
        ("bool", "passthrough", BOOL_COLS),
        ("cat", Pipeline([("fill", SimpleImputer(strategy="most_frequent")), ("hot", OneHotEncoder(drop="first", handle_unknown="ignore")),]), CAT_COLS),])

    return Pipeline([("prep", prep), ("model", LogisticRegression(max_iter=1000)),])


def current_score():
    path = os.path.join(CURRENT, "metrics.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f).get("pr_auc_test")


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = os.path.join(OUTPUT, "runs", stamp)
    os.makedirs(run_dir, exist_ok=True)

    df = load_data()
    df[BOOL_COLS] = df[BOOL_COLS].astype(int)

    features = df.drop(columns=ID_COLUMNS + [TARGET])
    target = df[TARGET]

    print("rows: %d   positives: %d (%.1f%%)"
          % (len(df), target.sum(), target.mean() * 100))

    X_train, X_test, y_train, y_test = train_test_split(features, target, test_size=0.2, stratify=target, random_state=42)

    model = build_pipeline()
    model.fit(X_train, y_train)

    p = model.predict_proba(X_test)[:, 1]
    pr_auc = float(average_precision_score(y_test, p))
    roc_auc = float(roc_auc_score(y_test, p))
    accuracy = float(accuracy_score(y_test, model.predict(X_test)))

    base_rate = float(y_test.mean())

    print("accuracy %.4f   roc-auc %.4f   pr-auc %.4f   (baseline %.4f)" % (accuracy, roc_auc, pr_auc, base_rate))

    model.fit(features, target)

    joblib.dump(model, os.path.join(run_dir, "model.joblib"))

    with open(os.path.join(run_dir, "features.json"), "w") as f:
        json.dump({
            "features": list(features.columns),
            "log": LOG_COLS,
            "plain": PLAIN_COLS,
            "boolean": BOOL_COLS,
            "categorical": CAT_COLS,
            "target": TARGET,
            "id_columns": ID_COLUMNS,
        }, f, indent=2)

    metrics = {
        "model": "LogisticRegression on log1p + scaled features",
        "accuracy_test": round(accuracy, 4),
        "roc_auc_test": round(roc_auc, 4),
        "pr_auc_test": round(pr_auc, 4),
        "pr_auc_majority_baseline": round(base_rate, 4),
        "n_rows": int(len(df)),
        "n_positives": int(target.sum()),
        "trained_at": stamp,
        "sklearn_version": sklearn.__version__,
    }
    with open(os.path.join(run_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    with open(os.path.join(run_dir, "VERSION"), "w") as f:
        f.write(stamp + "\n")

    previous = current_score()
    if previous is None:
        promote, why = True, "no model promoted yet"
    elif pr_auc >= GATE * previous:
        promote, why = True, "%.4f >= %.2f x %.4f" % (pr_auc, GATE, previous)
    else:
        promote, why = False, "%.4f < %.2f x %.4f" % (pr_auc, GATE, previous)

    if promote:
        if os.path.exists(CURRENT):
            shutil.rmtree(CURRENT)
        shutil.copytree(run_dir, CURRENT)
        print("PROMOTED (%s)" % why)
    else:
        print("NOT PROMOTED (%s) - current/ unchanged, run kept in %s"
              % (why, run_dir))


if __name__ == "__main__":
    main()