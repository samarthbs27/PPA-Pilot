# Server Setup and Sweep Execution

Reference for running the 25-run PPA sweep on the ASU server and transferring
results back for local parsing.

---

## Prerequisites

All four synthesized netlists must exist in the synthesis directory before
starting the Innovus sweep:

```
GCN/flow/syn/
├── GCN.1400.syn.v   GCN.1400.syn.sdc    ← 714 MHz   (exists)
├── GCN.1000.syn.v   GCN.1000.syn.sdc    ← 1.0 GHz
├── GCN.0800.syn.v   GCN.0800.syn.sdc    ← 1.25 GHz
└── GCN.0600.syn.v   GCN.0600.syn.sdc    ← 1.67 GHz
```

Run DC synthesis for the three missing clocks before launching the sweep.

---

## Files to Copy to the Server

Only two files need to be copied from the local repo:

| Local path | Copy to (server) |
|---|---|
| `GCN/flow/apr/innovus_flow.tcl` | APR work directory (replaces existing) |
| `ppa-pilot/scripts/run_sweep.py` | anywhere convenient (e.g. APR dir or home) |

Do not overwrite `Default.globals` or `Default.view` — they contain
server-specific paths and are not in this repo.

---

## Two Things to Set in run_sweep.py Before Running

Open `run_sweep.py` and set both path variables at the top:

```python
APR_DIR   = Path("/home/sbsudhar/GCN/flow/apr")          # ← directory with innovus_flow.tcl
SYNTH_DIR = Path("/home/sbsudhar/GCN/flow/syn/results")  # ← directory with GCN.<clk>.syn.v
```

`run_sweep.py` writes `GCN/flow/user_config.tcl` automatically before each run
(one level above the `apr/` directory, which is where `Default.globals` looks for it).
Do not edit `user_config.tcl` manually while the sweep is running.

---

## Server Directory Structure Before Running

```
GCN/flow/
├── user_config.tcl           ← auto-written by run_sweep.py per run (NOT inside apr/)
└── apr/
    ├── innovus_flow.tcl      ← copied from repo (updated run_dir output structure)
    ├── Default.globals       ← already on server (do not overwrite)
    └── Default.view          ← already on server (do not overwrite)

GCN/flow/syn/results/         ← set as SYNTH_DIR
├── GCN.1400.syn.v / .sdc    ← 714 MHz   (exists from previous runs)
├── GCN.1000.syn.v / .sdc    ← 1.0 GHz   (synthesize before sweep)
├── GCN.0800.syn.v / .sdc    ← 1.25 GHz  (synthesize before sweep)
└── GCN.0600.syn.v / .sdc    ← 1.67 GHz  (exists from freq_600 run)
```

---

## Running the Sweep

```bash
# Check the plan without executing anything
python run_sweep.py --dry-run

# Full sweep — run in a terminal inside the NanoHub GUI session
python run_sweep.py

# Resume after an interruption (skips runs with existing summary.rpt)
python run_sweep.py --resume
```

Progress is printed after each run:

```
[01/25] run_1400_u50_ar100_low
  [OK]      42 min  →  runs/run_1400_u50_ar100_low/
[02/25] run_1400_u65_ar100_low
  [FAILED]  38 min  exit=1  check logs/run_1400_u65_ar100_low.log
[03/25] run_1400_u70_ar100_low
  [OK]      47 min  →  runs/run_1400_u70_ar100_low/
```

A failed run is logged and skipped — the sweep continues. Failed runs with
partial reports are still useful ML data points.

---

## Sweep Run Matrix

| # | clk (ps) | util | AR  | cong   | Notes |
|---|---|---|---|---|---|
| 01 | 1400 | 0.50 | 1.0 | low    | baseline |
| 02 | 1400 | 0.65 | 1.0 | low    | util stress |
| 03 | 1400 | 0.70 | 1.0 | low    | util boundary |
| 04 | 1400 | 0.40 | 1.0 | low    | util easy |
| 05 | 1400 | 0.55 | 1.0 | low    | util mid |
| 06 | 1400 | 0.50 | 1.2 | low    | AR tall |
| 07 | 1400 | 0.50 | 0.8 | low    | AR wide |
| 08 | 1400 | 0.50 | 1.5 | low    | AR extreme |
| 09 | 1400 | 0.50 | 1.0 | medium | cong effort |
| 10 | 1400 | 0.50 | 1.0 | high   | cong effort |
| 11 | 1000 | 0.50 | 1.0 | low    | 1.0 GHz |
| 12 | 1000 | 0.40 | 1.0 | low    | |
| 13 | 1000 | 0.55 | 1.0 | low    | |
| 14 | 1000 | 0.65 | 1.0 | low    | |
| 15 | 1000 | 0.70 | 1.0 | low    | |
| 16 | 800  | 0.50 | 1.0 | low    | 1.25 GHz |
| 17 | 800  | 0.40 | 1.0 | low    | |
| 18 | 800  | 0.55 | 1.0 | low    | |
| 19 | 800  | 0.65 | 1.0 | low    | |
| 20 | 800  | 0.70 | 1.0 | low    | |
| 21 | 600  | 0.50 | 1.0 | low    | 1.67 GHz |
| 22 | 600  | 0.40 | 1.0 | low    | |
| 23 | 600  | 0.55 | 1.0 | low    | |
| 24 | 600  | 0.65 | 1.0 | low    | |
| 25 | 600  | 0.70 | 1.0 | low    | |

---

## Server Directory Structure After the Sweep

```
GCN/flow/apr/
├── logs/
│   ├── run_1400_u50_ar100_low.log
│   └── ... (one log per run)
└── runs/
    ├── run_1400_u50_ar100_low/
    │   ├── reports/
    │   │   ├── timing/postRoute/      ← GCN_postRoute.summary (WNS/TNS)
    │   │   ├── power/power.rpt
    │   │   ├── area.rpt
    │   │   ├── drc.rpt
    │   │   └── summary.rpt
    │   ├── CTS/
    │   │   ├── clock_trees.rpt        ← buffer count, depth, wirelength
    │   │   └── skew_groups.rpt        ← skew and insertion delay
    │   ├── GDS/
    │   └── checkpoints/
    └── ... (25 run directories)
```

---

## Transferring Reports to Local Machine

Tar only the files the parser needs — exclude `checkpoints/` and `GDS/`:

```csh
# Single run
tar -czf run_1400_u50_ar100_low_reports.tar.gz \
  runs/run_1400_u50_ar100_low/reports/ \
  runs/run_1400_u50_ar100_low/CTS/clock_trees.rpt \
  runs/run_1400_u50_ar100_low/CTS/skew_groups.rpt

# All 25 runs at once — csh foreach (server uses csh/tcsh, not bash)
foreach d (runs/run_*)
  set name = $d:t
  tar -czf ${name}_reports.tar.gz \
    ${d}/reports/ \
    ${d}/CTS/clock_trees.rpt \
    ${d}/CTS/skew_groups.rpt
end
```

> **Note:** The server shell is csh/tcsh. Bash `for d in runs/*/; do` syntax will fail
> with "for: Command not found". Use `foreach ... end` as shown above.

---

## Parsing Reports Locally

Untar into `GCN/reports/raw/`, then run the parser from the repo root:

```bash
python ppa-pilot/scripts/parse_reports.py \
  --run-id run_1400_u50_ar100_low \
  --report-dir GCN/reports/raw/runs/run_1400_u50_ar100_low \
  --config ppa-pilot/configs/baseline.yaml \
  --drc-count <actual_count_from_console> \
  --status complete
```

The parser appends a row to `ppa-pilot/results/qor_dataset.csv` automatically.
For runs without a dedicated YAML config, pass parameters directly:

```bash
python ppa-pilot/scripts/parse_reports.py \
  --run-id run_1000_u65_ar100_low \
  --report-dir GCN/reports/raw/runs/run_1000_u65_ar100_low \
  --clock-period 1.0 --utilization 0.65 --aspect-ratio 1.0 --cong-effort low \
  --drc-count <count> --status complete
```
