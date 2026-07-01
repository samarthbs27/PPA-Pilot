# Resume Bullets — GCN Physical Design Closure and ML-Guided PPA Optimization

All numbers from real Cadence Innovus 23.12 / Synopsys DC / ASAP7 runs.

---

## Project 1 — Primary PD Closure Bullet

**Target resume section:** Most recent / most prominent project

```
GCN Accelerator Physical Design Closure — Synopsys Design Compiler, Cadence Innovus 23.12, ASAP7 predictive 7nm
- Implemented a sparse Graph Convolution Network accelerator (96-element parallel MAC datapath,
  ~10K standard cells) from RTL through Synopsys DC synthesis, Cadence Innovus floorplanning,
  placement, CTS (CCOpt), routing, SPEF extraction, post-route STA (OCV/CPPR), power analysis,
  and GDS/DEF output using the ASAP7 predictive 7nm PDK.
- Debugged two-layer CTS failure (CCOpt finding zero clock sinks): traced to set_dont_touch_network
  producing DHLx1 latches and a mismatched SEQ Liberty silently black-boxing 1,087 flip-flops;
  resolved by RTL coding fix and switching to the 22b-compatible 201020 Liberty.
- Closed timing at 714 MHz with setup WNS +0.094 ns (0 violations) and hold WNS +0.134 ns
  (0 violations) after diagnosing IO-path hold violations as SDC modeling artifacts and applying
  set_false_path -hold via set_interactive_constraint_modes.
- Characterized four frequency Pareto points (714 MHz to 1.67 GHz) — all passed timing; observed
  DC replacing FAx1 full-adder tree (2,403 cells) with ASAP7-native MAJ majority-gate cells (2,223
  at 1.67 GHz) as clock tightened; power scaled +431% (3.13 mW to 16.65 mW) across the range.
- Generated full signoff artifact set: post-route netlist, PG netlist, SPEF, GDS, and
  timing/power/area/DRC reports; enabled antenna diode insertion to eliminate all antenna violations.
```

---

## Project 2 — ML/Automation Bullet

**Target resume section:** Immediately below Project 1, or combined block

```
ML-Guided PPA Optimization (PPA-Pilot) — Python, scikit-learn, Cadence Innovus
- Automated a 25-run Innovus APR sweep across clock period (0.6–1.4 ns), utilization (40–70%),
  aspect ratio (0.8–1.5), and congestion effort (low/medium/high) using run_sweep.py; auto-parsed
  all run reports into a QoR CSV via batch_parse.py (timing, power, area, DRC, CTS metrics).
- Built a Python report parser (parse_reports.py) reading five Innovus report types per run —
  post-route timing summaries (.gz), power reports, area reports, DRC reports, and CTS skew/tree
  reports — appending structured rows to qor_dataset.csv for downstream ML training.
- Trained RandomForest timing classifier (LOO accuracy 92%, F1 0.958), WNS regressor (MAE 85 ps),
  power regressor (R2 0.97, MAE 0.55 mW), and area regressor (R2 0.91, MAE 1,593 um2) using
  leave-one-out CV; feature importance: clock period dominates power/area (importance 0.96/0.91),
  utilization dominates timing-failure risk (0.58) — confirmed the sole timing-fail at 0.6 ns/65% util.
- Built recommend.py to score 672 candidate configs against trained models, rank by WNS/power/area
  objective, and output a user_config.tcl snippet — reducing next-run selection from exhaustive
  grid search to a single guided recommendation.
- Generated 9 PPA tradeoff plots (WNS vs utilization, power vs area Pareto, CTS skew vs clock,
  DRC vs utilization, predicted vs actual) from the QoR dataset.
```

---

## Supporting Bullet — STA Engine

```
Static Timing Analysis Engine — Python, Liberty/NLDM, gate-level netlist
- Built a gate-level STA engine with bilinear NLDM interpolation, arrival/required time
  propagation, slack analysis, and critical-path extraction; scaled to 100K+ gate circuits;
  timing methodology used in the GCN post-route analysis to interpret Innovus WNS/TNS reports
  and identify critical paths.
```

---

## Alternative: Compact combined bullet (for space-constrained resume)

```
GCN Accelerator RTL-to-GDS Physical Design and ML-Guided PPA Optimization
— Synopsys DC V-2023.12, Cadence Innovus 23.12, ASAP7 predictive 7nm, Python/scikit-learn
- Implemented a GCN accelerator (96-wide parallel MAC, ~10K cells) through full ASIC physical
  design — floorplan, placement, CTS, routing, SPEF extraction, post-route STA (OCV/CPPR), and
  GDS; closed 714 MHz timing at WNS +0.094 ns / 0 setup violations and hold WNS +0.134 ns /
  0 hold violations; characterized frequency Pareto from 714 MHz to 1.67 GHz (all timing-clean).
- Automated 25-run parameter sweep (clock, utilization, AR, congestion); parsed all reports into a
  QoR dataset; trained ML models (timing classifier 92% accuracy, power R2 0.97); recommender scored
  672 unseen configs and identified best next candidate (0.9 ns / 55% util) in 0 additional runs.
```

---

## Numbers quick-reference

| Metric | Baseline | Optimized | Delta |
|---|---|---|---|
| Clock | 714 MHz (1.4 ns) | 714 MHz (1.4 ns) | — |
| Setup WNS | +0.093 ns | +0.094 ns | clean |
| Hold WNS | −0.001 ns | +0.134 ns | closed |
| Hold violations | 3 | 0 | −3 |
| Cell area | 21,409 µm² | 21,022 µm² | −1.8% |
| Instance count | 10,520 | 10,140 | −3.6% |
| Total power | 3.156 mW | 3.134 mW | −0.7% |
| Antenna DRC | included in 9,054 | 0 | resolved |
| Geometry DRC | 9,054 | ~8,872 | −2% |

| Frequency | Setup WNS | Power | Area | Density |
|---|---|---|---|---|
| 714 MHz | +0.094 ns | 3.13 mW | 21,022 µm² | 51.8% |
| 1.0 GHz | +0.184 ns | 6.92 mW | 30,047 µm² | 74.0% |
| 1.25 GHz | +0.197 ns | 10.93 mW | 35,545 µm² | 87.0% |
| 1.67 GHz | +0.169 ns | 16.65 mW | 41,463 µm² | 81.8% |

---

## ML model quick-reference

| Model | Algorithm | LOO metric | Key finding |
|---|---|---|---|
| Timing classifier | RandomForest | Accuracy 92%, F1 0.958 | Caught the sole failure at 0.6 ns / 65% util |
| WNS regressor | RandomForest | R2 -0.44, MAE 85 ps | WNS too stochastic (CTS-driven) for point regression |
| Power regressor | GradientBoosting | R2 0.97, MAE 0.55 mW | Clock period importance 0.96 |
| Area regressor | RandomForest | R2 0.91, MAE 1,593 um2 | Clock period importance 0.91 |

---

## Role-specific emphasis

**Tenstorrent / Etched (PD intern — iteration speed, automation):**
Lead with PPA-Pilot automation — sweep infrastructure, report parser, ML predictor.
Emphasize run_sweep.py automation, batch_parse.py, and recommend.py as methodology contributions.

**Intel / AMD / NVIDIA (timing-focused roles):**
Lead with CTS debugging narrative (two-layer failure, Liberty mismatch diagnosis) and
frequency Pareto story (MAJ-gate synthesis behavior). Emphasize OCV/CPPR setup and
constraint authorship.

**Qualcomm / NXP / Microchip (SoC/signoff roles):**
Lead with full artifact set (GDS, SPEF, PG netlist, DRC). Mention antenna fix methodology,
SDC authorship (IO delay, hold false paths, clock uncertainty, max fanout), and plans for
MMMC/IR when commercial tools are available.
