# Merkabit Hardware Experiment Map

**For: Thor (and collaborators)**
**Hardware: ibm_strasbourg (Eagle r3, 127-qubit)**
**Validated qubit region: q+=62, q-=81, anc=72**

---

## Overview

```
                    ┌─────────────────────────────┐
                    │   ROTATION GAP (critical)    │
                    │   9 qubits, CX-heavy         │
                    │   run_rotation_gap_hardware   │
                    └──────────────┬───────────────┘
                                  │
              confirms multi-merkabit works on hardware
                                  │
         ┌────────────────────────┼────────────────────────┐
         │                        │                        │
   ┌─────▼──────┐          ┌─────▼──────┐          ┌──────▼─────┐
   │  P1: BERRY  │          │  P3: Z2    │          │  P5: DTC   │
   │  PHASE      │          │  SYMMETRY  │          │  SURVIVAL  │
   │  (7.13 rad) │          │  (exact)   │          │ (subharm.) │
   └──┬───────┬──┘          └────────────┘          └──────┬─────┘
      │       │                                            │
  ┌───▼──┐ ┌──▼────┐                                ┌─────▼──────┐
  │ ZP-  │ │Ramsey │                                │P2: STROBO  │
  │ GPW  │ │(no    │                                │(quasi-     │
  │(anc) │ │ancilla│                                │period 3.3T)│
  └──────┘ └───────┘                                └────────────┘
```

---

## Quick Reference

| # | Experiment | Script | Qubits | CX gates | Depth | Shots est. |
|---|-----------|--------|--------|----------|-------|------------|
| 0 | **Rotation Gap** | `run_rotation_gap_hardware.py` | 9 | 6/round | 50-300 | ~49K |
| 1a | P1 Berry (calibrated) | `run_p1_berry_phase.py` | 3 | 8/step | 200-360 | ~115K |
| 1b | P1 Berry (Ramsey) | `run_p1_ramsey.py` | 2 | **0** | 50-80 | ~131K |
| 2 | P2 Stroboscopic | `run_p2_stroboscopic.py` | 2 | **0** | linear | ~492K |
| 3 | P3 Z2 Symmetry | `run_p3_z2.py` | 2 | **0** | 40-100 | ~66K |
| 4 | P5 DTC Survival | `run_p5_dtc.py` | 2 | **0** | ~200 | ~590K |

**Total budget: ~1.44M shots** (all experiments, default settings)

---

## Execution Order (recommended)

### Phase 1: Validate locally first

Run `--sim-only` on everything before spending IBM credits:

```bash
cd merkabit_hardware

python experiments/run_rotation_gap_hardware.py --sim-only
python experiments/run_p1_berry_phase.py --sim-only
python experiments/run_p1_ramsey.py --sim-only
python experiments/run_p2_stroboscopic.py --sim-only --stride 4
python experiments/run_p3_z2.py --sim-only
python experiments/run_p5_dtc.py --sim-only
```

### Phase 2: Hardware — Priority Order

**STEP 0 — Rotation Gap (THE critical test)**
```bash
python experiments/run_rotation_gap_hardware.py --tau 1 3 5 --shots 8192
```
- Tests: detection_rate(dynamic) > detection_rate(static), Fano < 1
- This is what turns simulation claims into hardware facts
- 9 qubits, ~30 CX max (tau=5), well within decoherence budget
- Runs paired + unpaired control at each tau
- Auto-discovers qubit layout; use `--manual-layout` as fallback
- **IMPORTANT**: Script now handles native CX direction (Experiment 3 caveat).
  It detects whether CX(data->anc) or CX(anc->data) is native and applies
  H-conjugation if needed. The CX strategy is logged in output JSON.

**Success**: gap > 0 pp, Fano < 1.0, counter-rotating edges fire more

---

**STEP 1a — P1 Berry Phase (calibrated ZP-GPW)**
```bash
python experiments/run_p1_berry_phase.py --steps 2 4 6 8 10 12
```
- First runs calibration (bare Hadamard test) to measure the ~43 deg offset
- Then sweeps n=2..12 with Rz(-phi_cal) correction on ancilla
- If you already know the offset: `--phi-cal 43` skips calibration
- 3 qubits (62, 72, 81), uses CX (controlled-U0 via Hadamard test)
- Depth: 200-360 at n=12, pushes decoherence limit

**Success**: delta(n=12) matches prediction, phase accumulates in correct direction

**STEP 1b — P1 Berry Phase (Ramsey, backup)**
```bash
python experiments/run_p1_ramsey.py --steps 1 2 3 4 6 8 10 12
```
- NO ancilla, NO CX gates — pure single-qubit circuit
- Forward chirality vs reversed chirality (P sign swap)
- Berry phase = (delta_fwd - delta_rev) / 2
- 2 qubits only, depth ~50-80, maximum signal
- Run this even if 1a works — it's independent confirmation

**Success**: z_fwd - z_rev shows clear trend matching prediction

---

**STEP 2 — P3 Z2 Symmetry (quick win)**
```bash
python experiments/run_p3_z2.py --steps 4 6 8 12
```
- Cheapest experiment: 8 circuits, zero CX
- Forward vs reversed output distributions
- Tests: P_fwd(|01>) = P_rev(|10>) (qubit-swap symmetry)
- Simulation shows Z2 error = 1e-16; hardware should show < 0.03

**Success**: Z2_error < readout noise (~0.03), ZZ_sum ~ 0

---

**STEP 3 — P2 Stroboscopic Coherence**
```bash
# Fast survey first
python experiments/run_p2_stroboscopic.py --stride 2 --n-max 60

# If promising, refine near the peak
python experiments/run_p2_stroboscopic.py --stride 1 --n-max 48
```
- Measures P(|00>) return probability at each step n=1..60
- Looking for recurrence peak near n ~ 40 (= 3.3 x 12 steps)
- Zero CX, depth scales linearly with n
- At n=60 the depth is ~250 — watch for decoherence

**Success**: P(|00>) peak near n=40 above naive decay envelope

---

**STEP 4 — P5 DTC Survival**
```bash
# Clean run first
python experiments/run_p5_dtc.py --n-max 48 --shots 4096

# Then with perturbation
python experiments/run_p5_dtc.py --n-max 48 --shots 4096 --epsilon 0.05
```
- Measures <ZZ>(n) time series, Fourier analysis for 1/(2T) peak
- Three modes: paired (merkabit), unpaired (control), perturbed
- DTC ratio = power(2T)/power(T), should be > 1 for paired
- Most shot-intensive experiment — can reduce shots to 4096

**Success**: DTC ratio > 1 (paired), DTC ratio ~ 1 (control), survives epsilon

---

## CX Direction Caveat (MUST READ)

From Experiment 3 on ibm_strasbourg:

**Finding**: Native CX direction is 72->62 and 72->81 (ancilla controls data).
The intended CX(data->anc) for Z-parity is NON-NATIVE on this qubit region.

**Impact**:
- `run_rotation_gap_hardware.py`: HANDLED. Script auto-detects native direction
  and applies H-conjugation when needed. Strategy logged per edge.
- `run_p1_berry_phase.py`: Uses CX(anc->target), which IS native. No issue.
- All other experiments: Zero CX gates. Not affected.

**For reviewer documentation**: The sign of <XX> = -0.45 (Experiment 3) is
PHYSICAL, not a gate convention artifact. Equal magnitude opposite sign
(ZZ=+0.44, XX=-0.45) is the |Phi-> signature of pi-lock. A convention
artifact would shift both signs or change magnitudes.

---

## Output Locations

All results save to `outputs/` subdirectories:

```
outputs/
  rotation_gap/    <- rotation_gap_ibm_strasbourg_YYYYMMDD_HHMMSS.json
  p1_berry/        <- p1_berry_ibm_strasbourg_YYYYMMDD_HHMMSS.json
  p1_ramsey/       <- p1_ramsey_ibm_strasbourg_YYYYMMDD_HHMMSS.json
  p2_stroboscopic/ <- p2_strobo_ibm_strasbourg_YYYYMMDD_HHMMSS.json
  p3_z2/           <- p3_z2_ibm_strasbourg_YYYYMMDD_HHMMSS.json
  p5_dtc/          <- p5_dtc_ibm_strasbourg_YYYYMMDD_HHMMSS.json
```

Each JSON contains: raw counts, analysis, ideal predictions, backend info,
qubit assignments, timestamps, and job IDs for IBM audit trail.

---

## Prediction Summary

| ID | Prediction | Expected Value | Null Hypothesis |
|----|-----------|----------------|-----------------|
| P0 | Rotation gap | ~5 pp | gap = 0 (no difference static/dynamic) |
| P1 | Berry phase separation | 7.13 rad | random phase / no accumulation |
| P2 | Quasi-period | 3.3T = 39.6 steps | no recurrence / exponential decay |
| P3 | Z2 symmetry | exact (error < 0.03) | broken by noise |
| P5 | DTC subharmonic | ratio > 1 at 1/(2T) | no period doubling |

---

## If Something Fails

- **Depth too high** (> 300): Reduce tau or n. The rotation gap at tau=3
  (18 CX) is still meaningful. P1 Ramsey has zero CX — always works.
- **Layout discovery fails**: Use `--manual-layout` with the validated
  62/72/81 region and manually verify coupling map neighbors.
- **Calibration offset changed**: The 43 deg offset may drift between
  calibration sessions. Always run calibration fresh (Step 1a) or use
  the Ramsey approach (Step 1b) which doesn't need calibration.
- **Fano > 1**: If sub-Poissonian signature is lost, check if readout
  error mitigation is needed. Hardware noise can inflate variance.
