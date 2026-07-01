#!/usr/bin/env python3
"""
train_qor_model.py — Train ML models on the PPA sweep QoR dataset.

Reads qor_dataset.csv, trains Random Forest models to predict:
  - Timing pass/fail (WNS >= 0)
  - Setup WNS
  - Total power
  - Cell area

Uses leave-one-out CV (small dataset). Saves metrics to results/model_metrics.json
and trained models to models/.

Usage (from repo root):
    python ppa-pilot/scripts/train_qor_model.py
    python ppa-pilot/scripts/train_qor_model.py --min-rows 10
"""

import argparse
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestClassifier, RandomForestRegressor
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import (accuracy_score, f1_score, mean_absolute_error,
                                  mean_squared_error, r2_score)
    from sklearn.model_selection import LeaveOneOut, cross_val_predict
    import joblib
except ImportError as e:
    print(f"ERROR: Missing dependency: {e}")
    print("Install with: pip install pandas numpy scikit-learn matplotlib joblib")
    sys.exit(1)

REPO_ROOT   = Path(__file__).resolve().parent.parent
CSV_PATH    = REPO_ROOT / "results" / "qor_dataset.csv"
MODEL_DIR   = REPO_ROOT / "models"
METRICS_OUT = REPO_ROOT / "results" / "model_metrics.json"
PLOT_DIR    = REPO_ROOT / "images" / "ppa_tradeoff_plots"

CONG_MAP = {"low": 0, "medium": 1, "high": 2}

FEATURES = ["clock_period_ns", "utilization_target", "aspect_ratio", "cong_effort_enc"]

TARGETS = {
    "timing_pass":   {"type": "classifier", "col": None},        # derived from setup_wns_ns
    "setup_wns_ps":  {"type": "regressor",  "col": "setup_wns_ns", "scale": 1000},
    "total_power_mw":{"type": "regressor",  "col": "total_power_mw", "scale": 1},
    "cell_area_um2": {"type": "regressor",  "col": "cell_area_um2", "scale": 1},
}


def load_and_prepare(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, na_values=["NA", "na", ""])

    numeric_cols = [
        "clock_period_ns", "utilization_target", "aspect_ratio",
        "setup_wns_ns", "total_power_mw", "cell_area_um2",
        "cts_skew_ps", "instance_count", "wirelength_um",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["cong_effort_enc"] = df["cong_effort"].map(CONG_MAP).fillna(0).astype(int)
    df["timing_pass"]     = (df["setup_wns_ns"] >= 0).astype(int)
    df["setup_wns_ps"]    = df["setup_wns_ns"] * 1000

    # Use only sweep runs (consistent flow, same constraints)
    df = df[df["run_id"].str.startswith("run_")].copy()
    return df


def check_features(df: pd.DataFrame, min_rows: int) -> pd.DataFrame:
    sub = df.dropna(subset=FEATURES).copy()
    if len(sub) < min_rows:
        print(f"  Only {len(sub)} complete rows (need {min_rows}). "
              f"Run the full sweep first.")
        sys.exit(0)
    return sub


def loo_score_regressor(model, X: np.ndarray, y: np.ndarray) -> dict:
    loo   = LeaveOneOut()
    preds = cross_val_predict(model, X, y, cv=loo)
    return {
        "r2":   round(float(r2_score(y, preds)), 4),
        "mae":  round(float(mean_absolute_error(y, preds)), 4),
        "rmse": round(float(np.sqrt(mean_squared_error(y, preds))), 4),
    }


def loo_score_classifier(model, X: np.ndarray, y: np.ndarray) -> dict:
    loo   = LeaveOneOut()
    preds = cross_val_predict(model, X, y, cv=loo)
    return {
        "accuracy": round(float(accuracy_score(y, preds)), 4),
        "f1":       round(float(f1_score(y, preds, zero_division=0)), 4),
    }


def plot_predicted_vs_actual(y_true, y_pred, title: str, units: str, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(y_true, y_pred, s=60, alpha=0.8, zorder=3)
    lims = [min(min(y_true), min(y_pred)), max(max(y_true), max(y_pred))]
    ax.plot(lims, lims, "k--", linewidth=0.8, label="Perfect prediction")
    ax.set_xlabel(f"Actual ({units})")
    ax.set_ylabel(f"Predicted ({units})")
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3)
    out.mkdir(parents=True, exist_ok=True)
    fname = title.lower().replace(" ", "_").replace("/", "_") + "_loo.png"
    fig.savefig(out / fname, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Plot: {fname}")


def plot_feature_importance(model, feature_names: list, title: str, out: Path) -> None:
    importances = model.feature_importances_
    indices     = np.argsort(importances)[::-1]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(range(len(importances)), importances[indices], color="#3498db")
    ax.set_xticks(range(len(importances)))
    ax.set_xticklabels([feature_names[i] for i in indices], rotation=20, ha="right")
    ax.set_ylabel("Importance")
    ax.set_title(f"Feature Importance — {title}")
    ax.grid(axis="y", alpha=0.3)
    out.mkdir(parents=True, exist_ok=True)
    fname = f"feat_importance_{title.lower().replace(' ', '_')}.png"
    fig.savefig(out / fname, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Plot: {fname}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv",      default=str(CSV_PATH))
    ap.add_argument("--min-rows", type=int, default=10,
                    help="Minimum complete rows required to train (default: 10)")
    ap.add_argument("--no-save",  action="store_true",
                    help="Skip saving models to disk")
    args = ap.parse_args()

    print(f"Loading: {args.csv}")
    df  = load_and_prepare(Path(args.csv))
    sub = check_features(df, args.min_rows)

    print(f"Training on {len(sub)} sweep rows  |  features: {FEATURES}\n")
    X = sub[FEATURES].values

    metrics = {"n_rows": len(sub), "features": FEATURES, "models": {}}

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # --Timing classifier --──────────────────────────────────────────────────
    print("--Timing pass/fail classifier --")
    y_cls = sub["timing_pass"].values
    clf   = RandomForestClassifier(n_estimators=200, random_state=42)
    clf.fit(X, y_cls)
    cv_cls = loo_score_classifier(clf, X, y_cls)
    print(f"   LOO accuracy: {cv_cls['accuracy']:.3f}   F1: {cv_cls['f1']:.3f}")
    metrics["models"]["timing_classifier"] = cv_cls
    plot_feature_importance(clf, FEATURES, "Timing Classifier", PLOT_DIR)
    if not args.no_save:
        joblib.dump(clf, MODEL_DIR / "timing_classifier.joblib")

    # --Setup WNS regressor --────────────────────────────────────────────────
    print("\n--Setup WNS regressor --")
    wns_sub = sub.dropna(subset=["setup_wns_ps"])
    if len(wns_sub) >= args.min_rows:
        X_w  = wns_sub[FEATURES].values
        y_w  = wns_sub["setup_wns_ps"].values
        rfr  = RandomForestRegressor(n_estimators=200, random_state=42)
        rfr.fit(X_w, y_w)
        cv_w = loo_score_regressor(rfr, X_w, y_w)
        print(f"   LOO R2: {cv_w['r2']:.3f}   MAE: {cv_w['mae']:.1f} ps   RMSE: {cv_w['rmse']:.1f} ps")
        metrics["models"]["setup_wns_regressor"] = cv_w
        loo_preds = cross_val_predict(rfr, X_w, y_w, cv=LeaveOneOut())
        plot_predicted_vs_actual(y_w, loo_preds, "Setup WNS Regressor", "ps", PLOT_DIR)
        plot_feature_importance(rfr, FEATURES, "Setup WNS", PLOT_DIR)
        if not args.no_save:
            joblib.dump(rfr, MODEL_DIR / "wns_regressor.joblib")
    else:
        print(f"   Skipped — only {len(wns_sub)} rows with WNS data")

    # --Power regressor --────────────────────────────────────────────────────
    print("\n--Total power regressor --")
    pwr_sub = sub.dropna(subset=["total_power_mw"])
    if len(pwr_sub) >= args.min_rows:
        X_p  = pwr_sub[FEATURES].values
        y_p  = pwr_sub["total_power_mw"].values
        gbr  = GradientBoostingRegressor(n_estimators=200, random_state=42)
        gbr.fit(X_p, y_p)
        cv_p = loo_score_regressor(gbr, X_p, y_p)
        print(f"   LOO R2: {cv_p['r2']:.3f}   MAE: {cv_p['mae']:.3f} mW   RMSE: {cv_p['rmse']:.3f} mW")
        metrics["models"]["power_regressor"] = cv_p
        loo_preds = cross_val_predict(gbr, X_p, y_p, cv=LeaveOneOut())
        plot_predicted_vs_actual(y_p, loo_preds, "Power Regressor", "mW", PLOT_DIR)
        if not args.no_save:
            joblib.dump(gbr, MODEL_DIR / "power_regressor.joblib")
    else:
        print(f"   Skipped — only {len(pwr_sub)} rows with power data")

    # --Area regressor --─────────────────────────────────────────────────────
    print("\n--Cell area regressor --")
    area_sub = sub.dropna(subset=["cell_area_um2"])
    if len(area_sub) >= args.min_rows:
        X_a  = area_sub[FEATURES].values
        y_a  = area_sub["cell_area_um2"].values
        arf  = RandomForestRegressor(n_estimators=200, random_state=42)
        arf.fit(X_a, y_a)
        cv_a = loo_score_regressor(arf, X_a, y_a)
        print(f"   LOO R2: {cv_a['r2']:.3f}   MAE: {cv_a['mae']:.0f} um2   RMSE: {cv_a['rmse']:.0f} um2")
        metrics["models"]["area_regressor"] = cv_a
        loo_preds = cross_val_predict(arf, X_a, y_a, cv=LeaveOneOut())
        plot_predicted_vs_actual(y_a, loo_preds, "Area Regressor", "µm²", PLOT_DIR)
        if not args.no_save:
            joblib.dump(arf, MODEL_DIR / "area_regressor.joblib")
    else:
        print(f"   Skipped — only {len(area_sub)} rows with area data")

    # --Save metrics --───────────────────────────────────────────────────────
    METRICS_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(METRICS_OUT, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nMetrics saved: {METRICS_OUT}")
    if not args.no_save:
        print(f"Models saved:  {MODEL_DIR}/")


if __name__ == "__main__":
    main()
