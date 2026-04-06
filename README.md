# Paper 3: The Rotation Gap Is Not An Error

**Ternary Structure in IBM Quantum Hardware**

Selina Stenberg with Claude Anthropic, March 2026

## Overview

This repository contains all simulation code, analysis scripts, and raw output for Paper 3 of the Merkabit Research Series. The paper presents evidence from 756 QEC runs across three IBM Eagle r3 processors that a fraction of syndrome activations are not errors but structured cooperative transitions, and introduces a regime classifier decoder that improves logical error rates by 7-19% through selective abstention.

A cross-platform control on Google's 105-qubit Willow processor (420 experiments) shows the opposite statistics -- super-Poissonian, quadratic burst scaling, positive spatial correlation -- confirming the sub-Poissonian signal is architecture-specific to IBM's heavy-hex connectivity.

## Repository Structure

```
paper_3/
  decoders/           Regime classifier and edge-correlated decoders
  hardware/           IBM Eagle r3 DAQEC analysis scripts
  willow/             Google Willow cross-platform comparison
  outputs/            Raw output files (see below)
```

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
| `willow_fano_analysis.py` | 2.5 | Fano = 2.42 (super-Poissonian), quadratic burst scaling, distance-dependent |
| `willow_temporal_depth.py` | 2.5 | Spatial Fano 1.37-1.75, temporal autocorrelation +0.22, full decomposition |

## Data Sources

- **IBM Eagle r3**: Zenodo DOI [10.5281/zenodo.17881116](https://doi.org/10.5281/zenodo.17881116) (756 QEC runs, ibm_brisbane/kyoto/osaka, 14 days)
- **Google Willow**: Zenodo DOI [10.5281/zenodo.13273331](https://doi.org/10.5281/zenodo.13273331) (420 experiments, 105-qubit, d=3,5,7)

## Requirements

All scripts use NumPy and SciPy only. Seed 42 for reproducibility.

## Key Results

| Metric | IBM Eagle r3 | Google Willow |
|--------|-------------|---------------|
| Fano factor | 0.856 (sub-Poissonian) | 2.42 (super-Poissonian) |
| Distance dependence | None (ANOVA p = 0.79) | Strong (p ~ 0) |
| Burst scaling | Linear (R^2 = 0.9999) | Quadratic (R^2 = 0.9999) |
| Spatial correlation | Anti-bunched | Bunched (+0.13) |
| Architecture | Heavy-hex (hexagonal) | Grid (square-like) |

## Companion Papers

- **Base paper**: [The Merkabit](https://doi.org/10.5281/zenodo.18925475) (Zenodo)
- **Paper 15**: [The Rotation Gap Is Flat](https://github.com/selinaserephina-star/rotation_gap_merkabit) (GitHub)
- **Full series**: Papers 1-17, Merkabit Research Series
