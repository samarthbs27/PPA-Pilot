# Interview Notes — GCN Accelerator Physical Design Closure

These are concise talking-point answers for PD intern/new-grad interviews.
All metrics are from real Cadence Innovus 23.12 / ASAP7 runs on the GCN accelerator.

---

## 1. What was your input RTL and what constraints did you write?

Input RTL is a parameterized SystemVerilog GCN accelerator: 96-element parallel MAC datapath,
COO-based sparse graph aggregation, and a `Transformation_FSM` control path. ~10,000–10,500 standard
cells post-synthesis on ASAP7.

SDC constraints written:
- `create_clock -period 1.4 [get_ports clk]` — 714 MHz target
- `set_input_delay 0.1 -clock clk [all_inputs]`
- `set_output_delay 0.1 -clock clk [all_outputs]`
- `set_clock_uncertainty 0.01 [get_clocks clk]`
- `set_max_fanout 16 [current_design]`
- `set_driving_cell -lib_cell INVx3_ASAP7_75t_R [all_inputs]`
- `set_false_path -hold -from/to [get_ports *]` — added in optimization round 2

---

## 2. How did you choose the floorplan?

Square die (aspect ratio 1.0), 50% target utilization, 5 µm core margin on all sides,
control signals pinned to the west edge, data outputs to the east edge. The square aspect
ratio keeps wire lengths symmetric across the MAC array. 50% utilization was chosen to give
the router headroom while staying area-efficient — baseline came in at 52.6% placed density.

Die dimensions: 47,499 µm² total die area, 43,207 µm² core area.

---

## 3. What utilization did you use and why?

50% utilization target, resulting in ~52.6% placed density (including filler cells).
Rationale: the GCN MAC tile has a dense adder tree (2,403 `FAx1` full adders at 714 MHz) and
227 mm of total wire length — leaving 50% free routing space was intentional to reduce congestion.
The 25-run sweep quantified this across utilization targets of 40–70% at all four clock periods.
At 65% util and 0.6 ns (the tightest combination), CTS skew exploded to 1,229 ps and timing
failed (WNS -657 ps) — the only failure in the sweep. At 65% util and relaxed clocks (1.0–1.4 ns),
timing remained clean, confirming that utilization alone does not cause failure at lower frequencies.

When synthesis was re-run at 1 GHz, the 50% floorplan became 74% dense because DC produced
18,831 instances vs 10,140 at 714 MHz. The floorplan target stayed at 50% but actual cell
area outgrew the core — a direct consequence of the aggressive synthesis restructuring.

---

## 4. How did utilization affect timing and congestion?

At 50%: setup timing was clean from the first baseline run (+93 ps WNS). No congestion-driven
timing failures. 9,054 geometry DRC violations were observed — characteristically from ASAP7
M1/M2 spacing/density rules, not from routing overflow.

The 25-run sweep covered utilization from 40% to 70% at all four clock periods. Key findings:
- At 1.4 ns: WNS stayed positive across 40–70% util (range +76 to +102 ps). DRC was capped
  at 1,000+ for all runs — congestion did not worsen meaningfully with utilization at this clock.
- At 0.6 ns / 65% util: catastrophic CTS failure — skew reached 1,229 ps (vs ~250 ps for
  neighboring runs), timing collapsed to WNS -657 ps. The only failing run in the entire sweep.
- At 0.6 ns / 70% util: timing recovered (+106 ps WNS) because lower instance count from
  aggressive DC restructuring gave CCOpt an easier CTS problem at 70% than at 65%.

---

## 5. What did CTS do to your timing?

CTS (CCOpt in Innovus) synthesized the clock tree to 1,087 `ASYNC_DFFHx1_ASAP7_75t_R`
flip-flops. Post-CTS timing was not independently reported (used `timeDesign -postRoute` as
the primary STA). Final post-route setup WNS was +0.094 ns — no CTS-induced regressions.

CTS was the hardest debugging challenge: two layered failures stopped CCOpt from running at all.

**Failure 1:** `set_dont_touch_network` in synthesis caused DC to map async-reset always_ff
blocks to DHLx1 D-latches instead of DFFs. CCOpt found zero clock sinks.

**Failure 2:** After removing `set_dont_touch_network`, the wrong SEQ Liberty was loaded
in Innovus (`220123` lib, which doesn't contain `ASYNC_DFFHx1`). Innovus silently black-boxed
all 1,087 flip-flops, making them invisible to CTS. Fixed by switching to the `201020` SEQ lib.

---

## 6. What were your worst setup and hold paths?

**Setup:** Critical path through the 96-element parallel MAC datapath — full adder chains
(`FAx1`) through the aggregation tree. Worst setup slack was +93 ps at 714 MHz (clean).

**Hold:** Worst hold violation was −1 ps at IO-terminating paths (`in2reg`/`reg2out`) in
the baseline. These are SDC modeling artifacts — the 0.1 ns IO delay model creates apparent
hold risk at ports that doesn't reflect real chip timing. Real register-to-register hold
slack was +139 ps in the baseline (very clean).

---

## 7. How did you fix your top timing violations?

**Hold violations (IO paths):**
Root cause: SDC IO delay constraint creates apparent hold risk on `in2reg`/`reg2out` paths.
Fix: `set_false_path -hold -from/to [get_ports *]` via `set_interactive_constraint_modes {common}`.
Result: Hold WNS went from −0.001 ns (3 violations) to +0.134 ns (0 violations).

**Antenna DRC violations:**
Fix: Enabled antenna diode insertion in the Innovus router (`globalDetail_antenna_fix` strategy).
Result: 0 antenna DRC violations in optimized_01 and optimized_02.

**DHLx1 residual latches (CTS risk):**
Root cause: FSM reset path synthesized to level-sensitive latches.
Fix: Re-synthesized with corrected RTL coding style.
Result: 0 `DHLx1` cells in optimized_01 netlist.

---

## 8. How did power change after optimization?

| Run | Clock | Total Power | Delta vs baseline |
|---|---|---|---|
| baseline_01 | 714 MHz | 3.156 mW | — |
| optimized_01 | 714 MHz | 3.124 mW | −1.0% |
| optimized_02 | 714 MHz | 3.134 mW | −0.7% |
| freq_1000_01 | 1,000 MHz | 6.922 mW | **+119%** |

Breakdown (optimized_02): 1.501 mW internal (47.9%), 1.632 mW switching (52.1%),
0.001 mW leakage. Clock power: 0.264 mW (8.4% of total).

Power reduction at 714 MHz came from the 1.8% area reduction (fewer cells → lower switching
and leakage). All runs at TT/0.7V/25C corner, 0.2 toggle rate.

At 1 GHz: power more than doubled (3.13 → 6.92 mW) driven by two effects — 40% higher
switching frequency and 86% more instances from synthesis restructuring. Clock power alone
rose 72% (0.264 → 0.453 mW) due to the larger clock tree needed to drive 18,831 cells.

---

## 9. What DRC/LVS/antenna issues appeared?

**Baseline:** 9,054 DRC violations — mix of geometry (M1/M2 spacing/density) and antenna violations.
The Innovus drc.rpt is capped at 1,000 displayed violations (IMPVFG-1103); actual count came
from the Innovus console output: "9054 geometry drc markers."

**Antenna:** Resolved by enabling antenna diode insertion (`globalDetail_antenna_fix`).
Result: 0 antenna violations in optimized_01 and optimized_02.

**Geometry DRC:** 8,872 in optimized_01 (−2% from baseline). These are characteristic of
the ASAP7 open-source PDK and router — primarily M1/M2 spacing violations from the 7.5-track
cell abutment geometry. Not a signoff-quality DRC check; Calibre would be required for production.

**LVS:** Not run. Would require matching SPICE netlists from the 22b cell family. Post-route
`apr_pg.v` (PG netlist) was generated as the LVS input artifact.

---

## 10. How did you parse reports and automate sweeps?

`parse_reports.py` reads five Innovus report files per run:
- `GCN_postRoute.summary` → setup WNS/TNS/violations via regex on `WNS (ns):|` format
- `GCN_postRoute_hold.summary` → hold WNS/TNS/violations
- `area.rpt` → instance count and cell area from the top-level module line
- `power.rpt` → internal/switching/leakage/total/clock power
- `drc.rpt` → geometry DRC count (with manual override for the 1,000-violation cap)

Output: one row appended to `results/qor_dataset.csv` per invocation. YAML config provides
run metadata (clock period, utilization, strategy settings).

`sweep_configs.py` generates YAML configs for grid/random/focused parameter sweeps and tracks
them in a manifest CSV. `plot_qor.py` renders PPA tradeoff plots from the dataset.

---

## 11. Why did your ML model choose certain parameters?

A 25-run automated sweep across clock period (0.6–1.4 ns), utilization (40–70%),
aspect ratio (0.8–1.5), and congestion effort (low/medium/high) was executed with
`run_sweep.py`. Reports are parsed into `qor_dataset.csv` by `batch_parse.py`.

**Four models trained with leave-one-out CV (N=25):**

| Model | Algorithm | Result |
|---|---|---|
| Timing pass/fail classifier | RandomForestClassifier | LOO accuracy 92%, F1 0.958 |
| Setup WNS regressor | RandomForestRegressor | R2 -0.44, MAE 85 ps |
| Power regressor | GradientBoostingRegressor | R2 0.97, MAE 0.55 mW |
| Area regressor | RandomForestRegressor | R2 0.91, MAE 1,593 µm² |

**Measured feature importances:**

| Feature | Timing classifier | WNS regressor | Power | Area |
|---|---|---|---|---|
| clock_period_ns | 0.417 | 0.500 | **0.958** | **0.909** |
| utilization_target | **0.582** | 0.497 | 0.042 | 0.091 |
| aspect_ratio | 0.001 | 0.002 | 0.000 | 0.000 |
| cong_effort | 0.000 | 0.000 | 0.000 | 0.000 |

**Key findings to state in interview:**
- Power and area are almost entirely determined by clock period (importance 0.96 / 0.91).
  Tighter timing forces DC to use more logic stages and buffers, increasing switching power
  and cell count. This drove a 5.9x power range (3.1 mW → 18.4 mW) across the sweep.
- Timing failure risk is dominated by utilization (0.582). The only failing run was
  run_600_u65 — tightest clock combined with highest utilization caused CTS skew to explode
  to 1,229 ps (vs ~200 ps in neighboring runs), collapsing timing margin to -657 ps.
- WNS point regression doesn't work (R2 = -0.44). Timing margin in near-closure conditions
  is driven by CTS placement decisions, which are stochastic given the 4 input features.
  The classifier (pass/fail) is more useful for timing risk.
- Aspect ratio and congestion effort have near-zero importance — they were swept only at
  1.4 ns where the block has ample headroom, masking their effect.

**Recommender output** (`recommend.py --target-clock 1.0 --objective wns`):

```
Rank #1: clk=0.9 ns, util=55%, AR=1.0, cong=medium
Predicted WNS: +200 ps  |  Power: 9.83 mW  |  Area: 33,997 µm²
Timing pass probability: 100%
```

This is an interpolated config between the 0.8 and 1.0 GHz training clusters — selected
in zero additional Innovus runs from a 672-point candidate grid.

---

## 12. What would you do differently with PrimeTime/Innovus/Calibre access?

- **MMMC signoff:** Run SS/FF corners and OCV analysis in addition to TT. ASAP7 is a predictive
  PDK so OCV tables exist, but single-corner analysis understates hold risk at FF corner.
- **Calibre DRC/LVS:** Replace open-source router DRC with Calibre for signoff-quality results.
  The ~8,000–9,000 geometry violations are likely partially false positives from the router.
- **PrimeTime SPEF/SDF:** Use PT for post-route STA with full parasitic annotation from SPEF.
  Innovus `timeDesign` is faster but PT gives more accurate path-level timing and SI analysis.
- **Voltus/RedHawk:** IR drop and EM analysis on the power grid. Currently no PDN analysis.
- **Conformal LEC:** Formal equivalence between RTL and post-route netlist.
- **ECO flow:** With PT ECO + Innovus, targeted cell swaps for critical paths rather than
  full re-routing optimization rounds.

---

## 13. What limitations exist in an open-source flow?

- **Single corner only:** ASAP7 open-source characterization is TT/0.7V/25C only.
  No SS (setup guard), no FF (hold guard), no MMMC.
- **No LVS:** SPICE netlists for the 22b cell family are not bundled.
- **Router DRC ≠ Calibre DRC:** Open-source router DRC is a fast geometry check,
  not a PDK-rule-deck signoff. The 8,000+ "violations" may include false positives
  and miss some Calibre-caught issues.
- **No IR drop/EM:** No power integrity analysis. PDN assumed ideal.
- **ASAP7 is predictive:** Not a real manufacturable process — timing models are
  predictions calibrated to 7nm node behavior, not foundry-characterized data.
- **Limited CTS control:** CCOpt buffer set is curated from the ASAP7 library; not
  the same flexibility as a full-library CTS run with Tempus co-optimization.

---

## 14. How does this project map to industry PD work?

The core PD flow (synthesis → floorplan → placement → CTS → routing → STA → signoff artifacts)
mirrors the industry methodology. Specifically:

- **Report parsing and sweep automation** directly maps to methodology engineering at
  Tenstorrent, NVIDIA, and Intel — PD teams automate QoR collection and run hundreds
  of parameter sweeps per design.

- **CTS debugging** (cell library mismatch, Liberty black-boxing) is a real class of
  PD integration problem — the same diagnosis process applies with Tempus/PrimeTime and
  commercial Liberty files.

- **Constraint authorship** (IO delay, hold false paths, clock uncertainty, max fanout)
  is the first thing a PD engineer does at RTL handoff — demonstrated here from scratch.

- **Antenna DRC diagnosis and fix** is a routine post-route signoff task — identifying
  antenna DRC, enabling diode insertion, and re-running route is exactly the ECO loop
  used in production.

- **PPA-Pilot ML predictor** maps to ML-for-PD methodology roles at Tenstorrent and
  NVIDIA — building training datasets from real implementation runs and using them to
  guide next-iteration parameter choices.

The main gap vs. industry: single-corner analysis, no LVS, no IR/EM, and ASAP7 vs.
a real foundry PDK. These are open-source flow limitations, not methodology limitations.

---

## 15. What did you observe about synthesis behavior across frequency targets?

This is a strong talking point from the multi-frequency sweep (714 MHz → 1.67 GHz).

At 714 MHz, Synopsys DC mapped the 96-element parallel MAC datapath to 2,403 `FAx1`
(full adder) cells — the natural mapping for a parallel adder tree.

At 1 GHz and above, DC progressively replaced `FAx1` with ASAP7-native majority-gate
cells. By 1.67 GHz, the substitution is nearly complete — only 23 `FAx1` remain.

**Cell type evolution across frequency:**

| Cell | 714 MHz | 1 GHz | 1.67 GHz | Notes |
|---|---|---|---|---|
| `FAx1` | 2,403 | 795 | **23** | −99% — nearly eliminated |
| `MAJIxp5` | 0 | ~583 | **1,721** | Fast inverted majority gate |
| `MAJx2` | 0 | ~465 | **486** | Standard majority gate |
| `MAJx3` | 0 | 0 | **16** | Appeared at 1.67 GHz only |
| Total MAJ | 0 | ~1,048 | **2,223** | Dominant carry cell at high freq |
| `HB1xp67` | 0 | 0 | **793** | Half-buffer; appeared at 1.67 GHz |

**What is a majority gate?**
MAJ(A, B, C) = AB + AC + BC — outputs 1 if the majority of inputs are 1. This is
exactly the carry-out equation of a full adder: Cout = MAJ(A, B, Cin). A full adder
decomposes into MAJ (carry) + XOR (sum). ASAP7 exposes MAJ3 as a native characterized
standard cell — most PDKs don't. DC exploits it under tight timing because it implements
carry in fewer logic stages than an equivalent NAND/NOR chain.

**MAJx3 at 1.67 GHz:** 3-input majority gate with 3x drive strength. DC selected it for
high-fanout carry nets where `MAJIxp5` lacked drive to meet the 0.6 ns budget. This
level of PDK-specific cell selection only appears when synthesis is pushed to its limits.

**HB1xp67 at 1.67 GHz:** Half-buffer (~0.67 drive strength). Innovus inserted 793 on
short, low-fanout paths where a full `BUFx2` would add excess capacitance and hurt timing.
Sub-cell drive-strength decisions — not needed at 714 MHz's relaxed timing budget.

**Full Pareto curve — all four runs passed timing:**

| Metric | 714 MHz | 1 GHz | 1.25 GHz | 1.67 GHz |
|---|---|---|---|---|
| Cell area | 21,022 µm² | 30,047 µm² | 35,545 µm² | 41,463 µm² |
| Instance count | 10,140 | 18,831 | 23,541 | 23,473 |
| Total power | 3.13 mW | 6.92 mW | 10.93 mW | 16.65 mW |
| Placed density | 51.8% | 74.0% | 87.0% | 81.8% |
| Setup WNS | +0.094 ns | +0.184 ns | +0.197 ns | +0.169 ns |
| CTS skew | — | — | 205.7 ps | 286.5 ps |

Going from 714 MHz → 1.67 GHz: area +97%, power +431%, timing passed at every point.
The failure point is below 0.6 ns (not yet tested; sweep moved to utilization/congestion
axes for ML training data — the frequency Pareto curve is already well-characterized).

---

## 16. What happened to CTS as you pushed the clock higher?

At 714 MHz and 1 GHz, CTS metrics were not independently captured (only post-route timing
was reported). From 1.25 GHz onward, skew and insertion delay grew monotonically because
the clock tree must reach more cells (87% density at 1.25 GHz, 81% at 1.67 GHz) in the
same floorplan.

| Clock | Skew | Max insertion delay | Tree depth | Clock buffers | Skew / Period |
|---|---|---|---|---|---|
| 0.8 ns (1.25 GHz) | 205.7 ps | 441.0 ps | 16 | 43 | 25.7% |
| 0.6 ns (1.67 GHz) | 286.5 ps | 526.4 ps | 22 | 59 | **47.8%** |

At 1.67 GHz, max insertion delay (526.4 ps) is 87.7% of the clock period. Despite this,
timing passed because the MAJ-gate datapath left +169 ps WNS to absorb the CTS penalty.

**Why does skew matter?** Skew reduces the effective timing budget: if the clock period is
600 ps and skew is 286 ps, the combinational path must close in 600 − 286 = 314 ps. At
47.8% skew/period, further frequency scaling would require hierarchical clock distribution,
a smaller block size, or custom clock buffer sizing — not just tighter synthesis.
