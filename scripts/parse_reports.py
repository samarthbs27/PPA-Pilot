#!/usr/bin/env python3
"""
parse_reports.py — Parse Cadence Innovus post-route reports and append a row
to results/qor_dataset.csv.

Usage:
    python scripts/parse_reports.py \\
        --run-id freq_1000_01 \\
        --report-dir /server/path/to/reports/raw/freq_1000 \\
        --config configs/aggressive_clock.yaml \\
        --drc-count 9200 \\
        --status complete \\
        --notes "1 GHz run: setup failed, 318 violations"

The --config YAML file supplies flow metadata (clock period, utilization, etc.).
Any YAML field can be overridden on the command line.

NOTE on DRC count: Innovus caps drc.rpt at 1,000 violations (IMPVFG-1103).
Always pass --drc-count from the Innovus console output:
    "X geometry drc markers, Y antenna drc markers"
"""

import argparse
import csv
import re
import sys
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

REPO_ROOT = Path(__file__).parent.parent
CSV_PATH = REPO_ROOT / "results" / "qor_dataset.csv"

CSV_COLUMNS = [
    "run_id", "design", "platform_or_pdk", "flow_tool", "clock_period_ns",
    "utilization_target", "aspect_ratio", "core_margin_um", "place_density_pct",
    "pin_strategy", "macro_strategy", "cts_buffer_policy", "route_strategy",
    "setup_wns_ns", "setup_tns_ns", "setup_violating_paths",
    "hold_wns_ns", "hold_tns_ns", "hold_violating_paths",
    "max_transition_violations", "max_cap_violations", "max_fanout_violations",
    "cell_area_um2", "core_area_um2", "die_area_um2", "logic_density_pct",
    "instance_count", "buffer_count", "clock_buffer_count",
    "wirelength_um", "drc_count",
    "internal_power_mw", "switching_power_mw", "leakage_power_mw",
    "total_power_mw", "clock_power_mw",
    "runtime_min", "status", "notes",
]


def _f(v):
    """Return float or 'NA'."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return "NA"


def parse_timing_summary(path):
    """
    Parse GCN_postRoute.summary or GCN_postRoute_hold.summary.

    File format (relevant lines):
        |           WNS (ns):|  0.094  |  0.094  |  0.178  |
        |           TNS (ns):|  0.000  |  0.000  |  0.000  |
        |    Violating Paths:|    0    |    0    |    0    |
        |   max_fanout   |    123 (123)     |    -59     |    ...
        Density: 51.804%

    Returns dict with keys: wns, tns, violations, fanout_violations, density.
    The "all" column (first value) is extracted for WNS/TNS/violations.
    """
    result = {}
    if not path or not Path(path).exists():
        return result

    text = Path(path).read_text()

    m = re.search(r'WNS \(ns\):\|\s*([-\d.]+)', text)
    if m:
        result["wns"] = float(m.group(1))

    m = re.search(r'TNS \(ns\):\|\s*([-\d.]+)', text)
    if m:
        result["tns"] = float(m.group(1))

    m = re.search(r'Violating Paths:\|\s*(\d+)', text)
    if m:
        result["violations"] = int(m.group(1))

    # DRV fanout: "| max_fanout | 123 (123) | ..."
    m = re.search(r'max_fanout\s+\|\s+(\d+)\s*\(', text)
    if m:
        result["fanout_violations"] = int(m.group(1))

    m = re.search(r'Density:\s*([\d.]+)%', text)
    if m:
        result["density"] = float(m.group(1))

    return result


def parse_area_report(path, design="GCN"):
    """
    Parse area.rpt.

    Relevant line format:
        GCN                                     10140            21021.794
    (top-level instance has empty module name; indented children have module names)

    Returns dict with instance_count and cell_area_um2.
    """
    result = {}
    if not path or not Path(path).exists():
        return result

    text = Path(path).read_text()

    # Find the top-level line: design name at column 0, then large gap, then count, then area
    m = re.search(r'^' + re.escape(design) + r'\s+(\d+)\s+([\d.]+)', text, re.MULTILINE)
    if m:
        result["instance_count"] = int(m.group(1))
        result["cell_area_um2"] = float(m.group(2))

    return result


def parse_power_report(path):
    """
    Parse power.rpt.

    Relevant lines:
        Total Internal Power:        1.50057429     47.8778%
        Total Switching Power:       1.63248374     52.0866%
        Total Leakage Power:         0.00111531      0.0356%
        Total Power:                 3.13417334
        Clock (Combinational)   0.04479   0.2188   8.697e-06   0.2636   8.412

    Returns dict with internal/switching/leakage/total/clock power in mW.
    """
    result = {}
    if not path or not Path(path).exists():
        return result

    text = Path(path).read_text()

    m = re.search(r'Total Internal Power:\s+([\d.]+)', text)
    if m:
        result["internal_power_mw"] = float(m.group(1))

    m = re.search(r'Total Switching Power:\s+([\d.]+)', text)
    if m:
        result["switching_power_mw"] = float(m.group(1))

    m = re.search(r'Total Leakage Power:\s+([\d.e-]+)', text)
    if m:
        result["leakage_power_mw"] = float(m.group(1))

    m = re.search(r'Total Power:\s+([\d.]+)', text)
    if m:
        result["total_power_mw"] = float(m.group(1))

    # Clock (Combinational) row: internal switching leakage total percentage
    m = re.search(r'Clock \(Combinational\)\s+([\d.e-]+)\s+([\d.e-]+)\s+([\d.e-]+)\s+([\d.e-]+)', text)
    if m:
        result["clock_power_mw"] = float(m.group(4))

    return result


def parse_drc_report(path):
    """
    Parse drc.rpt for violation count.
    Returns (count, capped) where capped=True means Innovus hit the 1000-violation limit.
    Use --drc-count on the CLI to supply the actual count from the Innovus console.
    """
    if not path or not Path(path).exists():
        return None, False

    text = Path(path).read_text()

    capped = "exceeds the Error Limit" in text

    m = re.search(r'Verification Complete\s*:\s*(\d+)\s*Viols', text)
    count = int(m.group(1)) if m else None

    return count, capped


def load_config(config_path):
    if not config_path:
        return {}
    if not HAS_YAML:
        print("WARNING: pyyaml not installed; --config ignored. Install with: pip install pyyaml", file=sys.stderr)
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def main():
    ap = argparse.ArgumentParser(description="Parse Innovus reports → qor_dataset.csv row")
    ap.add_argument("--run-id", required=True, help="Unique run identifier")
    ap.add_argument("--report-dir", required=True, type=Path, help="Directory containing Innovus reports")
    ap.add_argument("--config", type=Path, default=None, help="YAML config file with flow metadata")
    ap.add_argument("--design", default=None)
    ap.add_argument("--pdk", default=None)
    ap.add_argument("--tool", default=None)
    ap.add_argument("--clock-period", type=float, default=None, help="Clock period in ns")
    ap.add_argument("--utilization", type=float, default=None)
    ap.add_argument("--aspect-ratio", type=float, default=None)
    ap.add_argument("--core-margin", type=float, default=None)
    ap.add_argument("--pin-strategy", default=None)
    ap.add_argument("--macro-strategy", default=None)
    ap.add_argument("--cts-policy", default=None)
    ap.add_argument("--route-strategy", default=None)
    ap.add_argument("--drc-count", default=None,
                    help="Actual geometry DRC count from Innovus console (overrides drc.rpt cap)")
    ap.add_argument("--runtime-min", type=float, default=None)
    ap.add_argument("--status", default="complete")
    ap.add_argument("--notes", default="")
    ap.add_argument("--output-csv", type=Path, default=CSV_PATH)
    args = ap.parse_args()

    # Load YAML config for defaults
    cfg = load_config(args.config)

    def get(cli_val, yaml_key, default="NA"):
        if cli_val is not None:
            return cli_val
        return cfg.get(yaml_key, default)

    design = get(args.design, "design", "GCN")
    rdir = args.report_dir

    # Parse reports
    setup = parse_timing_summary(rdir / "GCN_postRoute.summary")
    hold  = parse_timing_summary(rdir / "GCN_postRoute_hold.summary")
    area  = parse_area_report(rdir / "area.rpt", design=design)
    power = parse_power_report(rdir / "power.rpt")
    drc_parsed, drc_capped = parse_drc_report(rdir / "drc.rpt")

    # Resolve DRC count
    if args.drc_count is not None:
        drc_count = args.drc_count
    elif drc_capped:
        print("WARNING: DRC count capped at 1000 in drc.rpt (IMPVFG-1103).", file=sys.stderr)
        print("         Pass --drc-count N from the Innovus console:", file=sys.stderr)
        print('         "X geometry drc markers, Y antenna drc markers"', file=sys.stderr)
        drc_count = "1000_capped"
    else:
        drc_count = drc_parsed if drc_parsed is not None else "NA"

    density = area.get("density", setup.get("density", "NA"))

    row = {
        "run_id":                   args.run_id,
        "design":                   design,
        "platform_or_pdk":          get(args.pdk,           "platform_or_pdk", "ASAP7_predictive_7nm_27R"),
        "flow_tool":                get(args.tool,          "flow_tool",        "Cadence_Innovus_23.12"),
        "clock_period_ns":          get(args.clock_period,  "clock_period_ns"),
        "utilization_target":       get(args.utilization,   "utilization_target"),
        "aspect_ratio":             get(args.aspect_ratio,  "aspect_ratio"),
        "core_margin_um":           get(args.core_margin,   "core_margin_um"),
        "place_density_pct":        density,
        "pin_strategy":             get(args.pin_strategy,  "pin_strategy"),
        "macro_strategy":           get(args.macro_strategy,"macro_strategy"),
        "cts_buffer_policy":        get(args.cts_policy,    "cts_buffer_policy"),
        "route_strategy":           get(args.route_strategy,"route_strategy"),
        "setup_wns_ns":             setup.get("wns", "NA"),
        "setup_tns_ns":             setup.get("tns", "NA"),
        "setup_violating_paths":    setup.get("violations", "NA"),
        "hold_wns_ns":              hold.get("wns", "NA"),
        "hold_tns_ns":              hold.get("tns", "NA"),
        "hold_violating_paths":     hold.get("violations", "NA"),
        "max_transition_violations":"NA",
        "max_cap_violations":       "NA",
        "max_fanout_violations":    setup.get("fanout_violations", "NA"),
        "cell_area_um2":            area.get("cell_area_um2", "NA"),
        "core_area_um2":            "NA",
        "die_area_um2":             "NA",
        "logic_density_pct":        density,
        "instance_count":           area.get("instance_count", "NA"),
        "buffer_count":             "NA",
        "clock_buffer_count":       "NA",
        "wirelength_um":            "NA",
        "drc_count":                drc_count,
        "internal_power_mw":        power.get("internal_power_mw",  "NA"),
        "switching_power_mw":       power.get("switching_power_mw", "NA"),
        "leakage_power_mw":         power.get("leakage_power_mw",   "NA"),
        "total_power_mw":           power.get("total_power_mw",     "NA"),
        "clock_power_mw":           power.get("clock_power_mw",     "NA"),
        "runtime_min":              args.runtime_min if args.runtime_min is not None else "NA",
        "status":                   args.status,
        "notes":                    args.notes,
    }

    # Guard against duplicate run_id
    output_csv = args.output_csv
    if output_csv.exists():
        with open(output_csv, newline="") as f:
            existing_ids = [r["run_id"] for r in csv.DictReader(f)]
        if args.run_id in existing_ids:
            print(f"ERROR: run_id '{args.run_id}' already exists in {output_csv}.", file=sys.stderr)
            print("       Choose a different --run-id or remove the existing row first.", file=sys.stderr)
            sys.exit(1)

    write_header = not output_csv.exists()
    with open(output_csv, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    print(f"Appended run '{args.run_id}' to {output_csv}")
    print(f"  Setup  WNS: {row['setup_wns_ns']} ns  ({row['setup_violating_paths']} violations)")
    print(f"  Hold   WNS: {row['hold_wns_ns']} ns  ({row['hold_violating_paths']} violations)")
    print(f"  Cell area:  {row['cell_area_um2']} um2   instances: {row['instance_count']}")
    print(f"  Power:      {row['total_power_mw']} mW")
    print(f"  DRC count:  {row['drc_count']}")


if __name__ == "__main__":
    main()
