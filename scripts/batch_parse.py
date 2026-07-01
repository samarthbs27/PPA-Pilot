#!/usr/bin/env python3
"""
batch_parse.py — Parse all sweep run directories into qor_dataset.csv in one shot.

Run from the repo root after untarring sweep reports locally:

    python ppa-pilot/scripts/batch_parse.py --runs-dir GCN/reports/raw/runs/

Auto-detects clock period, utilization, aspect ratio, and congestion effort
from the directory name:
    run_1400_u65_ar100_low  →  clk=1.4 ns  util=0.65  AR=1.0  cong=low

Skips runs already in qor_dataset.csv unless --force is passed.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH  = REPO_ROOT / "results" / "qor_dataset.csv"
PARSER    = REPO_ROOT / "scripts" / "parse_reports.py"


def parse_dir_name(name: str) -> dict | None:
    """Extract flow params from run_CCCC_uUU_arAA_CONG directory name."""
    m = re.fullmatch(r"run_(\d+)_u(\d+)_ar(\d+)_(\w+)", name)
    if not m:
        return None
    clk_ps, util_pct, ar_int, cong = m.groups()
    return {
        "clock_period": int(clk_ps) / 1000,
        "utilization":  int(util_pct) / 100,
        "aspect_ratio": int(ar_int) / 100,
        "cong_effort":  cong,
    }


def parse_drc_count(run_dir: Path) -> str:
    drc_rpt = run_dir / "reports" / "drc.rpt"
    if not drc_rpt.exists():
        return "NA"
    text = drc_rpt.read_text(errors="replace")
    if "IMPVFG-1103" in text:
        return "1000_capped"
    m = re.search(r"Verification Complete\s*:\s*(\d+)\s*Viols", text)
    return m.group(1) if m else "NA"


def already_parsed(run_id: str) -> bool:
    if not CSV_PATH.exists():
        return False
    return any(
        line.startswith(run_id + ",")
        for line in CSV_PATH.read_text().splitlines()
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs-dir", required=True,
                    help="Directory containing sweep run subdirectories")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be parsed without writing anything")
    ap.add_argument("--force", action="store_true",
                    help="Re-parse runs already present in qor_dataset.csv")
    args = ap.parse_args()

    runs_dir = Path(args.runs_dir).resolve()
    if not runs_dir.exists():
        print(f"ERROR: --runs-dir not found: {runs_dir}", file=sys.stderr)
        sys.exit(1)

    candidates = sorted(
        d for d in runs_dir.iterdir()
        if d.is_dir() and d.name.startswith("run_")
    )
    if not candidates:
        print(f"No run_* directories found in {runs_dir}")
        sys.exit(0)

    print(f"\nFound {len(candidates)} run directories in {runs_dir}\n")

    parsed = skipped = failed = 0

    for run_dir in candidates:
        name   = run_dir.name
        params = parse_dir_name(name)

        if params is None:
            print(f"[SKIP]  {name} — name doesn't match run_CCCC_uUU_arAA_CONG pattern")
            skipped += 1
            continue

        if not args.force and already_parsed(name):
            print(f"[SKIP]  {name} — already in qor_dataset.csv")
            skipped += 1
            continue

        status  = "complete" if (run_dir / "reports" / "summary.rpt").exists() else "partial"
        drc     = parse_drc_count(run_dir)

        print(f"[PARSE] {name}")
        print(f"        clk={params['clock_period']}ns  util={params['utilization']}  "
              f"ar={params['aspect_ratio']}  cong={params['cong_effort']}  "
              f"drc={drc}  status={status}")

        if args.dry_run:
            parsed += 1
            continue

        cmd = [
            sys.executable, str(PARSER),
            "--run-id",       name,
            "--report-dir",   str(run_dir),
            "--clock-period", str(params["clock_period"]),
            "--utilization",  str(params["utilization"]),
            "--aspect-ratio", str(params["aspect_ratio"]),
            "--cong-effort",  params["cong_effort"],
            "--drc-count",    drc,
            "--status",       status,
        ]
        ret = subprocess.run(cmd, capture_output=True, text=True)
        if ret.returncode == 0:
            # Print the parser's summary lines (indented)
            for line in ret.stdout.strip().splitlines():
                if not line.startswith("Appended"):
                    print(f"        {line}")
            parsed += 1
        else:
            print(f"        [FAILED] exit={ret.returncode}")
            if ret.stderr:
                print(f"        {ret.stderr.strip()}")
            failed += 1

        print()

    print(f"{'='*50}")
    print(f"Done — parsed: {parsed}  skipped: {skipped}  failed: {failed}")
    print(f"CSV: {CSV_PATH}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
