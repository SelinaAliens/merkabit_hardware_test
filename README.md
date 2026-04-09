# Paper 3: The Rotation Gap Is Not An Error

**Ternary Structure in IBM Quantum Hardware**

Selina Stenberg with Claude Anthropic, 2026

## Overview

This repository contains all simulation code, analysis scripts, hardware protocol, and raw output for Paper 3 of the Merkabit Research Series. The paper presents evidence from 756 QEC runs across three IBM Eagle r3 processors that a fraction of syndrome activations are not errors but structured cooperative transitions, and introduces a regime classifier decoder that improves logical error rates by 7-19% through selective abstention.

A cross-platform control on Google's 105-qubit Willow processor (420 experiments) shows the opposite statistics -- super-Poissonian, quadratic burst scaling, positive spatial correlation -- confirming the sub-Poissonian signal is architecture-specific to IBM's heavy-hex connectivity.

**The P gate discovery (April 2026):** The merkabit's defining operation -- asymmetric phase on dual spinors -- compiles to two native IBM Rz gates with opposite signs. Zero overhead. Zero exotic hardware. The merkabit is native to every superconducting processor.

## Repository Structure

```
paper_3/
  decoders/                      Regime classifier and edge-correlated decoders
  hardware/                      IBM Eagle r3 DAQEC analysis scripts
  willow/                        Google Willow cross-platform comparison
  qubit_mapper.py                Eisenstein cell topology + Eagle r3 embedding
  ouroboros_circuit.py           12-step Floquet circuits, P gate asymmetry, R-locking
  multi_merkabit_circuit.py      3-node triangle + 7-node Eisenstein cell
  run_experiment.py              Main: --mode classical|hardware, --full-gap
  run_7node_lean.py              Lean 7-node baseline test
  outputs/                       Raw output files
```

## The P Gate

The merkabit's signature is the P gate:
```
Forward spinor:  Rz(+phi)
Inverse spinor:  Rz(-phi)
```
Two single-qubit rotations. Opposite signs. Every quantum computer on Earth can do this right now.

## Key Results

### IBM vs Google Willow Cross-Platform Comparison

| Metric | IBM Eagle r3 | Google Willow |
|--------|-------------|---------------|
| Fano factor | 0.856 (sub-Poissonian) | 2.42 (super-Poissonian) |
| Distance dependence | None (ANOVA p = 0.79) | Strong (p ~ 0) |
| Burst scaling | Linear (R^2 = 0.9999) | Super-linear (R^2 = 0.9999) |
| Spatial correlation | Anti-bunched | Bunched (+0.13) |
| Architecture | Heavy-hex (hexagonal) | Grid (square-like) |

### Pentachoric Circuit Simulation

| Configuration | Qubits | Fano Factor | Detection | Sub-Poissonian? |
|---|---|---|---|---|
| 3-merkabit triangle, tau=1 | 9 | **0.535** | 73.2% | Yes |
| 3-merkabit triangle, tau=5 | 9 | **0.52/round** | 78.2% | Yes |
| 3-merkabit triangle, tau=12 | 9 | **0.54/round** | 81.6% | Yes |
| 7-merkabit Eisenstein, tau=1 | 26 | **0.561** | 97.5% | Yes |
| Rotation gap (triangle) | -- | -- | **5.0 pp** | -- |

### Pentachoric Circuit Hardware — ibm_strasbourg (Apr 2026)

**P3 Z2 Symmetry** (`experiments/run_p3_z2.py`): mean Z2 error = **0.0163** across n=4,6,8,12
steps (threshold 0.03). Chirality reversal confirmed on hardware. ✅

**Rotation Gap** (`experiments/run_rotation_gap_hardware.py`): 3-merkabit triangle, 9 qubits,
validated layout q+=62/q-=81/anc=72.

| tau | Paired Fano | Control Fano | Sub-P? | Note |
|-----|------------|--------------|--------|------|
| 1   | 0.654      | 0.613        | ✅     | det 76.7% vs 79.6% |
| 3   | 0.871      | 0.600        | ✅     | det 98.5% vs 98.8% |
| 5   | **0.506**  | **0.564**    | ✅     | det saturated — Fano gap: paired more sub-P |

At tau=5: per-round Fano stable at ~0.487 across all 5 rounds. Counter-rotating edge (chi_diff=2)
fires most in every run. Full results: [HARDWARE-RESULTS.md](HARDWARE-RESULTS.md)

## Script-to-Result Mapping

### Decoders

| Script | Section | Result |
|--------|---------|--------|
| `regime_classifier_v2.py` | 5, 6 | Regime classifier decoder, 7-19% LER improvement |
| `regime_classifier_decoder.py` | 5, 6 | Unified classifier+decoder, selective abstention mechanism |
| `decoder_v2_fast.py` | 5 | Edge-mediated correlated decoder (fast, single-calibration) |
| `decoder_v2_edge_correlated.py` | 4 | Edge-mediated error model producing sub-Poissonian statistics |

### IBM Hardware Analysis

| Script | Section | Result |
|--------|---------|--------|
| `ibm_heron_paper15_tests.py` | 2.1-2.4 | Fano = 0.856, linear burst scaling R^2 = 0.9999, T2 threshold channel |
| `daqec_kww_analysis.py` | 2.4 | KWW stretched exponential on T1/T2 drift, alpha = 4/3 in T2 segments |
| `daqec_acf_psd_analysis.py` | 2.4 | ACF/PSD analysis, DFA Hurst exponents (T1 H~0.15, T2 H~1.0) |
| `fano_strong_coupling.py` | Appendix A | Fano/7 = alpha_s mapping, strong coupling from syndrome statistics |

### Google Willow Cross-Platform Comparison

| Script | Section | Result |
|--------|---------|--------|
| `willow_fano_analysis.py` | 2.5 | Fano = 2.42 (super-Poissonian), super-linear burst scaling, distance-dependent |
| `willow_temporal_depth.py` | 2.5 | Spatial Fano 1.37-1.75, temporal autocorrelation +0.22, full decomposition |
| `willow_classifier_test.py` | 2.6 | Regime classifier falsification: zero effect on Willow (r ~ 0, p > 0.6) |
| `ibm_vs_willow_apples.py` | 2.5 | Round-count matched comparison, zero temporal bunching on IBM |

### Pentachoric Hardware Protocol

| Script | Purpose | Result |
|--------|---------|--------|
| `qubit_mapper.py` | Eisenstein cell to Eagle r3 embedding | 26-qubit mapping |
| `ouroboros_circuit.py` | 12-step Floquet circuits with gate angles | P gate = Rz(+phi) x Rz(-phi) |
| `multi_merkabit_circuit.py` | Triangle + 7-node Eisenstein cell | Fano = 0.535-0.561 |
| `run_experiment.py` | Main: --mode classical/hardware | Full rotation gap protocol |

## Data Sources

- **IBM Eagle r3**: Zenodo DOI [10.5281/zenodo.17881116](https://doi.org/10.5281/zenodo.17881116) (756 QEC runs, ibm_brisbane/kyoto/osaka, 14 days)
- **Google Willow**: Zenodo DOI [10.5281/zenodo.13273331](https://doi.org/10.5281/zenodo.13273331) (420 experiments, 105-qubit, d=3,5,7)

## Usage

```bash
# Regime classifier (Paper 3 core result)
python decoders/regime_classifier_v2.py

# Willow cross-platform analysis
python willow/willow_fano_analysis.py

# Pentachoric circuit — classical simulation
python run_experiment.py --mode classical --full-gap --shots 8192

# Pentachoric circuit — IBM hardware
python run_experiment.py --mode hardware --backend ibm_strasbourg --full-gap

# 3-merkabit triangle
python multi_merkabit_circuit.py --cell triangle --shots 4096

# 7-merkabit Eisenstein cell
python run_7node_lean.py
```

## Requirements

```
pip install numpy scipy qiskit qiskit-aer qiskit-ibm-runtime
```

All simulations use seed 42 for reproducibility.

## Companion Papers

- **Base paper**: [The Merkabit](https://doi.org/10.5281/zenodo.18925475) (Zenodo)
- **Paper 15**: [The Rotation Gap Is Flat](https://github.com/selinaserephina-star/rotation_gap_merkabit) (GitHub)
- **Full series**: Papers 1-19, Merkabit Research Series
