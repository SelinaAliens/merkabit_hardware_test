# Pentachoric Merkabit Hardware Protocol

**The first physical implementation of the merkabit dual-spinor architecture on IBM quantum hardware.**

Selina Stenberg with Claude Anthropic, April 2026

## What This Is

A complete experimental protocol for running the pentachoric merkabit on IBM Eagle r3 processors. Each merkabit node is encoded as two physical qubits (forward spinor u, inverse spinor v) with asymmetric phase evolution. The P gate -- the operation that makes a merkabit different from a qubit -- compiles to two native Rz gates with opposite signs. Zero overhead. Zero exotic hardware.

## The Key Insight

The merkabit's signature is the P gate:
```
Forward spinor:  Rz(+phi)
Inverse spinor:  Rz(-phi)
```
Two single-qubit rotations. Opposite signs. Every quantum computer on Earth can do this right now. The dual-spinor encoding, the counter-rotation, the Z3 chirality, the pentachoric error detection -- all of it emerges from this one asymmetry.

## Results (Classical Simulation)

| Configuration | Qubits | Fano Factor | Detection | Sub-Poissonian? |
|---|---|---|---|---|
| 3-merkabit triangle, tau=1 | 9 | **0.535** | 73.2% | Yes |
| 3-merkabit triangle, tau=5 | 9 | **0.52/round** | 78.2% | Yes |
| 3-merkabit triangle, tau=12 | 9 | **0.54/round** | 81.6% | Yes |
| 7-merkabit Eisenstein, tau=1 | 26 | **0.561** | 97.5% | Yes |
| Rotation gap (triangle) | -- | -- | **5.0 pp** | -- |

Per-round Fano is sub-Poissonian at every tau -- the anti-bunching is spatial, not temporal, matching the IBM hardware pattern (F = 0.856).

## Repository Structure

```
merkabit_hardware_test/
  qubit_mapper.py              Eisenstein cell topology + Eagle r3 embedding
  ouroboros_circuit.py          12-step Floquet circuits, P gate asymmetry, R-locking
  multi_merkabit_circuit.py     3-node triangle + 7-node Eisenstein cell
  run_experiment.py             Main: --mode classical|hardware, --full-gap
  run_7node_lean.py             Lean 7-node baseline test
  outputs/
    test_tau1.json              Single-merkabit error sweep (tau=1)
    triangle_results.json       3-merkabit triangle full results (tau=1,5,12)
```

## The 5-Gate Ouroboros

Gates: {S, R, T, P, F} -- vertices of the 4-simplex (pentachoron).

**R = Rotation.** When R is absent at a node, rotation is suppressed (rx * 0.4) and phase compensates (rz * 1.3). This is the R-locking event.

Absent gate cycling:
```
absent(base, chirality, t) = (base + chirality * t) mod 5
```
- Chirality 0 (centre): absent gate fixed -- static detection only
- Chirality +1 (forward): cycles forward through all 5 gates
- Chirality -1 (inverse): cycles backward -- counter-rotating

The standing wave between forward and inverse rotation is what produces dynamic error detection. At tau=5, every edge has checked all 5 gate pairings. At tau=1, each edge checks only one.

## Gate Decomposition

Per ouroboros step k, each merkabit node applies:

```
U_step(k) = U_Rx(rx_angle) @ U_Rz(rz_angle) @ U_P(p_angle)
```

All three decompose to native IBM gates (ECR + Rz + sqrt(X)):

| Gate | Forward qubit (q_u) | Inverse qubit (q_v) | Two-qubit? |
|------|-------------------|-------------------|-----------|
| P(phi) | Rz(+phi) | Rz(-phi) | **No** |
| Rz(theta) | Rz(theta) | Rz(theta) | No |
| Rx(theta) | Rx(theta) | Rx(theta) | No |

The P gate is the only asymmetric operation. It requires no entanglement, no two-qubit gates, no special calibration. The merkabit is native to every superconducting processor.

## Usage

Classical simulation (verifies circuits before hardware submission):
```bash
# Single-merkabit error sweep
python run_experiment.py --mode classical --tau 1 --shots 4096

# Full rotation gap measurement (tau=1 AND tau=5)
python run_experiment.py --mode classical --full-gap --shots 8192

# 3-merkabit triangle
python multi_merkabit_circuit.py --cell triangle --shots 4096

# 7-merkabit Eisenstein cell (lean baseline)
python run_7node_lean.py
```

Hardware execution (requires IBM Quantum account):
```bash
python run_experiment.py --mode hardware --backend ibm_strasbourg --full-gap
```

## Hardware Requirements

- IBM Eagle r3 or later (127+ qubits, heavy-hex connectivity)
- Native ECR gate direction must be respected (see Thor's validation in Paper 3 Section 2.7)
- 26 qubits for full 7-merkabit cell (14 data + 12 ancilla)
- 9 qubits for 3-merkabit triangle (6 data + 3 ancilla)
- Circuit depth: 15 layers at tau=1, ~75 layers at tau=5 (within T2 coherence budget)

## Connection to the Papers

- **Paper 15** ([The Rotation Gap Is Flat](https://doi.org/10.5281/zenodo.19417293)): Predicts 13-24 pp rotation gap, 2450x suppression, flat across error rates
- **Paper 3** ([The Rotation Gap Is Not An Error](https://github.com/SelinaAliens/The_Rotation_Gap_Is_Not_An_Error)): Sub-Poissonian F = 0.856 on IBM, super-Poissonian F = 2.42 on Google Willow, 7-19% decoder improvement
- **Base paper** ([The Merkabit](https://doi.org/10.5281/zenodo.18925475)): Architecture definition, E6 algebra, pentachoric code

## Hardware Validation So Far

Thor Henning Hetland ran a hexagonal ZZ syndrome circuit on ibm_strasbourg (Eagle r3) with native-direction CX gates and measured **F = 0.9611 < 1** -- sub-Poissonian on real hardware. The routed circuit on the same processor gives F = 1.207 (super-Poissonian), and ibm_fez (Heron r2) gives F = 18.75. The signal is architecture-specific and gate-direction-sensitive. See [Paper 3 Section 2.7](https://github.com/SelinaAliens/rotation_gap_is_flat/pull/1).

This protocol extends that validation from a ZZ parity circuit to the full pentachoric ouroboros with dual-spinor encoding.

## Dependencies

```
pip install qiskit qiskit-aer qiskit-ibm-runtime numpy
```

All simulations use seed 42 for reproducibility.
