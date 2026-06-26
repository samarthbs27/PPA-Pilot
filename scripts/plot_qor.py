#!/usr/bin/env python3
"""
plot_qor.py — Generate PPA tradeoff plots from results/qor_dataset.csv.

Usage:
    python scripts/plot_qor.py
    python scripts/plot_qor.py --csv results/qor_dataset.csv --out images/ppa_tradeoff_plots

Generates:
    timing_wns_by_run.png        — Setup/hold WNS per run (bar)
    power_area_by_run.png        — Power and cell area per run (bar)
    wns_vs_clock_period.png      — Setup WNS vs clock period (scatter)
    power_vs_area.png            — Power vs area colored by run (scatter)
    drc_vs_utilization.png       — DRC count vs utilization target (scatter)
    hold_wns_by_run.png          — Hold WNS per run with pass/fail line (bar)
"""

import argparse
import sys
from pathlib import Path

try:
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np
except ImportError as e:
    print(f"ERROR: Missing dependency: {e}")
    print("Install with: pip install pandas matplotlib numpy")
    sys.exit(1)

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_CSV = REPO_ROOT / "results" / "qor_dataset.csv"
DEFAULT_OUT = REPO_ROOT / "images" / "ppa_tradeoff_plots"

COLORS = {
    "pass": "#2ecc71",
    "warn": "#f39c12",
    "fail": "#e74c3c",
    "neutral": "#3498db",
    "accent": "#9b59b6",
}


def coerce_numeric(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def run_color(row):
    """Color-code bars: green if timing clean, orange if hold violations, red if setup violations."""
    setup_v = row.get("setup_violating_paths", float("nan"))
    hold_v  = row.get("hold_violating_paths",  float("nan"))
    try:
        if float(setup_v) > 0:
            return COLORS["fail"]
        if float(hold_v) > 0:
            return COLORS["warn"]
        return COLORS["pass"]
    except (TypeError, ValueError):
        return COLORS["neutral"]


def save(fig, out_dir, name):
    path = out_dir / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path.name}")


def plot_timing_wns(df, out_dir):
    """Bar chart: setup WNS and hold WNS per run."""
    cols = ["run_id", "setup_wns_ns", "hold_wns_ns"]
    sub = df[cols].dropna(subset=["setup_wns_ns"])
    if sub.empty:
        return

    x = np.arange(len(sub))
    w = 0.35
    fig, ax = plt.subplots(figsize=(max(6, len(sub) * 1.5), 4))
    ax.bar(x - w/2, sub["setup_wns_ns"], w, label="Setup WNS (ns)",
           color=[COLORS["pass"] if v >= 0 else COLORS["fail"] for v in sub["setup_wns_ns"]])
    if "hold_wns_ns" in sub.columns:
        hold_vals = sub["hold_wns_ns"].fillna(0)
        ax.bar(x + w/2, hold_vals, w, label="Hold WNS (ns)",
               color=[COLORS["pass"] if v >= 0 else COLORS["warn"] for v in hold_vals])
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xticks(x)
    ax.set_xticklabels(sub["run_id"], rotation=20, ha="right")
    ax.set_ylabel("WNS (ns)")
    ax.set_title("Setup and Hold WNS by Run")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    save(fig, out_dir, "timing_wns_by_run.png")


def plot_power_area(df, out_dir):
    """Dual-axis bar: total power (left) and cell area (right) per run."""
    sub = df[["run_id", "total_power_mw", "cell_area_um2"]].dropna(subset=["total_power_mw"])
    if sub.empty:
        return

    x = np.arange(len(sub))
    fig, ax1 = plt.subplots(figsize=(max(6, len(sub) * 1.5), 4))
    ax2 = ax1.twinx()

    ax1.bar(x - 0.2, sub["total_power_mw"], 0.35, color=COLORS["accent"], alpha=0.85, label="Power (mW)")
    ax2.bar(x + 0.2, sub["cell_area_um2"], 0.35, color=COLORS["neutral"], alpha=0.85, label="Cell area (µm²)")

    ax1.set_xticks(x)
    ax1.set_xticklabels(sub["run_id"], rotation=20, ha="right")
    ax1.set_ylabel("Total Power (mW)", color=COLORS["accent"])
    ax2.set_ylabel("Cell Area (µm²)", color=COLORS["neutral"])
    ax1.set_title("Power and Area by Run")

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper right")
    ax1.grid(axis="y", alpha=0.3)
    save(fig, out_dir, "power_area_by_run.png")


def plot_wns_vs_clock(df, out_dir):
    """Scatter: setup WNS vs clock period."""
    sub = df[["run_id", "clock_period_ns", "setup_wns_ns"]].dropna()
    if len(sub) < 2:
        print("  Skipping wns_vs_clock_period.png (need >= 2 runs with clock_period_ns)")
        return

    colors = [COLORS["pass"] if v >= 0 else COLORS["fail"] for v in sub["setup_wns_ns"]]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(sub["clock_period_ns"], sub["setup_wns_ns"], c=colors, s=80, zorder=3)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    for _, row in sub.iterrows():
        ax.annotate(row["run_id"], (row["clock_period_ns"], row["setup_wns_ns"]),
                    textcoords="offset points", xytext=(4, 4), fontsize=7)
    ax.set_xlabel("Clock Period (ns)")
    ax.set_ylabel("Setup WNS (ns)")
    ax.set_title("Setup WNS vs Clock Period")
    ax.grid(alpha=0.3)
    pass_patch = mpatches.Patch(color=COLORS["pass"], label="Timing pass (WNS ≥ 0)")
    fail_patch = mpatches.Patch(color=COLORS["fail"], label="Timing fail (WNS < 0)")
    ax.legend(handles=[pass_patch, fail_patch])
    save(fig, out_dir, "wns_vs_clock_period.png")


def plot_power_vs_area(df, out_dir):
    """Scatter: total power vs cell area."""
    sub = df[["run_id", "cell_area_um2", "total_power_mw"]].dropna()
    if sub.empty:
        return

    fig, ax = plt.subplots(figsize=(6, 4))
    sc = ax.scatter(sub["cell_area_um2"], sub["total_power_mw"],
                    c=range(len(sub)), cmap="viridis", s=80, zorder=3)
    for _, row in sub.iterrows():
        ax.annotate(row["run_id"], (row["cell_area_um2"], row["total_power_mw"]),
                    textcoords="offset points", xytext=(4, 4), fontsize=7)
    plt.colorbar(sc, ax=ax, label="Run index")
    ax.set_xlabel("Cell Area (µm²)")
    ax.set_ylabel("Total Power (mW)")
    ax.set_title("Power vs Area (PPA Tradeoff)")
    ax.grid(alpha=0.3)
    save(fig, out_dir, "power_vs_area.png")


def plot_drc_vs_util(df, out_dir):
    """Scatter: DRC count vs utilization target."""
    sub = df[["run_id", "utilization_target", "drc_count"]].copy()
    sub["drc_count"] = pd.to_numeric(sub["drc_count"], errors="coerce")
    sub = sub.dropna(subset=["utilization_target", "drc_count"])
    if sub.empty:
        print("  Skipping drc_vs_utilization.png (no numeric DRC counts)")
        return

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(sub["utilization_target"], sub["drc_count"],
               color=COLORS["fail"], s=80, zorder=3)
    for _, row in sub.iterrows():
        ax.annotate(row["run_id"], (row["utilization_target"], row["drc_count"]),
                    textcoords="offset points", xytext=(4, 4), fontsize=7)
    ax.set_xlabel("Utilization Target")
    ax.set_ylabel("DRC Geometry Violation Count")
    ax.set_title("DRC Count vs Utilization")
    ax.grid(alpha=0.3)
    save(fig, out_dir, "drc_vs_utilization.png")


def main():
    ap = argparse.ArgumentParser(description="Generate PPA tradeoff plots from qor_dataset.csv")
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    if not args.csv.exists():
        print(f"ERROR: CSV not found: {args.csv}")
        sys.exit(1)

    args.out.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.csv)
    numeric_cols = [
        "clock_period_ns", "utilization_target", "aspect_ratio", "core_margin_um",
        "place_density_pct", "setup_wns_ns", "setup_tns_ns", "setup_violating_paths",
        "hold_wns_ns", "hold_tns_ns", "hold_violating_paths",
        "max_fanout_violations", "cell_area_um2", "logic_density_pct",
        "instance_count", "internal_power_mw", "switching_power_mw",
        "leakage_power_mw", "total_power_mw", "clock_power_mw", "runtime_min",
    ]
    df = coerce_numeric(df, numeric_cols)

    print(f"Loaded {len(df)} runs from {args.csv}")
    print(f"Output directory: {args.out}")

    plot_timing_wns(df, args.out)
    plot_power_area(df, args.out)
    plot_wns_vs_clock(df, args.out)
    plot_power_vs_area(df, args.out)
    plot_drc_vs_util(df, args.out)

    print("Done.")


if __name__ == "__main__":
    main()
