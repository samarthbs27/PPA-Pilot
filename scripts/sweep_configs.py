#!/usr/bin/env python3
"""
sweep_configs.py - Generate YAML config files for automated PPA sweep runs.

Each config is a variation on the baseline with one or more knobs changed.
Generated configs are tracked in configs/sweep/manifest.csv so previously
generated configs are not duplicated across invocations.

Usage:
    # Grid: all combinations up to --max configs
    python scripts/sweep_configs.py --strategy grid

    # Random: N random samples from the full space
    python scripts/sweep_configs.py --strategy random --n 20 --seed 42

    # Focused: dense sampling near the best known result (optimized_02)
    python scripts/sweep_configs.py --strategy focused

    # Preview without writing files
    python scripts/sweep_configs.py --strategy grid --dry-run

    # List all previously generated sweep configs
    python scripts/sweep_configs.py --list
"""

import argparse
import csv
import itertools
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

REPO_ROOT = Path(__file__).parent.parent
SWEEP_DIR = REPO_ROOT / "configs" / "sweep"
MANIFEST_PATH = SWEEP_DIR / "manifest.csv"

MANIFEST_COLS = [
    "run_id", "config_file", "strategy",
    "clock_period_ns", "utilization_target", "aspect_ratio", "core_margin_um",
    "status", "generated_at",
]

# Base settings inherited by all sweep configs
BASE = {
    "design": "GCN",
    "platform_or_pdk": "ASAP7_predictive_7nm_27R",
    "flow_tool": "Cadence_Innovus_23.12",
    "pin_strategy": "west_ctrl_east_out",
    "macro_strategy": "none",
    "cts_buffer_policy": "BUF_INV_curated",
    "route_strategy": "globalDetail_antenna_fix",
    "hold_io_false_path": True,
}

# Full parameter space for grid/random strategies
FULL_SPACE = {
    "clock_period_ns":    [1.0, 1.2, 1.4, 1.6, 2.0],
    "utilization_target": [0.40, 0.50, 0.55, 0.60, 0.65, 0.70],
    "aspect_ratio":       [0.8, 1.0, 1.2, 1.5],
    "core_margin_um":     [3, 5, 7, 10],
}

# Focused space near optimized_02 (1.4 ns, 50% util, 1.0 AR, 5 um margin)
FOCUSED_SPACE = {
    "clock_period_ns":    [1.2, 1.4, 1.6],
    "utilization_target": [0.45, 0.50, 0.55, 0.60],
    "aspect_ratio":       [0.9, 1.0, 1.1],
    "core_margin_um":     [4, 5, 6],
}


def load_manifest():
    """Return set of existing run_ids from manifest."""
    if not MANIFEST_PATH.exists():
        return {}
    with open(MANIFEST_PATH, newline="") as f:
        return {row["run_id"]: row for row in csv.DictReader(f)}


def append_manifest(rows):
    write_header = not MANIFEST_PATH.exists()
    with open(MANIFEST_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def next_run_index(existing, prefix):
    """Find the next integer index not already used for a given prefix."""
    used = set()
    for rid in existing:
        if rid.startswith(prefix):
            try:
                used.add(int(rid.split("_")[-1]))
            except ValueError:
                pass
    i = 1
    while i in used:
        i += 1
    return i


def make_config(run_id, strategy, params):
    cfg = dict(BASE)
    cfg["run_id_prefix"] = run_id
    cfg.update(params)
    cfg["sweep_strategy"] = strategy
    cfg["sweep_params"] = list(params.keys())
    cfg["notes"] = (
        f"Auto-generated sweep config. "
        f"clock={params['clock_period_ns']} ns, "
        f"util={params['utilization_target']}, "
        f"AR={params['aspect_ratio']}, "
        f"margin={params['core_margin_um']} um."
    )
    return cfg


def write_config(path, cfg, dry_run):
    if dry_run:
        return
    if not HAS_YAML:
        print("ERROR: pyyaml not installed. Run: pip install pyyaml", file=sys.stderr)
        sys.exit(1)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)


def all_combinations(space):
    keys = list(space.keys())
    for values in itertools.product(*[space[k] for k in keys]):
        yield dict(zip(keys, values))


def generate(strategy, space, prefix, existing, max_configs, seed, dry_run):
    combos = list(all_combinations(space))

    if strategy == "random":
        rng = random.Random(seed)
        rng.shuffle(combos)

    # Filter out any combination already in the manifest
    def is_dup(c, existing):
        for row in existing.values():
            try:
                if (
                    float(row["clock_period_ns"]) == c["clock_period_ns"]
                    and float(row["utilization_target"]) == c["utilization_target"]
                    and float(row["aspect_ratio"]) == c["aspect_ratio"]
                    and float(row["core_margin_um"]) == c["core_margin_um"]
                ):
                    return True
            except (ValueError, KeyError):
                pass
        return False

    new_combos = [c for c in combos if not is_dup(c, existing)]
    if not new_combos:
        print("No new configs to generate (all combinations already in manifest).")
        return []

    selected = new_combos[:max_configs]
    idx = next_run_index(existing, prefix)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    written = []
    for params in selected:
        run_id = f"{prefix}_{idx:03d}"
        cfg = make_config(run_id, strategy, params)
        cfg_file = SWEEP_DIR / f"{run_id}.yaml"
        write_config(cfg_file, cfg, dry_run)
        written.append({
            "run_id": run_id,
            "config_file": str(cfg_file.relative_to(REPO_ROOT)),
            "strategy": strategy,
            "clock_period_ns": params["clock_period_ns"],
            "utilization_target": params["utilization_target"],
            "aspect_ratio": params["aspect_ratio"],
            "core_margin_um": params["core_margin_um"],
            "status": "pending",
            "generated_at": now,
        })
        idx += 1

    return written


def cmd_list(existing):
    if not existing:
        print("No sweep configs in manifest yet.")
        return
    print(f"{'run_id':<22} {'clock':>7} {'util':>6} {'AR':>5} {'margin':>7}  {'status':<10}  generated_at")
    print("-" * 80)
    for row in existing.values():
        print(
            f"{row['run_id']:<22} "
            f"{row['clock_period_ns']:>7} "
            f"{row['utilization_target']:>6} "
            f"{row['aspect_ratio']:>5} "
            f"{row['core_margin_um']:>7}  "
            f"{row['status']:<10}  "
            f"{row['generated_at']}"
        )


def main():
    ap = argparse.ArgumentParser(description="Generate PPA sweep YAML configs")
    ap.add_argument("--strategy", choices=["grid", "random", "focused"], default="grid")
    ap.add_argument("--n", type=int, default=20, help="Configs to generate (random strategy)")
    ap.add_argument("--max", type=int, default=50, help="Max configs per invocation (grid/focused)")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed for random strategy")
    ap.add_argument("--out", type=Path, default=None, help="Override output directory (default: configs/sweep)")
    ap.add_argument("--dry-run", action="store_true", help="Preview configs without writing files")
    ap.add_argument("--list", action="store_true", help="Show manifest of existing sweep configs")
    args = ap.parse_args()

    global SWEEP_DIR, MANIFEST_PATH
    if args.out:
        SWEEP_DIR = args.out
        MANIFEST_PATH = SWEEP_DIR / "manifest.csv"

    existing = load_manifest()

    if args.list:
        cmd_list(existing)
        return

    space = FOCUSED_SPACE if args.strategy == "focused" else FULL_SPACE
    max_cfg = args.n if args.strategy == "random" else args.max
    prefix = f"sweep_{args.strategy}"

    total_combos = 1
    for v in space.values():
        total_combos *= len(v)

    print(f"Strategy: {args.strategy}")
    print(f"Parameter space: {total_combos} total combinations")
    print(f"Max to generate: {max_cfg}")
    print(f"Existing in manifest: {len(existing)}")
    if args.dry_run:
        print("DRY RUN — no files will be written\n")

    written = generate(
        args.strategy, space, prefix, existing, max_cfg, args.seed, args.dry_run
    )

    if not written:
        return

    if not args.dry_run:
        append_manifest(written)

    print(f"\n{'run_id':<22} {'clock':>7} {'util':>6} {'AR':>5} {'margin':>7}")
    print("-" * 55)
    for row in written:
        print(
            f"{row['run_id']:<22} "
            f"{row['clock_period_ns']:>7} "
            f"{row['utilization_target']:>6} "
            f"{row['aspect_ratio']:>5} "
            f"{row['core_margin_um']:>7}"
        )

    action = "Would generate" if args.dry_run else "Generated"
    print(f"\n{action} {len(written)} config(s) in {SWEEP_DIR}")
    if not args.dry_run:
        print(f"Manifest updated: {MANIFEST_PATH}")
    print("\nNext steps:")
    print("  1. Copy each config's run_id to the server and launch Innovus with the matching parameters.")
    print("  2. After each run completes, collect reports and run:")
    print("       python scripts/parse_reports.py --run-id <run_id> --report-dir <path> --config configs/sweep/<run_id>.yaml")
    print("  3. Once 10+ rows are in qor_dataset.csv, run:")
    print("       python scripts/train_qor_model.py")


if __name__ == "__main__":
    main()
