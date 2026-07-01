# configs — Named Flow Variant Configurations

YAML metadata files for named GCN APR runs. Each file documents the exact
flow parameters used for one named run and its expected results.

These are used when parsing a named run into `qor_dataset.csv`:

```bash
python scripts/parse_reports.py \
    --run-id baseline_01 \
    --report-dir /path/to/reports/raw/baseline \
    --config configs/baseline.yaml \
    --drc-count 9054 --status complete
```

For automated sweep runs (run_1400_u50_ar100_low, etc.), parameters are
passed directly on the CLI by `batch_parse.py` — no config file needed.

---

## Config fields

| Field | Description |
|---|---|
| `clock_period_ns` | Clock period in nanoseconds |
| `clock_period_ps` | Clock period in picoseconds (value for `user_config.tcl`) |
| `utilization_target` | Floorplan utilization target (0.0–1.0) |
| `aspect_ratio` | Die aspect ratio (height/width) |
| `core_margin_um` | Core-to-die margin on all sides |
| `cong_effort` | Innovus placement congestion effort: low / medium / high |
| `route_strategy` | NanoRoute mode descriptor |
| `cts_buffer_policy` | Label for the CCOpt buffer/inverter cell set |
| `pin_strategy` | Pin assignment descriptor |
| `expected.*` | Expected post-route metrics from the actual run |

---

## Configs in this directory

| File | Clock | Util | AR | Notes |
|---|---|---|---|---|
| `baseline.yaml` | 1.4 ns (714 MHz) | 50% | 1.0 | Matches optimized_02 — hold-closed final result |
| `high_util.yaml` | 1.4 ns | 65% | 1.0 | Higher utilization stress point |
| `util_40.yaml` | 1.4 ns | 40% | 1.0 | Low-utilization headroom run |
| `util_55.yaml` | 1.4 ns | 55% | 1.0 | Mid-utilization |
| `util_70.yaml` | 1.4 ns | 70% | 1.0 | High-utilization boundary |
| `ar_080.yaml` | 1.4 ns | 50% | 0.8 | Wide die |
| `ar_120.yaml` | 1.4 ns | 50% | 1.2 | Tall die |
| `ar_150.yaml` | 1.4 ns | 50% | 1.5 | Extreme AR |
| `cong_medium.yaml` | 1.4 ns | 50% | 1.0 | Medium congestion effort |
| `cong_high.yaml` | 1.4 ns | 50% | 1.0 | High congestion effort |
| `relaxed_clock.yaml` | 1.6 ns (625 MHz) | 50% | 1.0 | Relaxed frequency |
| `aggressive_clock.yaml` | 1.0 ns (1.0 GHz) | 50% | 1.0 | 1 GHz target |
| `freq_0800.yaml` | 0.8 ns (1.25 GHz) | 50% | 1.0 | 1.25 GHz Pareto point |
| `freq_0600.yaml` | 0.6 ns (1.67 GHz) | 50% | 1.0 | 1.67 GHz Pareto point |
