#!/usr/bin/env python3
"""
plot_qor.py — Generate PPA tradeoff plots from qor_dataset.csv.

Usage (from repo root):
    python ppa-pilot/scripts/plot_qor.py
    python ppa-pilot/scripts/plot_qor.py --sweep-only
    python ppa-pilot/scripts/plot_qor.py --csv ppa-pilot/results/qor_dataset.csv

Output: images/ppa_tradeoff_plots/*.png
"""

import argparse
import sys
from pathlib import Path

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np
    import pandas as pd
except ImportError as e:
    print(f"ERROR: Missing dependency: {e}")
    print("Install with: pip install pandas matplotlib numpy")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH  = REPO_ROOT / "results" / "qor_dataset.csv"
PLOT_DIR  = REPO_ROOT / "images" / "ppa_tradeoff_plots"

CLK_COLORS = {0.6: "#d62728", 0.8: "#ff7f0e", 1.0: "#1f77b4", 1.4: "#2ca02c"}
CLK_LABELS = {0.6: "1.67 GHz", 0.8: "1.25 GHz", 1.0: "1.0 GHz", 1.4: "714 MHz"}


def load(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, na_values=["NA", "na", ""])

    # Convert DRC: "1000_capped" → 1001 (numeric sentinel for ">1000")
    def parse_drc(val):
        if pd.isna(val):
            return np.nan
        s = str(val).strip()
        if "capped" in s.lower():
            return 1001.0
        try:
            return float(s)
        except ValueError:
            return np.nan

    numeric_cols = [
        "clock_period_ns", "utilization_target", "aspect_ratio",
        "setup_wns_ns", "setup_tns_ns", "setup_violating_paths",
        "hold_wns_ns", "hold_tns_ns", "hold_violating_paths",
        "cell_area_um2", "instance_count", "wirelength_um",
        "total_power_mw", "internal_power_mw", "switching_power_mw",
        "cts_skew_ps", "cts_max_insertion_delay_ps", "cts_max_depth",
        "place_density_pct", "buffer_count", "clock_buffer_count",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["drc_numeric"] = df["drc_count"].apply(parse_drc)
    return df


def sweep_only(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["run_id"].str.startswith("run_")].copy()


def save(fig: plt.Figure, name: str, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / name, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  {name}")


# ── Individual plot functions ──────────────────────────────────────────────────

def plot_wns_by_run(df: pd.DataFrame, out: Path) -> None:
    sub = df.dropna(subset=["setup_wns_ns"]).copy()
    if sub.empty:
        return
    x = np.arange(len(sub))
    w = 0.35
    fig, ax = plt.subplots(figsize=(max(7, len(sub) * 1.2), 4))
    setup_colors = ["#2ca02c" if v >= 0 else "#d62728" for v in sub["setup_wns_ns"]]
    ax.bar(x - w/2, sub["setup_wns_ns"] * 1000, w, color=setup_colors, label="Setup WNS")
    if "hold_wns_ns" in sub.columns:
        hold_vals = sub["hold_wns_ns"].fillna(0) * 1000
        hold_colors = ["#2ca02c" if v >= 0 else "#ff7f0e" for v in hold_vals]
        ax.bar(x + w/2, hold_vals, w, color=hold_colors, label="Hold WNS")
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xticks(x)
    ax.set_xticklabels(sub["run_id"], rotation=30, ha="right", fontsize=7)
    ax.set_ylabel("WNS (ps)")
    ax.set_title("Setup and Hold WNS by Run")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    save(fig, "timing_wns_by_run.png", out)


def plot_wns_vs_utilization(df: pd.DataFrame, out: Path) -> None:
    sub = df.dropna(subset=["setup_wns_ns", "utilization_target"]).copy()
    if sub.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 5))
    for clk, grp in sub.groupby("clock_period_ns"):
        color = CLK_COLORS.get(clk, "gray")
        label = CLK_LABELS.get(clk, f"{clk} ns")
        ax.scatter(grp["utilization_target"] * 100, grp["setup_wns_ns"] * 1000,
                   c=color, label=label, s=80, zorder=3)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--", label="Timing boundary")
    ax.set_xlabel("Utilization target (%)")
    ax.set_ylabel("Setup WNS (ps)")
    ax.set_title("Setup WNS vs Utilization")
    ax.legend(title="Clock")
    ax.grid(True, alpha=0.3)
    save(fig, "wns_vs_utilization.png", out)


def plot_wns_vs_clock(df: pd.DataFrame, out: Path) -> None:
    sub = df.dropna(subset=["setup_wns_ns", "clock_period_ns"]).copy()
    if len(sub) < 2:
        return
    fig, ax = plt.subplots(figsize=(8, 5))
    for util, grp in sub.groupby("utilization_target"):
        grp_s = grp.sort_values("clock_period_ns")
        ax.plot(grp_s["clock_period_ns"], grp_s["setup_wns_ns"] * 1000,
                marker="o", label=f"util={int(util*100)}%")
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Clock period (ns)")
    ax.set_ylabel("Setup WNS (ps)")
    ax.set_title("Timing Margin vs Clock Period")
    ax.invert_xaxis()
    ax.set_xticks([0.6, 0.8, 1.0, 1.4])
    ax.set_xticklabels(["0.6\n(1.67 GHz)", "0.8\n(1.25 GHz)", "1.0\n(1.0 GHz)", "1.4\n(714 MHz)"])
    ax.legend(title="Utilization")
    ax.grid(True, alpha=0.3)
    save(fig, "wns_vs_clock_period.png", out)


def plot_power_vs_area(df: pd.DataFrame, out: Path) -> None:
    sub = df.dropna(subset=["total_power_mw", "cell_area_um2"]).copy()
    if sub.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 5))
    for clk, grp in sub.groupby("clock_period_ns"):
        color = CLK_COLORS.get(clk, "gray")
        label = CLK_LABELS.get(clk, f"{clk} ns")
        ax.scatter(grp["cell_area_um2"] / 1000, grp["total_power_mw"],
                   c=color, label=label, s=80, zorder=3)
    ax.set_xlabel("Cell area (× 10³ µm²)")
    ax.set_ylabel("Total power (mW)")
    ax.set_title("Power vs Area Pareto")
    ax.legend(title="Clock")
    ax.grid(True, alpha=0.3)
    save(fig, "power_vs_area.png", out)


def plot_power_vs_clock(df: pd.DataFrame, out: Path) -> None:
    sub = df.dropna(subset=["total_power_mw", "clock_period_ns"]).copy()
    if len(sub) < 2:
        return
    fig, ax = plt.subplots(figsize=(7, 5))
    for util, grp in sub.groupby("utilization_target"):
        grp_s = grp.sort_values("clock_period_ns")
        ax.plot(grp_s["clock_period_ns"], grp_s["total_power_mw"],
                marker="o", label=f"util={int(util*100)}%")
    ax.set_xlabel("Clock period (ns)")
    ax.set_ylabel("Total power (mW)")
    ax.set_title("Power vs Clock Period")
    ax.invert_xaxis()
    ax.set_xticks([0.6, 0.8, 1.0, 1.4])
    ax.set_xticklabels(["0.6\n(1.67 GHz)", "0.8\n(1.25 GHz)", "1.0\n(1.0 GHz)", "1.4\n(714 MHz)"])
    ax.legend(title="Utilization")
    ax.grid(True, alpha=0.3)
    save(fig, "power_vs_clock.png", out)


def plot_power_area_by_run(df: pd.DataFrame, out: Path) -> None:
    sub = df.dropna(subset=["total_power_mw"]).copy()
    if sub.empty:
        return
    x = np.arange(len(sub))
    fig, ax1 = plt.subplots(figsize=(max(7, len(sub) * 1.2), 4))
    ax2 = ax1.twinx()
    ax1.bar(x - 0.2, sub["total_power_mw"], 0.35, color="#9b59b6", alpha=0.85, label="Power (mW)")
    if "cell_area_um2" in sub.columns:
        area_vals = sub["cell_area_um2"].fillna(0)
        ax2.bar(x + 0.2, area_vals, 0.35, color="#3498db", alpha=0.85, label="Area (µm²)")
    ax1.set_xticks(x)
    ax1.set_xticklabels(sub["run_id"], rotation=30, ha="right", fontsize=7)
    ax1.set_ylabel("Total Power (mW)", color="#9b59b6")
    ax2.set_ylabel("Cell Area (µm²)", color="#3498db")
    ax1.set_title("Power and Area by Run")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left")
    ax1.grid(axis="y", alpha=0.3)
    save(fig, "power_area_by_run.png", out)


def plot_drc_vs_utilization(df: pd.DataFrame, out: Path) -> None:
    sub = df.dropna(subset=["drc_numeric", "utilization_target"]).copy()
    if sub.empty:
        print("  [SKIP] drc_vs_utilization — no numeric DRC data")
        return
    fig, ax = plt.subplots(figsize=(8, 5))
    for clk, grp in sub.groupby("clock_period_ns"):
        color = CLK_COLORS.get(clk, "gray")
        label = CLK_LABELS.get(clk, f"{clk} ns")
        ax.scatter(grp["utilization_target"] * 100, grp["drc_numeric"],
                   c=color, label=label, s=80, zorder=3)
    ax.axhline(1001, color="red", linewidth=0.8, linestyle=":",
               label=">1000 cap")
    ax.set_xlabel("Utilization target (%)")
    ax.set_ylabel("DRC count  (1001 = >1000 cap)")
    ax.set_title("DRC Count vs Utilization")
    ax.legend(title="Clock")
    ax.grid(True, alpha=0.3)
    save(fig, "drc_vs_utilization.png", out)


def plot_cts_skew_vs_clock(df: pd.DataFrame, out: Path) -> None:
    sub = df.dropna(subset=["cts_skew_ps", "clock_period_ns"]).copy()
    if sub.empty:
        print("  [SKIP] cts_skew_vs_clock — no CTS data")
        return
    fig, ax = plt.subplots(figsize=(7, 5))
    for util, grp in sub.groupby("utilization_target"):
        grp_s = grp.sort_values("clock_period_ns")
        ax.plot(grp_s["clock_period_ns"], grp_s["cts_skew_ps"],
                marker="o", label=f"util={int(util*100)}%")
    ax.set_xlabel("Clock period (ns)")
    ax.set_ylabel("CTS skew (ps)")
    ax.set_title("CTS Skew vs Clock Period")
    ax.invert_xaxis()
    ax.grid(True, alpha=0.3)
    ax.legend(title="Utilization")
    save(fig, "cts_skew_vs_clock.png", out)


def plot_area_vs_utilization(df: pd.DataFrame, out: Path) -> None:
    sub = df.dropna(subset=["cell_area_um2", "utilization_target"]).copy()
    if sub.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 5))
    for clk, grp in sub.groupby("clock_period_ns"):
        color = CLK_COLORS.get(clk, "gray")
        label = CLK_LABELS.get(clk, f"{clk} ns")
        ax.scatter(grp["utilization_target"] * 100, grp["cell_area_um2"] / 1000,
                   c=color, label=label, s=80, zorder=3)
    ax.set_xlabel("Utilization target (%)")
    ax.set_ylabel("Cell area (× 10³ µm²)")
    ax.set_title("Cell Area vs Utilization")
    ax.legend(title="Clock")
    ax.grid(True, alpha=0.3)
    save(fig, "area_vs_utilization.png", out)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv",        default=str(CSV_PATH), help="Path to qor_dataset.csv")
    ap.add_argument("--out",        default=str(PLOT_DIR),  help="Output directory for PNGs")
    ap.add_argument("--sweep-only", action="store_true",
                    help="Only plot automated sweep rows (run_id starts with 'run_')")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    out_dir  = Path(args.out)

    if not csv_path.exists():
        print(f"ERROR: CSV not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    df = load(csv_path)
    print(f"Loaded {len(df)} rows from {csv_path}")

    if args.sweep_only:
        df = sweep_only(df)
        print(f"  Filtered to {len(df)} sweep rows (--sweep-only)")

    if df.empty:
        print("No data to plot.")
        return

    print(f"\nGenerating plots -> {out_dir}/")
    plot_wns_by_run(df, out_dir)
    plot_wns_vs_utilization(df, out_dir)
    plot_wns_vs_clock(df, out_dir)
    plot_power_vs_area(df, out_dir)
    plot_power_vs_clock(df, out_dir)
    plot_power_area_by_run(df, out_dir)
    plot_drc_vs_utilization(df, out_dir)
    plot_cts_skew_vs_clock(df, out_dir)
    plot_area_vs_utilization(df, out_dir)
    print("\nDone.")


if __name__ == "__main__":
    main()
