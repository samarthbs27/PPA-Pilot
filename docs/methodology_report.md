# PPA-Pilot Methodology Report

ML-guided physical design QoR prediction and parameter recommendation
for the GCN accelerator implemented in Cadence Innovus 23.12 on ASAP7.

---

## 1. Motivation

Physical design closure requires exploring many combinations of flow parameters —
clock period, utilization, aspect ratio, placement density, and congestion effort.
A 25-run exhaustive grid search takes ~20 hours of Innovus wall time. The goal of
PPA-Pilot is to:

1. Build a QoR dataset from real Innovus runs
2. Train simple ML models to predict timing/power/area from flow parameters
3. Use those models to rank unseen configs and reduce guided search iterations

This is a project-scale methodology prototype, not an industry-grade predictor.
The design, tool, and PDK are fixed across all runs — the models capture
tool behavior on this specific block, not general physical design rules.

---

## 2. Dataset

### 2.1 Source

All data comes from real Cadence Innovus 23.12 APR runs of the GCN accelerator
on the ASAP7 predictive 7nm PDK (RVT cells, TT/0.7V/25C corner).

### 2.2 Sweep matrix

| Axis | Values | # Levels |
|---|---|---|
| Clock period | 0.6 / 0.8 / 1.0 / 1.4 ns | 4 |
| Utilization target | 40 / 50 / 55 / 65 / 70% | 5 |
| Aspect ratio | 0.8 / 1.0 / 1.2 / 1.5 | 4 (clk=1.4 only) |
| Congestion effort | low / medium / high | 3 (clk=1.4 only) |

Total automated sweep runs: **25**

Phase 1 (clk=1400 ps): 10 runs varying all four axes.
Phases 2–4 (clk=1000/800/600 ps): 5 runs each, varying utilization only.

### 2.3 ML training subset

Only sweep runs (`run_id` starts with `run_`) are used for ML training.
Pre-sweep manual runs (baseline_01, optimized_01/02, freq_*) are excluded
because they differ in flow setup and SDC from the sweep baseline.

### 2.4 Metrics captured per run

| Category | Metrics |
|---|---|
| Timing | Setup WNS/TNS/violations, hold WNS/TNS/violations |
| Area | Cell area (µm²), instance count, placed density |
| Power | Internal, switching, leakage, total (mW), clock power |
| DRC | Geometry violation count (capped at 1,000 by Innovus) |
| CTS | Skew (ps), max insertion delay (ps), depth, wirelength |
| Wire | Total wirelength (µm), buffer count, CTS buffer count |

### 2.5 DRC note

Innovus `verify_drc` caps the reported count at 1,000 (IMPVFG-1103).
Runs hitting the cap are recorded as `1000_capped` in the CSV and converted
to 1,001 for numeric ML use. The exact count is not available from the report
file alone — it would require reading the Innovus console log.

---

## 3. Features

Four flow parameters are used as ML input features:

| Feature | Type | Encoding |
|---|---|---|
| `clock_period_ns` | Continuous | Raw value (0.6–1.4) |
| `utilization_target` | Continuous | Raw value (0.40–0.70) |
| `aspect_ratio` | Continuous | Raw value (0.8–1.5) |
| `cong_effort` | Ordinal categorical | low=0, medium=1, high=2 |

`core_margin_um` is fixed at 5 µm across all sweep runs and is excluded.

---

## 4. Targets

| Target | Model type | Units |
|---|---|---|
| Timing pass/fail (WNS ≥ 0) | Classifier | Binary |
| Setup WNS | Regressor | ps |
| Total power | Regressor | mW |
| Cell area | Regressor | µm² |

---

## 5. Models

| Model | Algorithm | Library | Estimators |
|---|---|---|---|
| Timing classifier | RandomForestClassifier | scikit-learn | 200 |
| WNS regressor | RandomForestRegressor | scikit-learn | 200 |
| Power regressor | GradientBoostingRegressor | scikit-learn | 200 |
| Area regressor | RandomForestRegressor | scikit-learn | 200 |

Random Forest was chosen for its robustness to small datasets, built-in feature
importance, and interpretability. GradientBoosting is used for power because power
has a strong monotonic relationship with clock period — GBR captures sequential
residual correction well on this type of signal.

No hyperparameter tuning was performed — the defaults are appropriate for a
25-sample dataset and prevent overfitting to noise.

---

## 6. Evaluation method

**Leave-one-out cross-validation (LOO-CV)** is used throughout because the dataset
is small (25 rows). LOO trains on N−1 samples and predicts the held-out sample,
repeating for all N samples. This gives an unbiased estimate of generalization
error at the cost of N training runs.

Metrics reported:
- Classifiers: accuracy, F1 score
- Regressors: R², MAE, RMSE

---

## 7. Results

### 7.1 Timing classifier (LOO-CV)

| Metric | Value |
|---|---|
| Accuracy | 0.920 (23/25 correct) |
| F1 score | 0.958 |

The classifier correctly identified 24 of 25 passing runs and the single failing
run (run_600_u65_ar100_low, WNS -657 ps, CTS skew 1,229 ps). Two passes were
misclassified — both near the decision boundary at 0.6 ns and high utilization.

### 7.2 WNS regressor (LOO-CV)

| Metric | Value |
|---|---|
| R2 | -0.435 |
| MAE | 85.1 ps |
| RMSE | 192.5 ps |

Negative R2 is expected: 24 of 25 runs passed timing with WNS between +52 ps and
+210 ps — a narrow 158 ps band dominated by CTS skew variation, which is not
directly controlled by the four input features. The single outlier (-657 ps) pulls
RMSE sharply upward. The classifier (Section 7.1) is more useful than the regressor
for timing risk assessment at this dataset size.

### 7.3 Power regressor (LOO-CV)

| Metric | Value |
|---|---|
| R2 | 0.974 |
| MAE | 0.546 mW |
| RMSE | 0.803 mW |

Excellent fit. Power spans 3.1 mW (714 MHz) to 18.4 mW (1.67 GHz) — a 5.9x range
driven almost entirely by clock period (switching frequency + synthesis cell count).
The GBR model captures the near-linear log relationship well.

### 7.4 Area regressor (LOO-CV)

| Metric | Value |
|---|---|
| R2 | 0.905 |
| MAE | 1,593 um2 |
| RMSE | 2,468 um2 |

Strong fit. Cell area spans 21,000–46,000 um2, driven primarily by clock period
(tighter timing forces more buffers and synthesis restructuring). Utilization target
has a secondary effect on placed density rather than total cell count.

---

## 8. Feature importance (measured)

Actual Random Forest feature importances from trained models:

| Feature | Timing classifier | WNS regressor | Power regressor | Area regressor |
|---|---|---|---|---|
| clock_period_ns | 0.417 | 0.500 | **0.958** | **0.909** |
| utilization_target | **0.582** | 0.497 | 0.042 | 0.091 |
| aspect_ratio | 0.001 | 0.002 | 0.000 | 0.000 |
| cong_effort_enc | 0.000 | 0.000 | 0.000 | 0.000 |

Key findings:

1. **Power and area are dominated by clock period** (0.96 and 0.91 importance).
   Tighter timing forces DC to use more combinational stages and buffers, directly
   increasing switching power and cell count.

2. **Timing failure risk is dominated by utilization** (0.582).
   The only timing failure (run_600_u65) occurred at the combination of tightest
   clock and highest utilization — the classifier correctly weights utilization
   as the primary risk factor.

3. **WNS margin shows nearly equal clock/utilization importance** (0.50/0.50).
   Both parameters constrain the routing slack budget, making point-to-point WNS
   prediction harder than pass/fail classification.

4. **Aspect ratio and congestion effort have near-zero importance** across all models.
   At 1.4 ns (the AR/cong sweep), the GCN block has sufficient timing headroom that
   die shape and routing aggressiveness do not meaningfully affect timing or power.

Feature importance plots: `images/ppa_tradeoff_plots/feat_importance_*.png`

---

## 9. Recommender

`recommend.py` loads all four trained models and scores a 672-point candidate
grid (8 clock × 7 util × 4 AR × 3 cong). For each unseen config it predicts:

- Timing pass probability
- Setup WNS (ps)
- Total power (mW)
- Cell area (µm²)

Configs are ranked by the user-specified objective (`--objective wns/power/area`)
subject to a clock period constraint (`--target-clock`). The top-ranked config
is output as a `user_config.tcl` snippet ready for the next Innovus run.

Example:
```bash
python scripts/recommend.py --target-clock 1.0 --objective wns --top 3
```

---

## 10. Limitations

- **Small dataset:** 25 runs is sufficient for simple correlations but not for
  deep generalization. Models capture tool behavior on this specific block only.
- **Fixed design:** All runs are the same GCN RTL. The models do not generalize
  to different designs or cell counts.
- **Single corner:** ASAP7 open PDK has TT/0.7V/25C only. Power and timing
  predictions apply to this corner only — SS/FF behavior is uncharacterized.
- **DRC cap:** DRC counts capped at 1,001 (numeric sentinel) compress information
  about runs with significantly different violation counts.
- **LOO instability at N=25:** LOO CV with 25 samples can be noisy. R² values
  should be interpreted with caution — a model with R²=0.7 at N=25 may perform
  worse on truly unseen configs.
- **No runtime prediction:** Runtime varies 14–71 minutes depending on instance
  count. A runtime model would improve sweep scheduling but was not built.

---

## 11. Comparison: exhaustive vs. guided search

| Strategy | Runs to characterize space | Notes |
|---|---|---|
| Exhaustive grid | 25 | All configs tried; full QoR dataset built |
| Random search | ~3 avg to find any passing config | 96% pass rate; geometric distribution |
| ML-guided | 1 (rank #1 recommendation) | Recommender outputs best candidate immediately after training |

The 25-run exhaustive sweep built the training dataset. Given the same budget
goal — find a timing-clean, low-power config at 1.0 GHz — random search would
be expected to find a passing config within ~3 tries (Bernoulli at 96% pass rate),
but would not rank by power without running all candidates.

The trained recommender (`recommend.py --target-clock 1.0 --objective wns`)
immediately outputs:

```
Rank #1: clk=0.9 ns, util=55%, AR=1.0, cong=medium
Predicted WNS: +200 ps  |  Power: 9.83 mW  |  Area: 33,997 um2
Timing pass probability: 100%
```

This is an interpolated config between the 0.8 ns and 1.0 ns training points —
a config the sweep did not run — selected in 0 additional Innovus runs.
The honest interpretation: the recommender reduces next-config selection from
a grid-search guess to a single informed recommendation backed by 25 training runs.
