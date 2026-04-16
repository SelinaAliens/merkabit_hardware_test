# Merkabit Hardware Tests

**IBM cross-architecture validation of the merkabit framework**

Selina Stenberg with Thor Henning Hetland and Claude Anthropic, 2026

## Overview

This repository is the hardware-validation track of the Merkabit Research Series. It contains the simulation code, analysis scripts, hardware protocols, and raw output for **four papers** that share a single codebase and IBM session history:

| Paper | Title | Venue | Core result |
|-------|-------|-------|-------------|
| **3**  | The Rotation Gap Is Not An Error | arXiv · [Zenodo 10.5281/zenodo.19438935](https://doi.org/10.5281/zenodo.19438935) | Regime-classifier decoder on 756 IBM Eagle r3 QEC runs; Willow cross-platform control |
| **24** | The P Gate Is Native | [Zenodo 10.5281/zenodo.19484743](https://doi.org/10.5281/zenodo.19484743) | First hardware validation of the P gate on ibm_strasbourg (6–7 Apr 2026) — ZPMB, π-lock, Z₂ symmetry, Eisenstein cell |
| **25** | Four of Five | [Zenodo 10.5281/zenodo.19502830](https://doi.org/10.5281/zenodo.19502830) | P1 Ramsey, P2 quasi-period, τ=5 rotation-gap Fano gap — 4/5 Appendix N predictions retired (9 Apr 2026) |
| **26** | The Merkabit Is Geometric | [Zenodo 10.5281/zenodo.19554030](https://doi.org/10.5281/zenodo.19554030) | Heron r2 cross-architecture (Kingston), Willow reinterpretation, square-vs-hex topology simulation — 5/5 retired (12 Apr 2026) |

**Appendix N prediction scorecard: 5/5 retired on IBM hardware across three backends and two processor architectures.** See [HARDWARE-RESULTS.md](HARDWARE-RESULTS.md) for per-session details with IBM job IDs.

The private working repo is [`selinaserephina-star/merkabit_hardware_test`](https://github.com/selinaserephina-star/merkabit_hardware_test); the public MIT-licensed mirror is [`SelinaAliens/merkabit_hardware_test`](https://github.com/SelinaAliens/merkabit_hardware_test).

## The P Gate

The merkabit's signature is the P gate:
```
Forward spinor:  Rz(+phi)
Inverse spinor:  Rz(-phi)
```
Two single-qubit rotations. Opposite signs. On IBM hardware, `Rz` is a virtual-Z frame change — zero duration, zero error, zero cost. On Google Willow, the entire n-step Floquet evolution compiles to a single PhXZ gate per qubit (depth 2 regardless of n). The three hardware papers below (24, 25, 26) are the progressive proof of native implementability across architectures.

## Repository Structure

```
merkabit_hardware/
  decoders/                  Regime classifier and edge-correlated decoders       (Paper 3)
  hardware/                  IBM Eagle r3 DAQEC analysis scripts                   (Paper 3)
  willow/                    Google Willow cross-platform comparison               (Paper 3 + Paper 26 correction)
  experiments/               Pentachoric hardware protocol (P1..P5)                (Papers 24, 25, 26)
    run_p3_z2.py                     Chirality Z₂ symmetry, ZPMB benchmarks        (Paper 24)
    run_rotation_gap_hardware.py     9-qubit triangle, tau sweep                   (Paper 24, 25)
    run_p1_berry_phase.py            Ancilla-controlled Berry phase, depth ≤ 389   (Paper 25)
    run_p1_ramsey.py                 Ramsey Berry phase, zero CX, depth 6          (Paper 25, 26)
    run_p2_stroboscopic.py           Stroboscopic quasi-period n=1..59             (Paper 25, 26)
    run_p5_dtc.py                    DTC paired/control/ε perturbation             (Paper 25, 26)
    sim_square_vs_hex.py             Noiseless hex vs square topology              (Paper 26)
    sim_square_vs_hex_noisy.py       Monte Carlo with injected error rate ε        (Paper 26)
    make_paper25_figures.py          Paper 25 publication figures
    make_paper22_figures.py          Paper 22 publication figures
  qubit_mapper.py            Eisenstein cell topology + Eagle r3/Heron r2 embedding
  ouroboros_circuit.py       12-step Floquet circuits, P gate asymmetry, R-locking
  multi_merkabit_circuit.py  3-node triangle + 7-node Eisenstein cell
  run_experiment.py          Main harness: --mode classical|hardware, --full-gap
  outputs/                   Raw JSON counts from all IBM sessions (Strasbourg, Brussels, Kingston)
  figures/                   Paper figures + figures_data.json
  HARDWARE-RESULTS.md        Per-session results with IBM job IDs
```

---

## Paper 3 — The Rotation Gap Is Not An Error

**Scripts:** `decoders/`, `hardware/`, `willow/`, `run_experiment.py`, `run_7node_lean.py`, `multi_merkabit_circuit.py`

Evidence from 756 QEC runs on IBM Eagle r3 (ibm_brisbane/kyoto/osaka, 14 days) that a fraction of syndrome activations are not errors but structured cooperative transitions. Introduces a regime-classifier decoder that improves logical error rates by 7–19% through selective abstention. A 420-experiment cross-platform control on Google's 105-qubit Willow processor (d=3,5,7) shows the opposite statistics — super-Poissonian, quadratic burst scaling, positive spatial correlation — confirming the signal is absent in surface-code circuits without the P-gate asymmetry. (The framing "architecture-specific to heavy-hex" is corrected by Paper 26; see below.)

### IBM vs Google Willow Cross-Platform Comparison

| Metric | IBM Eagle r3 | Google Willow |
|--------|-------------|---------------|
| Fano factor | 0.856 (sub-Poissonian) | 2.42 (super-Poissonian) |
| Distance dependence | None (ANOVA p = 0.79) | Strong (p ~ 0) |
| Burst scaling | Linear (R² = 0.9999) | Super-linear (R² = 0.9999) |
| Spatial correlation | Anti-bunched | Bunched (+0.13) |
| Architecture | Heavy-hex (hexagonal) | Grid (square-like) |

### Pentachoric Circuit Simulation

| Configuration | Qubits | Fano Factor | Detection | Sub-Poissonian? |
|---|---|---|---|---|
| 3-merkabit triangle, τ=1 | 9 | **0.535** | 73.2% | Yes |
| 3-merkabit triangle, τ=5 | 9 | **0.52/round** | 78.2% | Yes |
| 3-merkabit triangle, τ=12 | 9 | **0.54/round** | 81.6% | Yes |
| 7-merkabit Eisenstein, τ=1 | 26 | **0.561** | 97.5% | Yes |
| Rotation gap (triangle) | — | — | **5.0 pp** | — |

**Data source (Paper 3):** [Zenodo 10.5281/zenodo.17881116](https://doi.org/10.5281/zenodo.17881116) (756 QEC runs) and [Zenodo 10.5281/zenodo.13273331](https://doi.org/10.5281/zenodo.13273331) (Willow, 420 experiments).

---

## Paper 24 — The P Gate Is Native

**Backend:** ibm_strasbourg (Eagle r3, 127-qubit heavy-hex) · **Session:** 6–7 Apr 2026 · **Validated qubit region:** q+=62, q−=81, anc=72

First on-silicon validation of the P gate. The merkabit's defining operation — asymmetric phase on dual spinors — compiles to two native IBM Rz gates with opposite signs. Zero overhead. Zero exotic hardware.

**ZPMB (Zero-Parameter Merkabit Benchmarks)**, Paper 24 §3:
- **ZP-ORF (return fidelity):** paired 0.9684 vs unpaired 0.9670 at depth 1 (ratio 1.001 — P gate adds zero noise). ✅
- **π-lock ⟨ZZ⟩:** +0.44 hardware vs +0.447 ideal (2% agreement, two independent runs).
- **ZP-PPW parity witness:** ⟨ZZ⟩=+0.44, ⟨XX⟩=−0.45 (equal magnitude, opposite sign — |Φ⁻⟩ signature). ✅

**P3 Z₂ symmetry** (`experiments/run_p3_z2.py`): mean Z₂ error = **0.0163** across n=4, 6, 8, 12 steps (threshold 0.03). Chirality reversal confirmed. ✅ Job IDs `d7ab7061co6s73d8fbhg` – `d7ab7au1co6s73d8fbsg`.

**P4 Pentachoric Eisenstein cell** (7-node, 26 qubits): centre-node detection = **99.3%** vs predicted 91% ± 5%; Fano (centre) = 0.055 ± 0.009; all 28 single-gate injections above 97% detection. ✅

---

## Paper 25 — Four of Five

**Backends:** ibm_strasbourg (Eagle r3) + ibm_brussels (Eagle r3) · **Session:** 9 Apr 2026

Four of the five Appendix N predictions retired in one session.

**Rotation Gap** (9-qubit triangle, q+=62/q−=81/anc=72):

| τ | Config | Det rate | Fano | Sub-P? | Depth |
|---|--------|----------|------|--------|-------|
| 1 | paired  | 0.767 | 0.654 | ✅ | 47 |
| 1 | control | 0.796 | 0.613 | ✅ | — |
| 3 | paired  | 0.985 | 0.871 | ✅ | 156 |
| 3 | control | 0.988 | 0.600 | ✅ | — |
| 5 | **paired**  | 1.000† | **0.506** | ✅ | 279 |
| 5 | **control** | 1.000† | **0.564** | ✅ | — |

† Detection saturated — Fano gap (paired − control = −0.058) is the operative metric at τ=5. **Matched depth, same chip, same gate count: only the P gate presence differs.** Per-round Fano stable at 0.487 across all 5 rounds. Counter-rotating edge (chi_diff=2) fires most in every run.

**P1b Ramsey** (forward vs reversed chirality, 16 jobs, zero CX, depth 6):

| n | Ideal diff | HW diff | Notes |
|---|-----------|---------|-------|
| 4 | −0.556 | **−0.557** | near-exact |
| 8 | +1.138 | **+1.085** | 95% fidelity |
| 10 | +1.486 | **+1.433** | 96% fidelity |
| 12 | +0.156 | +0.194 | near-zero return |

Sign flip n=6→8 confirmed. Z₂ antisymmetry ⟨Z⁺⟩_diff = −⟨Z⁻⟩_diff confirmed to ~1%.

**P2 Stroboscopic** (30 circuits, n=1..59 stride 2, batched job `d7bovn8evlqs73a4buk0`, zero CX, depth 6):

| n | n/T | P_hw | P_ideal | Note |
|---|-----|------|---------|------|
| 13 | 1.08T | 0.688 | 0.696 | local min |
| 27 | 2.25T | 0.670 | 0.683 | local min |
| **39** | **3.25T** | **0.890** | **0.909** | **hardware peak (97.9%)** |
| 41 | 3.42T | 0.783 | 0.788 | sharp drop |
| 57 | 4.75T | 0.901 | 0.924 | secondary peak |

Quasi-period 3.3T = 39.6 steps confirmed. P_return oscillates at 97–99% fidelity throughout — quantum dynamics, not decoherence. ✅

---

## Paper 26 — The Merkabit Is Geometric

**Backends:** ibm_kingston (Heron r2, 156-qubit) + ibm_brussels + ibm_strasbourg · **Session:** 12 Apr 2026

Completes the Appendix N scorecard to **5/5** and corrects the Paper 24 Willow interpretation.

### 1. Cross-architecture confirmation on Heron r2 (Kingston)

The full pentachoric protocol was repeated on IBM Heron r2 (`ibm_kingston`, different coupling map from Eagle r3). P2 local minima at n=13 (0.688 Strasbourg vs 0.709 Kingston, ideal 0.696) and n=27 (0.670 vs 0.694, ideal 0.683) bracket the ideal within 2% on both architectures. Batched job `d7ds1uh5a5qc73dq87d0` on Kingston.

**P5 DTC paired/control ratio:**

| Backend | Architecture | Paired/Control 2T |
|---------|--------------|-------------------|
| ibm_brussels | Eagle r3 | 3.20–3.58× |
| ibm_strasbourg | Eagle r3 | 3.20× (ε=0.3) |
| **ibm_kingston** | **Heron r2** | **3.43–3.92×** |

P5 DTC job IDs documented in `HARDWARE-RESULTS.md` §P5 prose (`d7drb1sdm0ls73cc1lfg` paired, `d7drb3p4p4gc73f6jhf0` control, `d7drb5ir4f1s73a4eotg` ε=0.1 on Brussels; equivalent Kingston runs in `outputs/p5_dtc/p5_dtc_ibm_kingston_20260412_*.json`).

**P1b Ramsey on Heron r2** (16 jobs, batched): sign flip n=6→8 confirmed, peak at n=10 (+1.4429 hw vs +1.4861 ideal, 97% fidelity), Z₂ antisymmetry ⟨Z⁺⟩_diff = +1.4429 / ⟨Z⁻⟩_diff = −1.4756.

### 2. Willow interpretation corrected

Paper 3/24's framing that the sub-Poissonian signal is "architecture-specific to heavy-hex" was premature — the Willow comparison was paired-IBM vs unpaired-Google, not hex-vs-square under matched protocols. The honest conclusion: **the signal follows the P-gate asymmetry, not the topology**.

### 3. Square-grid topology simulation

Monte Carlo with injected error rate ε, matched protocol:

| Topology | τ | ε | Fano | Sub-P? |
|----------|---|---|------|--------|
| hex-triangle (3n) | 5 | 0.10 | 0.92→sub-Poissonian | ✅ |
| square-2×2 (4n) | 5 | 0.10 | sub-Poissonian | ✅ |
| hex-Eisenstein (7n) | 5 | 0.10 | 0.522 | ✅ |
| square-3×3 (9n) | 5 | 0.10 | 0.343 | ✅ |
| **4×4 square (16n)** | **5** | **0.10** | **0.285** | **✅ tightest anti-bunching of any cell** |

The 4×4 and 5×5 square cells are defined in the sibling repo (see below) at `willow_hardware_merkabit/simulations/sim_scaling_comparison.py`; the 2×2 / 3×3 cells are in this repo (`experiments/sim_square_vs_hex_noisy.py`).

At τ ≥ 5, **both topologies go sub-Poissonian**, and at matched node counts the square grid is *more* sub-Poissonian than hex at every error rate tested.

**Pre-registered prediction for Google Willow** (Paper 26 §6): F ≈ 0.3–0.7 at 2-qubit τ=5, DTC ratio > 3×, P1b sign flip n=6→8, P2 n=13 local min ≈ 0.696, P2 quasi-period peak at n = 39 ± 2, F ≈ 0.29 on a 4×4 square at τ=5. Cirq implementations, the full scaling simulation, and the timestamped `PREDICTION.md` live in the sibling repo — see below.

### Sibling repository — Google Willow early-application access

Paper 26 is the joint publication of two repositories. This repo (`merkabit_hardware_test`) holds the **IBM hardware side** — raw JSON counts, job IDs, `HARDWARE-RESULTS.md`, the three-backend 5/5 scorecard. The sibling repo, [`SelinaAliens/willow_hardware_merkabit`](https://github.com/SelinaAliens/willow_hardware_merkabit), is the **Google Willow early-application-access side**: pre-registered Cirq circuits ready to ship to Willow, plus the topology-scaling simulations that motivate the prediction.

| Sibling-repo file | Role in Paper 26 |
|-------------------|------------------|
| `PREDICTION.md` | Timestamped pre-registration of the six Willow observables |
| `experiments/run_p1b_ramsey_cirq.py` | P1b Ramsey in Cirq (depth 2 after PhXZ merge) |
| `experiments/run_p2_stroboscopic_cirq.py` | P2 quasi-period sweep in Cirq |
| `experiments/run_p5_dtc_cirq.py` | P5 DTC paired/control/ε in Cirq |
| `simulations/sim_scaling_comparison.py` | Hex {3,7,19} and square {4,9,16,25} cells — source of F=0.285 at 4×4 τ=5 ε=0.10 |
| `simulations/sim_square_vs_hex{,_noisy}.py` | Matched-protocol hex-vs-square Monte Carlo (also mirrored here for convenience) |

The two repos are intentionally matched: the IBM results in this repo pin down 5/5 on Eagle r3 and Heron r2; the Willow repo stages the next Google-hardware session without touching this codebase.

### Appendix N scorecard — complete

| Prediction | Status | Backend(s) | Paper |
|-----------|--------|------------|-------|
| P1 Berry phase | ✅ | Strasbourg (Ramsey + ancilla) | 25 |
| P2 Quasi-period | ✅ | Strasbourg + Kingston | 25, 26 |
| P3 Z₂ chirality symmetry | ✅ | Strasbourg | 24 |
| P4 Centre-node detection rate | ✅ | Strasbourg | 24 |
| **P5 DTC robustness** | ✅ | **Brussels + Strasbourg + Kingston** | **26** |

**5/5 retired on hardware within one week (6–12 April 2026). No error mitigation applied anywhere.** Full session details with IBM job IDs: [HARDWARE-RESULTS.md](HARDWARE-RESULTS.md).

---

## Script-to-Result Mapping

### Paper 3 — Decoders
| Script | Section | Result |
|--------|---------|--------|
| `decoders/regime_classifier_v2.py` | 5, 6 | Regime classifier decoder, 7–19% LER improvement |
| `decoders/regime_classifier_decoder.py` | 5, 6 | Unified classifier+decoder, selective abstention |
| `decoders/decoder_v2_fast.py` | 5 | Edge-mediated correlated decoder (fast, single-calibration) |
| `decoders/decoder_v2_edge_correlated.py` | 4 | Edge-mediated error model producing sub-Poissonian statistics |

### Paper 3 — IBM Hardware Analysis
| Script | Section | Result |
|--------|---------|--------|
| `hardware/ibm_heron_paper15_tests.py` | 2.1–2.4 | Fano = 0.856, linear burst scaling R²=0.9999, T2 threshold channel |
| `hardware/daqec_kww_analysis.py` | 2.4 | KWW stretched exponential on T1/T2 drift, α = 4/3 in T2 segments |
| `hardware/daqec_acf_psd_analysis.py` | 2.4 | ACF/PSD, DFA Hurst (T1 H~0.15, T2 H~1.0) |
| `hardware/fano_strong_coupling.py` | App. A | Fano/7 = αₛ mapping, strong coupling from syndrome statistics |

### Paper 3 — Willow Cross-Platform
| Script | Section | Result |
|--------|---------|--------|
| `willow/willow_fano_analysis.py` | 2.5 | Fano = 2.42 super-Poissonian, super-linear burst scaling |
| `willow/willow_temporal_depth.py` | 2.5 | Spatial Fano 1.37–1.75, temporal autocorrelation +0.22 |
| `willow/willow_classifier_test.py` | 2.6 | Regime classifier falsification: zero effect on Willow (r~0, p>0.6) |
| `willow/ibm_vs_willow_apples.py` | 2.5 | Round-count matched comparison, zero temporal bunching on IBM |

### Papers 24, 25, 26 — Pentachoric Hardware Protocol
| Script | Paper | Purpose |
|--------|-------|---------|
| `qubit_mapper.py` | 3/24/25/26 | Eisenstein cell → Eagle r3 / Heron r2 embedding |
| `ouroboros_circuit.py` | 24 | 12-step Floquet circuits, P gate = Rz(+φ) ⊗ Rz(−φ) |
| `multi_merkabit_circuit.py` | 3 | Triangle + 7-node Eisenstein cell (Fano 0.535–0.561) |
| `run_experiment.py` | 3 | Main harness: `--mode classical/hardware` |
| `experiments/run_p3_z2.py` | **24** | Z₂ symmetry + ZPMB benchmarks + P4 Eisenstein cell |
| `experiments/run_p1_ramsey.py` | **25/26** | Ramsey Berry phase (Strasbourg + Kingston), zero CX |
| `experiments/run_p1_berry_phase.py` | **25** | Ancilla-controlled Berry phase |
| `experiments/run_p2_stroboscopic.py` | **25/26** | Quasi-period n=1..59 (Strasbourg + Kingston) |
| `experiments/run_p5_dtc.py` | **25/26** | DTC paired/control/perturbed (Brussels + Strasbourg + Kingston) |
| `experiments/run_rotation_gap_hardware.py` | **25** | 9-qubit τ sweep with Fano gap |
| `experiments/sim_square_vs_hex.py` | **26** | Noiseless hex vs square topology |
| `experiments/sim_square_vs_hex_noisy.py` | **26** | Monte Carlo with injected errors |

## Data Sources

- **Paper 3 — IBM Eagle r3 DAQEC:** [Zenodo 10.5281/zenodo.17881116](https://doi.org/10.5281/zenodo.17881116) (756 QEC runs, ibm_brisbane/kyoto/osaka, 14 days)
- **Paper 3 — Google Willow:** [Zenodo 10.5281/zenodo.13273331](https://doi.org/10.5281/zenodo.13273331) (420 experiments, 105-qubit, d=3,5,7)
- **Papers 24/25/26 — Strasbourg/Brussels/Kingston:** raw JSON counts in `outputs/`; IBM job IDs embedded per file or documented in `HARDWARE-RESULTS.md` §P5

## Usage

```bash
# Paper 3 — regime classifier
python decoders/regime_classifier_v2.py

# Paper 3 — Willow cross-platform analysis
python willow/willow_fano_analysis.py

# Paper 3 — pentachoric classical simulation
python run_experiment.py --mode classical --full-gap --shots 8192

# Paper 3 — pentachoric on IBM hardware
python run_experiment.py --mode hardware --backend ibm_strasbourg --full-gap

# Paper 24 — Z2 symmetry + ZPMB + P4 Eisenstein cell
python experiments/run_p3_z2.py --steps 4 6 8 12

# Paper 25 — Ramsey Berry phase (zero CX, always runs)
python experiments/run_p1_ramsey.py --steps 1 2 3 4 6 8 10 12

# Paper 25 — ancilla-controlled Berry phase (calibrated)
python experiments/run_p1_berry_phase.py --steps 2 4 6 8 10 12

# Paper 25/26 — stroboscopic recurrence sweep (Strasbourg + Kingston)
python experiments/run_p2_stroboscopic.py --stride 2 --n-max 60

# Paper 25/26 — DTC survival (paired / control / ε, three backends)
python experiments/run_p5_dtc.py --n-max 48 --shots 4096
python experiments/run_p5_dtc.py --n-max 48 --shots 4096 --epsilon 0.1
python experiments/run_p5_dtc.py --n-max 48 --shots 4096 --epsilon 0.3

# Paper 25 — 9-qubit rotation gap (critical test, Fano gap)
python experiments/run_rotation_gap_hardware.py --tau 1 3 5 --shots 8192

# Paper 26 — square vs hex topology (simulation)
python experiments/sim_square_vs_hex.py
python experiments/sim_square_vs_hex_noisy.py
```

See `experiments/EXPERIMENT_MAP.md` for the full protocol, execution order, shot budgets, and CX-direction caveats.

## Requirements

```
pip install numpy scipy qiskit qiskit-aer qiskit-ibm-runtime
```

All simulations use seed 42 for reproducibility.

## Theoretical Companion (Merkabit Research Series)

This repo is the hardware arm. The theoretical derivations (from which the Appendix N predictions are drawn) are:

| Paper | Title | Key result |
|-------|-------|-----------|
| Paper 20 | Gravity and Dark Matter from the Eisenstein Lattice | Inverse square law from 3D Laplacian Green's function; G_eff = 0.2542; dark matter = sedenion zero-divisor sector |
| Paper 21 | Orbital Quantisation, CPT, and the Pentachoric Transient | Bohr quantisation from Coxeter period; forbidden zone at r=8; falsifiable LIGO prediction (φ-trough at N≈75) |
| Paper 22 | The Cosmological Constant from Vacuum Monopole Suppression | Λ = 2.870×10⁻¹²² (observed 2.87×10⁻¹²²) — 0.01% accuracy, zero free parameters |
| Paper 23 | Ternary-Binary Coupling, Newton's Constant, and the Hierarchy | G = 1/N_spinor², Λ, Higgs vev v ≈ 255.3 GeV |

## Companion Repositories

- **Base paper:** [The Merkabit](https://doi.org/10.5281/zenodo.18925475) (Zenodo)
- **Paper 15:** [The Rotation Gap Is Flat](https://github.com/selinaserephina/rotation_gap_merkabit) (private working repo)
- **Sibling repo — Google Willow early-application access:** [`SelinaAliens/willow_hardware_merkabit`](https://github.com/SelinaAliens/willow_hardware_merkabit) — timestamped `PREDICTION.md`, Cirq circuits for P1b / P2 / P5 ready for Willow, 4×4 / 5×5 square-grid scaling simulations. Jointly publishes Paper 26 with this repo.

**Open science — no restrictions — all nations welcome.**
