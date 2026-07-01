# PPA-Pilot — ML-Guided Physical Design QoR Automation

**Automation, report parsing, and ML-guided parameter exploration for the GCN accelerator
physical design flow.**

This is Project 2 of a two-part physical design portfolio.
The design-under-implementation lives in the companion
[GCN Physical Design repo](https://github.com/samarthbs27/pd-closurelab-gcn).

---

## What it does

```
YAML config / CLI knobs
        │
        ▼
  run_sweep.py  ──►  Innovus APR runs (on server, sequential)
                             │
                    raw reports (timing, power, area, DRC, CTS)
                             │
                    parse_reports.py  or  batch_parse.py
                             │
                             ▼
                  results/qor_dataset.csv
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         plot_qor.py   train_qor_       recommend.py
                        model.py
```

| Script | Purpose |
|---|---|
| `scripts/run_sweep.py` | Launch all 25 sequential Innovus runs on the server |
| `scripts/parse_reports.py` | Parse one Innovus run's reports → one CSV row |
| `scripts/batch_parse.py` | Parse all sweep run directories in one shot |
| `scripts/plot_qor.py` | Generate PPA tradeoff plots from the CSV |
| `scripts/train_qor_model.py` | Train RF/GBR models on parsed QoR data |
| `scripts/recommend.py` | Recommend next flow config from trained models |

For server setup, sweep execution, and report transfer details see
[docs/server_setup.md](docs/server_setup.md).

---

## Repository structure

```
ppa-pilot/
├── configs/                  # YAML configs for named flow variants
│   ├── baseline.yaml
│   └── ...
├── docs/
│   ├── server_setup.md       # Server paths, sweep execution, transfer instructions
│   ├── methodology_report.md # ML dataset, model choices, accuracy
│   └── interview_notes.md    # Talking points with real metrics
├── models/                   # Trained models — gitignored
│   ├── timing_classifier.joblib
│   ├── wns_regressor.joblib
│   ├── power_regressor.joblib
│   └── area_regressor.joblib
├── results/
│   ├── qor_dataset.csv       # Main QoR database (committed)
│   └── model_metrics.json    # LOO CV accuracy / R² for each model
└── scripts/
    ├── run_sweep.py
    ├── parse_reports.py
    ├── batch_parse.py
    ├── plot_qor.py
    ├── train_qor_model.py
    └── recommend.py
```

---

## Current dataset

25-run automated sweep in progress (Cadence Innovus 23.12, ASAP7 predictive 7nm).
8 rows currently in `qor_dataset.csv` (6 manual + 2 sweep sanity runs).

### Sweep matrix (25 runs)

| Phase | Clock | Utilization sweep | AR sweep | Cong sweep | Runs |
|---|---|---|---|---|---|
| 1 | 1.4 ns (714 MHz) | 40/50/55/65/70% | 0.8/1.0/1.2/1.5 | low/medium/high | 10 |
| 2 | 1.0 ns (1.0 GHz) | 40/50/55/65/70% | 1.0 | low | 5 |
| 3 | 0.8 ns (1.25 GHz) | 40/50/55/65/70% | 1.0 | low | 5 |
| 4 | 0.6 ns (1.67 GHz) | 40/50/55/65/70% | 1.0 | low | 5 |

### Frequency Pareto (manual runs — all timing-clean)

| Clock | Setup WNS | Power | Cell area | Instances | Placed density |
|---|---|---|---|---|---|
| 714 MHz (1.4 ns) | +0.094 ns | 3.13 mW | 21,022 µm² | 10,140 | 51.8% |
| 1.0 GHz (1.0 ns) | +0.184 ns | 6.92 mW | 30,047 µm² | 18,831 | 74.0% |
| 1.25 GHz (0.8 ns) | +0.197 ns | 10.93 mW | 35,545 µm² | 23,541 | 87.0% |
| 1.67 GHz (0.6 ns) | +0.169 ns | 16.65 mW | 41,463 µm² | 23,473 | 81.8% |

---

## Quickstart

### Prerequisites

```bash
pip install pandas numpy scikit-learn matplotlib pyyaml joblib
```

### Parse a single run

```bash
python ppa-pilot/scripts/parse_reports.py \
    --run-id run_1400_u50_ar100_low \
    --report-dir GCN/reports/raw/runs/run_1400_u50_ar100_low \
    --clock-period 1.4 --utilization 0.50 --aspect-ratio 1.0 --cong-effort low \
    --drc-count 1000_capped --status complete
```

### Parse all sweep runs at once

```bash
# After untarring all 25 run tarballs into GCN/reports/raw/runs/
python ppa-pilot/scripts/batch_parse.py --runs-dir GCN/reports/raw/runs/

# Dry-run first to check what will be parsed
python ppa-pilot/scripts/batch_parse.py --runs-dir GCN/reports/raw/runs/ --dry-run
```

### Generate PPA plots

```bash
python ppa-pilot/scripts/plot_qor.py
# Output: ppa-pilot/images/ppa_tradeoff_plots/*.png
```

### Train ML models (after 10+ runs)

```bash
python ppa-pilot/scripts/train_qor_model.py
# Output: models/*.joblib  results/model_metrics.json
```

### Get config recommendation

```bash
python ppa-pilot/scripts/recommend.py --target-clock 1.0 --objective wns
python ppa-pilot/scripts/recommend.py --target-clock 0.8 --objective power --top 3
```

---

## ML pipeline

**Features used:** `clock_period_ns`, `utilization_target`, `aspect_ratio`, `cong_effort` (ordinal-encoded)

**Targets:**

| Model | Algorithm | Target | CV method |
|---|---|---|---|
| Timing classifier | RandomForestClassifier | WNS ≥ 0 (pass/fail) | Leave-one-out |
| WNS regressor | RandomForestRegressor | Setup WNS (ps) | Leave-one-out |
| Power regressor | GradientBoostingRegressor | Total power (mW) | Leave-one-out |
| Area regressor | RandomForestRegressor | Cell area (µm²) | Leave-one-out |

**Recommender:** scores all unseen configs in a candidate grid, ranks by predicted WNS / power / area, filters by clock constraint, outputs user_config.tcl snippet.

---

## Config knobs tracked

| Parameter | Range in sweep | Notes |
|---|---|---|
| `clock_period_ns` | 0.6 / 0.8 / 1.0 / 1.4 | 4 Pareto points |
| `utilization_target` | 0.40 / 0.50 / 0.55 / 0.65 / 0.70 | Primary congestion knob |
| `aspect_ratio` | 0.8 / 1.0 / 1.2 / 1.5 | Swept at clk=1400 only |
| `cong_effort` | low / medium / high | Innovus placement effort |
| `core_margin_um` | 5 (fixed) | Not swept |

---

## Known limitations

- **DRC cap:** Innovus `drc.rpt` truncates at 1,000 violations. `batch_parse.py` auto-detects this and records `1000_capped`. Exact count requires the Innovus console log.
- **Single corner:** ASAP7 open PDK ships TT/0.7V/25C only. No SS/FF MMMC.
- **Small dataset:** 25 runs is enough for simple ML but too small for deep generalization. Models are project-scale predictors, not industry-grade.
- **Sweep runs only for ML:** Pre-sweep manual runs (baseline/optimized/freq) have inconsistent flow configs and are excluded from ML training.

---

## References

- [GCN Physical Design Repo](https://github.com/samarthbs27/pd-closurelab-gcn)
- [ASAP7 PDK](https://github.com/The-OpenROAD-Project/asap7)
- [Cadence Innovus Documentation](https://support.cadence.com)
- [scikit-learn](https://scikit-learn.org)
