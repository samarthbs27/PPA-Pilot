#!/usr/bin/env python3
"""
parse_reports.py — Parse Cadence Innovus post-route reports and append a row
to results/qor_dataset.csv.

Usage:
    python scripts/parse_reports.py \\
        --run-id freq_1000_01 \\
        --report-dir /server/path/to/reports/raw/freq_1000 \\
        --config configs/freq_1000.yaml \\
        --drc-count 9200 \\
        --status complete \\
        --notes "1 GHz run"

The --config YAML file supplies flow metadata (clock period, utilization, etc.).
Any YAML field can be overridden on the command line.

NOTE on DRC count: Innovus caps drc.rpt at 1,000 violations (IMPVFG-1103).
Always pass --drc-count from the Innovus console output:
    "X geometry drc markers, Y antenna drc markers"

CTS reports (CTS/clock_trees.rpt, CTS/skew_groups.rpt) are parsed automatically
if present under <report-dir>/CTS/. Missing CTS reports produce NA for those columns.
"""

import argparse
import csv
import gzip
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
    "cong_effort", "pin_strategy", "macro_strategy", "cts_buffer_policy", "route_strategy",
    "setup_wns_ns", "setup_tns_ns", "setup_violating_paths",
    "hold_wns_ns", "hold_tns_ns", "hold_violating_paths",
    "max_transition_violations", "max_cap_violations", "max_fanout_violations",
    "cell_area_um2", "core_area_um2", "die_area_um2", "logic_density_pct",
    "instance_count", "buffer_count", "clock_buffer_count",
    # CTS metrics (from CTS/clock_trees.rpt and CTS/skew_groups.rpt)
    "cts_skew_ps", "cts_max_insertion_delay_ps", "cts_max_depth", "cts_wirelength_um",
    "wirelength_um", "drc_count",
    "internal_power_mw", "switching_power_mw", "leakage_power_mw",
    "total_power_mw", "clock_power_mw", "seq_power_mw", "comb_power_mw",
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

    Relevant lines:
        |           WNS (ns):|  0.094  |  0.094  |  0.178  |
        |           TNS (ns):|  0.000  |  0.000  |  0.000  |
        |    Violating Paths:|    0    |    0    |    0    |
        |   max_fanout   |    123 (123)     |    -59     |
        Density: 51.804%

    Returns dict with keys: wns, tns, violations, fanout_violations, density.
    """
    result = {}
    if not path or not Path(path).exists():
        return result

    p = Path(path)
    if p.suffix == ".gz":
        with gzip.open(p, "rt", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    else:
        text = p.read_text()

    m = re.search(r'WNS \(ns\):\|\s*([-\d.]+)', text)
    if m:
        result["wns"] = float(m.group(1))

    m = re.search(r'TNS \(ns\):\|\s*([-\d.]+)', text)
    if m:
        result["tns"] = float(m.group(1))

    m = re.search(r'Violating Paths:\|\s*(\d+)', text)
    if m:
        result["violations"] = int(m.group(1))

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

    Relevant line:
        GCN    10140    21021.794

    Returns dict with instance_count and cell_area_um2.
    """
    result = {}
    if not path or not Path(path).exists():
        return result

    text = Path(path).read_text()

    m = re.search(r'^' + re.escape(design) + r'\s+(\d+)\s+([\d.]+)', text, re.MULTILINE)
    if m:
        result["instance_count"] = int(m.group(1))
        result["cell_area_um2"] = float(m.group(2))

    return result


def parse_power_report(path):
    """
    Parse power.rpt.

    Parses total power breakdown AND sequential/combinational split:
        Total Internal Power:    5.01499343    45.8823%
        Total Switching Power:   5.91284356    54.0968%
        Total Leakage Power:     0.00227843     0.0208%
        Total Power:            10.93011543
        Sequential    1.637  0.1904  0.0003163  1.827  16.72
        Combinational 3.273  5.255   0.00195    8.529  78.04
        Clock (Combinational)  0.1056  0.4678  1.207e-05  0.5734  5.246

    Returns dict with power values in mW.
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

    # Clock (Combinational): internal switching leakage total percentage
    m = re.search(r'Clock \(Combinational\)\s+([\d.e-]+)\s+([\d.e-]+)\s+([\d.e-]+)\s+([\d.e-]+)', text)
    if m:
        result["clock_power_mw"] = float(m.group(4))

    # Sequential row: internal switching leakage total percentage
    m = re.search(r'^Sequential\s+([\d.e-]+)\s+([\d.e-]+)\s+([\d.e-]+)\s+([\d.e-]+)', text, re.MULTILINE)
    if m:
        result["seq_power_mw"] = float(m.group(4))

    # Combinational row: internal switching leakage total percentage
    m = re.search(r'^Combinational\s+([\d.e-]+)\s+([\d.e-]+)\s+([\d.e-]+)\s+([\d.e-]+)', text, re.MULTILINE)
    if m:
        result["comb_power_mw"] = float(m.group(4))

    return result


def parse_summary_report(path):
    """
    Parse summary.rpt for total wirelength and total BUF cell count.

    Wirelength line (near end of file):
        Total wire length: 361760.0120 um

    Buffer count: sum of all BUFx* instance counts in the Standard Cells table.
    Table format:
        BUFx2_ASAP7_75t_R    107    124.8048

    Returns dict with wirelength_um and buffer_count.
    """
    result = {}
    if not path or not Path(path).exists():
        return result

    text = Path(path).read_text()

    m = re.search(r'Total wire length:\s+([\d.]+)\s+um', text)
    if m:
        result["wirelength_um"] = float(m.group(1))

    # Count BUF cells from the Standard Cells in Netlist table only.
    # That table has format: "  CellName  count  area" (two numbers after name).
    # The max_cap table has only one number — so this pattern is specific enough.
    section_m = re.search(r'Standard Cells in Netlist(.*?)(?=\n#\s|\n={10})', text, re.DOTALL)
    if section_m:
        section = section_m.group(1)
        buf_counts = re.findall(r'BUFx\w+\s+(\d+)\s+[\d.]+', section)
        if buf_counts:
            result["buffer_count"] = sum(int(c) for c in buf_counts)

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


def parse_clock_trees(path):
    """
    Parse CTS/clock_trees.rpt.

    Extracts:
        Buffers    43    68.118    27.295     → cts_buf_count (= clock_buffer_count)
        Maximum depth  :  16                 → cts_max_depth
        Total wire length from Clock DAG wire lengths section → cts_wirelength_um

    Returns dict.
    """
    result = {}
    if not path or not Path(path).exists():
        return result

    text = Path(path).read_text()

    m = re.search(r'^Buffers\s+(\d+)', text, re.MULTILINE)
    if m:
        result["clock_buffer_count"] = int(m.group(1))

    m = re.search(r'Maximum depth\s*:\s*(\d+)', text)
    if m:
        result["cts_max_depth"] = int(m.group(1))

    # Total wire length from the "Clock DAG wire lengths" section
    m = re.search(r'Clock DAG wire lengths:.*?Total\s+([\d.]+)', text, re.DOTALL)
    if m:
        result["cts_wirelength_um"] = float(m.group(1))

    return result


def parse_skew_groups(path):
    """
    Parse CTS/skew_groups.rpt for the setup corner (delayCorner_slow:setup.late).

    Relevant line:
        delayCorner_slow:setup.late  clk/common  none  235.3  441.0  340.8  74.9  explicit  *30.0  205.7  46.6%

    Columns: corner | group | id_target | min_id | max_id | avg_id | stddev |
             skew_type | skew_target | skew | occupancy

    Returns dict with cts_skew_ps and cts_max_insertion_delay_ps.
    """
    result = {}
    if not path or not Path(path).exists():
        return result

    text = Path(path).read_text()

    # Match the setup.late row and capture min_id, max_id, skew
    m = re.search(
        r'delayCorner_slow:setup\.late\s+\S+\s+\S+\s+'
        r'([\d.]+)\s+([\d.]+)\s+[\d.]+\s+[\d.]+\s+\S+\s+\*?([\d.]+)\s+([\d.]+)',
        text
    )
    if m:
        result["cts_max_insertion_delay_ps"] = float(m.group(2))
        result["cts_skew_ps"] = float(m.group(4))

    return result


def load_config(config_path):
    if not config_path:
        return {}
    if not HAS_YAML:
        print("WARNING: pyyaml not installed; --config ignored. Install with: pip install pyyaml",
              file=sys.stderr)
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def find_report(rdir, *candidates):
    """Return the first candidate path (relative to rdir) that exists, or None.

    Supports both old flat layout and new run_dir layout:
        Old:  <report-dir>/GCN_postRoute.summary
        New:  <report-dir>/reports/timing/postRoute/GCN_postRoute.summary
    """
    for c in candidates:
        p = rdir / Path(c)
        if p.exists():
            return p
    return None


def main():
    ap = argparse.ArgumentParser(description="Parse Innovus reports → qor_dataset.csv row")
    ap.add_argument("--run-id",      required=True, help="Unique run identifier")
    ap.add_argument("--report-dir",  required=True, type=Path,
                    help="Run directory (runs/run_<clk>_u<util>) or legacy flat report dir")
    ap.add_argument("--config",      type=Path, default=None,
                    help="YAML config file with flow metadata")
    ap.add_argument("--design",      default=None)
    ap.add_argument("--pdk",         default=None)
    ap.add_argument("--tool",        default=None)
    ap.add_argument("--clock-period",type=float, default=None, help="Clock period in ns")
    ap.add_argument("--utilization", type=float, default=None)
    ap.add_argument("--aspect-ratio",type=float, default=None)
    ap.add_argument("--core-margin", type=float, default=None)
    ap.add_argument("--cong-effort",     default=None,
                    help="Placement congestion effort: low | medium | high")
    ap.add_argument("--pin-strategy",   default=None)
    ap.add_argument("--macro-strategy", default=None)
    ap.add_argument("--cts-policy",     default=None)
    ap.add_argument("--route-strategy", default=None)
    ap.add_argument("--drc-count",   default=None,
                    help="Actual geometry DRC count from Innovus console (overrides drc.rpt cap)")
    ap.add_argument("--runtime-min", type=float, default=None)
    ap.add_argument("--status",      default="complete")
    ap.add_argument("--notes",       default="")
    ap.add_argument("--output-csv",  type=Path, default=CSV_PATH)
    args = ap.parse_args()

    cfg = load_config(args.config)

    def get(cli_val, yaml_key, default="NA"):
        if cli_val is not None:
            return cli_val
        return cfg.get(yaml_key, default)

    design = get(args.design, "design", "GCN")
    rdir   = args.report_dir

    # Resolve file paths — support both new run_dir layout and old flat layout.
    # New: runs/run_1400_u50/reports/timing/postRoute/GCN_postRoute.summary
    # Old: reports/raw/freq_1000/GCN_postRoute.summary
    setup_path   = find_report(rdir,
        "reports/timing/postRoute/GCN_postRoute.summary.gz",
        "reports/timing/postRoute/GCN_postRoute.summary",
        "GCN_postRoute.summary")
    hold_path    = find_report(rdir,
        "reports/timing/postRoute/GCN_postRoute_hold.summary.gz",
        "reports/timing/postRoute/GCN_postRoute_hold.summary",
        "GCN_postRoute_hold.summary")
    area_path    = find_report(rdir, "reports/area.rpt",        "area.rpt")
    power_path   = find_report(rdir, "reports/power/power.rpt", "power.rpt")
    summary_path = find_report(rdir, "reports/summary.rpt",     "summary.rpt")
    drc_path     = find_report(rdir, "reports/drc.rpt",         "drc.rpt")
    cts_path     = find_report(rdir, "CTS/clock_trees.rpt",  "clock_trees.rpt")
    skew_path    = find_report(rdir, "CTS/skew_groups.rpt", "skew_groups.rpt")

    # Parse all reports
    setup   = parse_timing_summary(setup_path)
    hold    = parse_timing_summary(hold_path)
    area    = parse_area_report(area_path, design=design)
    power   = parse_power_report(power_path)
    summary = parse_summary_report(summary_path)
    cts     = parse_clock_trees(cts_path)
    skew    = parse_skew_groups(skew_path)
    drc_parsed, drc_capped = parse_drc_report(drc_path)

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

    density = setup.get("density", "NA")

    row = {
        "run_id":                    args.run_id,
        "design":                    design,
        "platform_or_pdk":           get(args.pdk,            "platform_or_pdk", "ASAP7_predictive_7nm_27R"),
        "flow_tool":                 get(args.tool,           "flow_tool",        "Cadence_Innovus_23.12"),
        "clock_period_ns":           get(args.clock_period,   "clock_period_ns"),
        "utilization_target":        get(args.utilization,    "utilization_target"),
        "aspect_ratio":              get(args.aspect_ratio,   "aspect_ratio"),
        "core_margin_um":            get(args.core_margin,    "core_margin_um"),
        "place_density_pct":         density,
        "cong_effort":               get(args.cong_effort,    "cong_effort",   "low"),
        "pin_strategy":              get(args.pin_strategy,   "pin_strategy"),
        "macro_strategy":            get(args.macro_strategy, "macro_strategy"),
        "cts_buffer_policy":         get(args.cts_policy,     "cts_buffer_policy"),
        "route_strategy":            get(args.route_strategy, "route_strategy"),
        "setup_wns_ns":              setup.get("wns",        "NA"),
        "setup_tns_ns":              setup.get("tns",        "NA"),
        "setup_violating_paths":     setup.get("violations", "NA"),
        "hold_wns_ns":               hold.get("wns",         "NA"),
        "hold_tns_ns":               hold.get("tns",         "NA"),
        "hold_violating_paths":      hold.get("violations",  "NA"),
        "max_transition_violations": "NA",
        "max_cap_violations":        "NA",
        "max_fanout_violations":     setup.get("fanout_violations", "NA"),
        "cell_area_um2":             area.get("cell_area_um2",   "NA"),
        "core_area_um2":             "NA",
        "die_area_um2":              "NA",
        "logic_density_pct":         density,
        "instance_count":            area.get("instance_count",   "NA"),
        "buffer_count":              summary.get("buffer_count",   "NA"),
        "clock_buffer_count":        cts.get("clock_buffer_count", "NA"),
        "cts_skew_ps":               skew.get("cts_skew_ps",               "NA"),
        "cts_max_insertion_delay_ps":skew.get("cts_max_insertion_delay_ps", "NA"),
        "cts_max_depth":             cts.get("cts_max_depth",    "NA"),
        "cts_wirelength_um":         cts.get("cts_wirelength_um","NA"),
        "wirelength_um":             summary.get("wirelength_um", "NA"),
        "drc_count":                 drc_count,
        "internal_power_mw":         power.get("internal_power_mw",  "NA"),
        "switching_power_mw":        power.get("switching_power_mw", "NA"),
        "leakage_power_mw":          power.get("leakage_power_mw",   "NA"),
        "total_power_mw":            power.get("total_power_mw",     "NA"),
        "clock_power_mw":            power.get("clock_power_mw",     "NA"),
        "seq_power_mw":              power.get("seq_power_mw",       "NA"),
        "comb_power_mw":             power.get("comb_power_mw",      "NA"),
        "runtime_min":               args.runtime_min if args.runtime_min is not None else "NA",
        "status":                    args.status,
        "notes":                     args.notes,
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
    print(f"  Setup  WNS:    {row['setup_wns_ns']} ns  ({row['setup_violating_paths']} violations)")
    print(f"  Hold   WNS:    {row['hold_wns_ns']} ns  ({row['hold_violating_paths']} violations)")
    print(f"  Cell area:     {row['cell_area_um2']} um2   instances: {row['instance_count']}")
    print(f"  Wirelength:    {row['wirelength_um']} um")
    print(f"  Power:         {row['total_power_mw']} mW  (seq: {row['seq_power_mw']} / comb: {row['comb_power_mw']})")
    print(f"  CTS skew:      {row['cts_skew_ps']} ps   max_id: {row['cts_max_insertion_delay_ps']} ps")
    print(f"  CTS depth:     {row['cts_max_depth']}   cts_wl: {row['cts_wirelength_um']} um")
    print(f"  Buffers:       total={row['buffer_count']}  cts={row['clock_buffer_count']}")
    print(f"  DRC count:     {row['drc_count']}")


if __name__ == "__main__":
    main()
