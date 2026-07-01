#!/usr/bin/env python3
"""
recommend.py — Recommend the next Innovus flow config using trained ML models.

Loads trained WNS regressor and timing classifier from models/ and scores a
candidate config grid. Outputs the top-ranked configuration as a YAML snippet
ready to use as user_config.tcl parameters.

Usage:
    python ppa-pilot/scripts/recommend.py
    python ppa-pilot/scripts/recommend.py --target-clock 1.0 --objective wns
    python ppa-pilot/scripts/recommend.py --target-clock 0.8 --objective power --max-drc 0

Options:
    --target-clock FLOAT   Clock period constraint in ns (default: 1.0)
    --objective STR        Optimization goal: wns | power | area (default: wns)
    --max-drc INT          Max acceptable DRC risk score 0–2 (default: 2)
    --top N                Show top N candidates (default: 5)
"""

import argparse
import sys
from pathlib import Path

try:
    import numpy as np
    import pandas as pd
    import joblib
except ImportError as e:
    print(f"ERROR: Missing dependency: {e}")
    print("Install with: pip install numpy pandas scikit-learn joblib")
    sys.exit(1)

REPO_ROOT  = Path(__file__).resolve().parent.parent
MODEL_DIR  = REPO_ROOT / "models"
CSV_PATH   = REPO_ROOT / "results" / "qor_dataset.csv"

CONG_MAP     = {"low": 0, "medium": 1, "high": 2}
CONG_MAP_INV = {v: k for k, v in CONG_MAP.items()}
FEATURES     = ["clock_period_ns", "utilization_target", "aspect_ratio", "cong_effort_enc"]


# -- Candidate grid -------------------------------------------------------------
# Same parameter space as the 25-run sweep, extended with finer granularity.

CANDIDATE_GRID = [
    {"clock_period_ns": clk, "utilization_target": util,
     "aspect_ratio": ar,    "cong_effort_enc": cong_enc}
    for clk  in [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.4]
    for util in [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
    for ar   in [0.8, 1.0, 1.2, 1.5]
    for cong_enc in [0, 1, 2]
]


def load_models() -> dict:
    available = {}
    for name, fname in [
        ("timing_classifier", "timing_classifier.joblib"),
        ("wns_regressor",     "wns_regressor.joblib"),
        ("power_regressor",   "power_regressor.joblib"),
        ("area_regressor",    "area_regressor.joblib"),
    ]:
        path = MODEL_DIR / fname
        if path.exists():
            available[name] = joblib.load(path)
        else:
            available[name] = None
    return available


def load_seen_configs(csv_path: Path) -> set:
    """Return set of (clk, util, ar, cong_enc) already in the dataset."""
    if not csv_path.exists():
        return set()
    df = pd.read_csv(csv_path, na_values=["NA", "na", ""])
    seen = set()
    for _, row in df.iterrows():
        try:
            clk  = float(row["clock_period_ns"])
            util = float(row["utilization_target"])
            ar   = float(row["aspect_ratio"])
            cong = CONG_MAP.get(str(row.get("cong_effort", "low")), 0)
            seen.add((round(clk, 3), round(util, 3), round(ar, 3), cong))
        except (ValueError, TypeError, KeyError):
            continue
    return seen


def score_candidates(models: dict, grid: list, objective: str,
                     target_clock: float) -> pd.DataFrame:
    df = pd.DataFrame(grid)

    # Filter to configs that meet the clock constraint
    df = df[df["clock_period_ns"] <= target_clock + 0.01].copy()

    X = df[FEATURES].values

    # Timing pass probability
    if models["timing_classifier"]:
        proba = models["timing_classifier"].predict_proba(X)
        # With only one class in training data, proba has shape (N, 1)
        df["pass_prob"] = proba[:, 1] if proba.shape[1] > 1 else proba[:, 0]
    else:
        df["pass_prob"] = np.nan

    # Predicted WNS (ps)
    if models["wns_regressor"]:
        df["pred_wns_ps"] = models["wns_regressor"].predict(X)
    else:
        df["pred_wns_ps"] = np.nan

    # Predicted power (mW)
    if models["power_regressor"]:
        df["pred_power_mw"] = models["power_regressor"].predict(X)
    else:
        df["pred_power_mw"] = np.nan

    # Predicted area (µm²)
    if models["area_regressor"]:
        df["pred_area_um2"] = models["area_regressor"].predict(X)
    else:
        df["pred_area_um2"] = np.nan

    # Rank by objective
    if objective == "wns" and "pred_wns_ps" in df.columns:
        df["score"] = df["pred_wns_ps"].fillna(-9999)
        df = df.sort_values("score", ascending=False)
    elif objective == "power" and "pred_power_mw" in df.columns:
        df["score"] = -df["pred_power_mw"].fillna(9999)
        df = df.sort_values("score", ascending=False)
    elif objective == "area" and "pred_area_um2" in df.columns:
        df["score"] = -df["pred_area_um2"].fillna(9999)
        df = df.sort_values("score", ascending=False)
    else:
        df["score"] = df["pass_prob"].fillna(0)
        df = df.sort_values("score", ascending=False)

    df["cong_effort"] = df["cong_effort_enc"].map(CONG_MAP_INV)
    return df.reset_index(drop=True)


def confidence_label(pass_prob) -> str:
    if pd.isna(pass_prob):
        return "unknown"
    if pass_prob >= 0.80:
        return "high"
    if pass_prob >= 0.55:
        return "medium"
    return "low"


def print_recommendation(row: pd.Series, rank: int, seen: set) -> None:
    key = (round(row["clock_period_ns"], 3),
           round(row["utilization_target"], 3),
           round(row["aspect_ratio"], 3),
           int(row["cong_effort_enc"]))
    already = " [already run]" if key in seen else ""

    print(f"\n{'-'*50}")
    print(f"  Rank #{rank}{already}")
    print(f"  clock_period_ns  : {row['clock_period_ns']}")
    print(f"  utilization      : {row['utilization_target']}")
    print(f"  aspect_ratio     : {row['aspect_ratio']}")
    print(f"  cong_effort      : {row['cong_effort']}")
    if not pd.isna(row.get("pred_wns_ps")):
        print(f"  Predicted WNS    : {row['pred_wns_ps']:+.1f} ps")
    if not pd.isna(row.get("pred_power_mw")):
        print(f"  Predicted power  : {row['pred_power_mw']:.3f} mW")
    if not pd.isna(row.get("pred_area_um2")):
        print(f"  Predicted area   : {row['pred_area_um2']:.0f} um2")
    if not pd.isna(row.get("pass_prob")):
        print(f"  Timing pass prob : {row['pass_prob']:.0%}  [{confidence_label(row['pass_prob'])} confidence]")
    print(f"{'-'*50}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target-clock", type=float, default=1.0,
                    help="Clock period constraint in ns (default: 1.0)")
    ap.add_argument("--objective",    default="wns",
                    choices=["wns", "power", "area"],
                    help="Optimization goal (default: wns)")
    ap.add_argument("--max-drc",      type=int, default=2,
                    help="Max DRC risk: 0=none, 1=medium, 2=any (default: 2)")
    ap.add_argument("--top",          type=int, default=5,
                    help="Number of top candidates to show (default: 5)")
    ap.add_argument("--show-seen",    action="store_true",
                    help="Include configs already in the dataset")
    args = ap.parse_args()

    print(f"\nLoading models from {MODEL_DIR}/")
    models = load_models()

    n_loaded = sum(1 for v in models.values() if v is not None)
    if n_loaded == 0:
        print("ERROR: No trained models found. Run train_qor_model.py first.")
        sys.exit(1)

    loaded_names = [k for k, v in models.items() if v is not None]
    print(f"  Loaded: {', '.join(loaded_names)}")

    seen = load_seen_configs(CSV_PATH)
    print(f"  {len(seen)} configs already in dataset")

    print(f"\nObjective : {args.objective}")
    print(f"Clock <=  : {args.target_clock} ns")
    print(f"Candidates: {len(CANDIDATE_GRID)} total grid points")

    ranked = score_candidates(models, CANDIDATE_GRID, args.objective, args.target_clock)

    if not args.show_seen:
        def is_seen(row):
            key = (round(row["clock_period_ns"], 3),
                   round(row["utilization_target"], 3),
                   round(row["aspect_ratio"], 3),
                   int(row["cong_effort_enc"]))
            return key in seen
        unseen = ranked[~ranked.apply(is_seen, axis=1)]
    else:
        unseen = ranked

    if unseen.empty:
        print("\nAll recommended configs are already in the dataset. "
              "Use --show-seen to include them.")
        return

    print(f"\nTop {args.top} recommendations (unseen configs):")
    for i, (_, row) in enumerate(unseen.head(args.top).iterrows(), 1):
        print_recommendation(row, i, seen)

    print(f"\n  user_config.tcl snippet for rank #1:")
    top = unseen.iloc[0]
    print(f"    set clk_period    {int(top['clock_period_ns'] * 1000)}")
    print(f"    set util_target   {top['utilization_target']}")
    print(f"    set aspect_ratio  {top['aspect_ratio']}")
    print(f"    set cong_effort   \"{top['cong_effort']}\"")
    print()


if __name__ == "__main__":
    main()
