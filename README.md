# PPA-Pilot — ML-Guided Physical Design QoR Automation

**Automation, report parsing, and ML-guided parameter exploration for the GCN accelerator
physical design flow.**

This is Project 2 of a two-part physical design portfolio.
The design-under-implementation lives in the companion
[pd-closurelab-gcn](https://github.com/samarthbs27/pd-closurelab-gcn) repository.

---

## What it does

```
YAML config ──► Innovus APR run (on server)
                       │
                       ▼
               raw reports (timing, power, area, DRC)
                       │
              parse_reports.py
                       │
                       ▼
              results/qor_dataset.csv
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
      plot_qor.py  train_qor_    recommend.py
                   model.py
```

| Script | Purpose |
|---|---|
| `scripts/parse_reports.py` | Parse Innovus post-route reports → CSV row |
| `scripts/plot_qor.py` | Generate PPA tradeoff plots from CSV |
| `scripts/sweep_configs.py` | Generate config grid for parameter sweeps |
| `scripts/train_qor_model.py` | Train ML models on parsed QoR data |
| `scripts/recommend.py` | Recommend next flow config from trained model |

---

## Repository structure

```
ppa-pilot/
├── configs/                  # YAML configs — one per flow variant
│   ├── baseline.yaml         # 714 MHz baseline (optimized_02)
│   ├── high_util.yaml        # Higher utilization target (~65%)
│   ├── relaxed_clock.yaml    # Relaxed clock (1.6 ns / 625 MHz)
│   └── aggressive_clock.yaml # Tight clock (1.0 ns / 1 GHz)
├── scripts/
│   ├── parse_reports.py      # Report parser → CSV
│   ├── plot_qor.py           # QoR plots
│   ├── sweep_configs.py      # Config grid generator
│   ├── train_qor_model.py    # ML training
│   └── recommend.py          # Config recommender
├── reports/
│   └── parsed/               # Per-run parsed summaries (JSON)
├── results/
│   ├── qor_dataset.csv       # Main QoR database
│   └── model_metrics.json    # ML model performance
├── models/                   # Serialized trained models (gitignored)
└── images/
    └── ppa_tradeoff_plots/   # Generated PPA plots
```

---

## Current dataset

| Run | Clock | Setup WNS | Hold WNS | Cell Area | Power | DRC |
|---|---|---|---|---|---|---|
| baseline_01 | 1.4 ns | +0.093 ns | −0.001 ns (3 viol) | 21,409 µm² | 3.156 mW | 9,054 |
| optimized_01 | 1.4 ns | +0.092 ns | −0.000 ns (2 viol) | 21,394 µm² | 3.124 mW | 8,872 |
| optimized_02 | 1.4 ns | +0.094 ns | +0.134 ns (0 viol) | 21,022 µm² | 3.134 mW | ~8,872 |

Design: GCN accelerator · PDK: ASAP7 predictive 7nm RVT · Tool: Cadence Innovus 23.12

---

## Quickstart

### Prerequisites

```bash
pip install pandas numpy scikit-learn matplotlib pyyaml
```

### Parse a new Innovus run

```bash
python scripts/parse_reports.py \
    --run-id my_run_01 \
    --report-dir /path/to/reports/raw/my_run_01 \
    --config configs/baseline.yaml \
    --drc-count 8872 \
    --status complete \
    --notes "description of what changed"
```

### Generate PPA plots

```bash
python scripts/plot_qor.py
# Output: images/ppa_tradeoff_plots/*.png
```

### (After 20+ runs) Train ML models

```bash
python scripts/train_qor_model.py
# Output: models/*, results/model_metrics.json
```

### Get config recommendation

```bash
python scripts/recommend.py --target-clock 1.0 --objective wns --max-drc 0
```

---

## Config knobs tracked

| Parameter | Baseline | Range swept |
|---|---|---|
| `clock_period_ns` | 1.4 | 1.0 – 2.0 |
| `utilization_target` | 0.50 | 0.40 – 0.70 |
| `aspect_ratio` | 1.0 | 0.75 – 1.5 |
| `core_margin_um` | 5 | 3 – 10 |
| `place_density_pct` | ~52 | varies with floorplan |
| `pin_strategy` | west_ctrl_east_out | multiple |
| `cts_buffer_policy` | BUF_INV_curated | multiple |
| `route_strategy` | globalDetail_antenna_fix | multiple |

---

## Known limitations

- Cadence Innovus DRC cap: `drc.rpt` truncates at 1,000 violations.
  Pass `--drc-count` from the Innovus console output for actual count.
- Dataset is currently small (3 runs). ML models are not yet trained.
  More runs needed before `train_qor_model.py` and `recommend.py` produce meaningful output.
- Single timing corner (TT/0.7V/25C). ASAP7 open PDK ships TT only.

---

## References

- [GCN Physical Design Repo](https://github.com/samarthbs27/pd-closurelab-gcn)
- [ASAP7 PDK](https://github.com/The-OpenROAD-Project/asap7)
- [Cadence Innovus Documentation](https://support.cadence.com)
