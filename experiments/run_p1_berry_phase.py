#!/usr/bin/env python3
"""
P1: Berry Phase Separation via Calibrated ZP-GPW
=================================================

Prediction P1: Berry phase separation = 7.13 rad between forward and
inverse ouroboros cycles. This is the prediction most unlike anything
standard quantum circuits produce.

Strategy:
  1. PRE-CALIBRATION: Measure and zero the ~43 deg systematic phase offset
     on ancilla qubit 72 using a bare Hadamard-test identity circuit.
  2. CALIBRATED ZP-GPW: Re-run geometric phase witness with Rz correction
     on ancilla, sweeping n = 2,4,6,8,10,12 ouroboros steps.
  3. BERRY PHASE EXTRACTION: Extract delta(n) with calibrated offset removed.
     Full-cycle (n=12) gives total geometric phase; compare to 7.13 rad prediction.

The 43 deg offset from Experiment 4 is likely always-on ZZ coupling between
qubits 62/72/81 or systematic ECR cross-resonance phase drift. A single
Rz(phi_cal) on qubit 72 before the Hadamard test should absorb it.

Circuit (calibration):
  anc(72): |0> -- H -- [identity on q+,q-] -- H -- measure   (X-basis)
  anc(72): |0> -- H -- [identity on q+,q-] -- Sdg -- H -- measure  (Y-basis)
  Expected: <X>=1.0, <Y>=0.0 ideally. Deviation = phi_cal.

Circuit (calibrated ZP-GPW):
  anc(72): |0> -- Rz(-phi_cal) -- H -- [ctrl-U0_n] -- H -- measure   (X)
  anc(72): |0> -- Rz(-phi_cal) -- H -- [ctrl-U0_n] -- Sdg -- H -- measure  (Y)

Authors: Stenberg & Hetland, April 2026
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

RESULTS_DIR = Path(__file__).parent.parent / "outputs" / "p1_berry"

T_CYCLE    = 12
STEP_PHASE = 2 * np.pi / T_CYCLE
GATES      = ['S', 'R', 'T', 'F', 'P']


def get_gate_angles(k: int) -> tuple[float, float, float]:
    absent     = k % 5
    gate_label = GATES[absent]
    p          = STEP_PHASE
    sym        = STEP_PHASE / 3
    w          = 2 * np.pi * k / T_CYCLE
    rx         = sym * (1.0 + 0.5 * np.cos(w))
    rz         = sym * (1.0 + 0.5 * np.cos(w + 2 * np.pi / 3))
    if gate_label == 'S': rz *= 0.4;  rx *= 1.3
    elif gate_label == 'R': rx *= 0.4; rz *= 1.3
    elif gate_label == 'T': rx *= 0.7; rz *= 0.7
    elif gate_label == 'P': p  *= 0.6; rx *= 1.8; rz *= 1.5
    return p, rz, rx


# --- Ideal signal computation ------------------------------------------------

def expected_signal(n_steps: int) -> dict:
    """Compute <00|U0_n|00> from matrix multiplication."""
    U = np.eye(4, dtype=complex)
    for k in range(n_steps):
        p, rz, rx = get_gate_angles(k)
        Rz_f = np.diag([np.exp(-1j*(rz-p)/2), np.exp(1j*(rz-p)/2)])
        Rz_i = np.diag([np.exp(-1j*(rz+p)/2), np.exp(1j*(rz+p)/2)])
        c = np.cos(rx/2); s = -1j*np.sin(rx/2)
        Rx = np.array([[c, s], [s, c]])
        U = np.kron(Rx @ Rz_f, Rx @ Rz_i) @ U
    state0 = np.array([1, 0, 0, 0], dtype=complex)
    m00 = state0.conj() @ U @ state0
    delta = float(np.angle(m00))
    return {
        "n_steps":   n_steps,
        "m00_re":    float(m00.real),
        "m00_im":    float(m00.imag),
        "magnitude": float(abs(m00)),
        "delta_rad": delta,
        "delta_deg": float(np.degrees(delta)),
    }


def berry_phase_prediction() -> dict:
    """Compute predicted Berry phase separation (forward vs inverse cycle)."""
    # Forward cycle: standard chirality +1
    U_fwd = np.eye(4, dtype=complex)
    for k in range(T_CYCLE):
        p, rz, rx = get_gate_angles(k)
        Rz_f = np.diag([np.exp(-1j*(rz-p)/2), np.exp(1j*(rz-p)/2)])
        Rz_i = np.diag([np.exp(-1j*(rz+p)/2), np.exp(1j*(rz+p)/2)])
        c = np.cos(rx/2); s = -1j*np.sin(rx/2)
        Rx = np.array([[c, s], [s, c]])
        U_fwd = np.kron(Rx @ Rz_f, Rx @ Rz_i) @ U_fwd

    # Eigenphases of full-cycle unitary
    eigenvalues = np.linalg.eigvals(U_fwd)
    phases = np.angle(eigenvalues)
    phases_sorted = np.sort(phases)

    # Total geometric phase from <00|U_fwd|00>
    state0 = np.array([1, 0, 0, 0], dtype=complex)
    m00 = state0.conj() @ U_fwd @ state0
    total_phase = np.angle(m00)

    return {
        "eigenphases_rad": phases_sorted.tolist(),
        "eigenphases_deg": np.degrees(phases_sorted).tolist(),
        "total_phase_rad": float(total_phase),
        "total_phase_deg": float(np.degrees(total_phase)),
        "m00_magnitude":   float(abs(m00)),
    }


# --- Controlled-U0 circuit primitives ----------------------------------------

def _ctrl_rz(qc, theta, anc, target):
    qc.rz(theta / 2, target)
    qc.cx(anc, target)
    qc.rz(-theta / 2, target)
    qc.cx(anc, target)


def _ctrl_rx(qc, theta, anc, target):
    qc.h(target)
    qc.rz(theta / 2, target)
    qc.cx(anc, target)
    qc.rz(-theta / 2, target)
    qc.cx(anc, target)
    qc.h(target)


def _append_ctrl_u0(qc, anc, q_fwd, q_inv, n_steps):
    for k in range(n_steps):
        p, rz, rx = get_gate_angles(k)
        _ctrl_rz(qc, rz - p, anc, q_fwd)
        _ctrl_rx(qc, rx,     anc, q_fwd)
        _ctrl_rz(qc, rz + p, anc, q_inv)
        _ctrl_rx(qc, rx,     anc, q_inv)


# --- Circuit builders --------------------------------------------------------

def build_calibration_circuit(basis: str) -> QuantumCircuit:
    """
    Calibration circuit: Hadamard test with identity on data qubits.
    Measures the systematic phase offset on ancilla.

    Virtual qubits: 0=anc, 1=q_fwd, 2=q_inv
    No controlled gates => any phase shift is hardware systematic.
    """
    assert basis in ('X', 'Y')
    qr = QuantumRegister(3, 'q')
    cr = ClassicalRegister(1, 'c')
    qc = QuantumCircuit(qr, cr)
    qc.h(qr[0])
    # Two CX gates that cancel (identity on data qubits, but expose ZZ coupling)
    qc.cx(qr[0], qr[1])
    qc.cx(qr[0], qr[1])
    qc.cx(qr[0], qr[2])
    qc.cx(qr[0], qr[2])
    if basis == 'Y':
        qc.sdg(qr[0])
    qc.h(qr[0])
    qc.measure(qr[0], cr[0])
    return qc


def build_calibrated_zpgpw(n_steps: int, basis: str,
                           phi_cal: float) -> QuantumCircuit:
    """
    ZP-GPW with pre-calibration Rz on ancilla to zero systematic offset.

    phi_cal: calibration angle in radians (from calibration step).
    Apply Rz(-phi_cal) on ancilla before H to absorb systematic phase.
    """
    assert basis in ('X', 'Y')
    qr = QuantumRegister(3, 'q')
    cr = ClassicalRegister(1, 'c')
    qc = QuantumCircuit(qr, cr)

    # Pre-calibration correction
    if abs(phi_cal) > 1e-10:
        qc.rz(-phi_cal, qr[0])

    qc.h(qr[0])
    _append_ctrl_u0(qc, 0, 1, 2, n_steps)
    if basis == 'Y':
        qc.sdg(qr[0])
    qc.h(qr[0])
    qc.measure(qr[0], cr[0])
    return qc


# --- Hardware runner ----------------------------------------------------------

def run_calibration(backend, shots, q_anc, q_fwd, q_inv):
    """Step 1: measure systematic phase offset on ancilla. Batched (1 IBM job)."""
    layout = [q_anc, q_fwd, q_inv]
    print("\n-- Calibration (X + Y basis, batched) " + "-" * 22)

    pm = generate_preset_pass_manager(
        optimization_level=1, backend=backend, initial_layout=layout)
    transpiled_x = pm.run(build_calibration_circuit('X'))
    transpiled_y = pm.run(build_calibration_circuit('Y'))
    print(f"   Cal X depth: {transpiled_x.depth()}  Cal Y depth: {transpiled_y.depth()}")

    sampler = Sampler(backend)
    job = sampler.run([transpiled_x, transpiled_y], shots=shots)
    print(f"   Batch job ID: {job.job_id()}  -- waiting ...")
    batch_result = job.result()

    results = {}
    for idx, (basis, t) in enumerate(zip(('X', 'Y'), (transpiled_x, transpiled_y))):
        counts = batch_result[idx].data.c.get_counts()
        total = sum(counts.values())
        p0 = counts.get('0', 0) / total
        exp_val = p0 - (1 - p0)
        results[basis] = {
            "counts": counts, "shots": total, "exp_val": exp_val,
            "transpiled_depth": t.depth(),
            "batch_job_id": job.job_id(), "circuit_index": idx,
        }
        print(f"   <{basis}> = {exp_val:+.4f}  depth={t.depth()}")

    x_hw = results['X']['exp_val']
    y_hw = results['Y']['exp_val']
    phi_cal = float(np.arctan2(y_hw, x_hw))
    print(f"\n   Calibration: <X>={x_hw:+.4f}  <Y>={y_hw:+.4f}")
    print(f"   Systematic offset phi_cal = {np.degrees(phi_cal):+.2f} deg")
    print(f"   (Ideal: <X>=1.0, <Y>=0.0, phi_cal=0.0)")
    return phi_cal, {"x": results['X'], "y": results['Y'],
                     "phi_cal_rad": phi_cal,
                     "phi_cal_deg": float(np.degrees(phi_cal))}


def run_calibrated_sweep(backend, phi_cal, shots, q_anc, q_fwd, q_inv,
                         step_list):
    """Step 2: calibrated ZP-GPW sweep. Batched (1 IBM job for all circuits)."""
    layout = [q_anc, q_fwd, q_inv]

    # Order: (n=steps[0],X), (n=steps[0],Y), (n=steps[1],X), ...
    order = [(n, b) for n in step_list for b in ('X', 'Y')]
    print(f"\nBuilding {len(order)} sweep circuits and transpiling...")

    pm = generate_preset_pass_manager(
        optimization_level=1, backend=backend, initial_layout=layout)
    transpiled_list = []
    for n, basis in order:
        qc = build_calibrated_zpgpw(n, basis, phi_cal)
        t = pm.run(qc)
        transpiled_list.append(t)
        print(f"  n={n:2d} {basis}: abstract depth={qc.depth()} "
              f"transpiled depth={t.depth()}")

    print(f"\nSubmitting batch of {len(transpiled_list)} circuits...")
    sampler = Sampler(backend)
    job = sampler.run(transpiled_list, shots=shots)
    print(f"Batch job ID: {job.job_id()}  -- waiting ...")
    batch_result = job.result()

    results = []
    for step_idx, n in enumerate(step_list):
        ideal = expected_signal(n)
        data = {}
        for basis_idx, basis in enumerate(('X', 'Y')):
            circuit_idx = step_idx * 2 + basis_idx
            counts = batch_result[circuit_idx].data.c.get_counts()
            total = sum(counts.values())
            p0 = counts.get('0', 0) / total
            exp_val = p0 - (1 - p0)
            data[basis] = {
                "counts": counts, "shots": total, "exp_val": exp_val,
                "transpiled_depth": transpiled_list[circuit_idx].depth(),
                "batch_job_id": job.job_id(), "circuit_index": circuit_idx,
            }

        x_hw = data['X']['exp_val']
        y_hw = data['Y']['exp_val']
        delta_hw = float(np.arctan2(y_hw, x_hw))
        mag_hw = float(np.sqrt(x_hw**2 + y_hw**2))
        entry = {
            "n_steps": n,
            "ideal": ideal,
            "x_hw": x_hw, "y_hw": y_hw,
            "delta_hw_rad": delta_hw,
            "delta_hw_deg": float(np.degrees(delta_hw)),
            "magnitude_hw": mag_hw,
            "delta_error_deg": float(np.degrees(delta_hw - ideal["delta_rad"])),
            "runs": data,
        }
        results.append(entry)
        print(f"  n={n:2d}: delta_hw={np.degrees(delta_hw):+.2f} deg  "
              f"delta_ideal={ideal['delta_deg']:+.2f} deg  "
              f"error={np.degrees(delta_hw - ideal['delta_rad']):+.2f} deg  "
              f"|M00|={mag_hw:.4f}")
    return results


# --- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="P1: Berry phase via calibrated ZP-GPW")
    parser.add_argument("--backend",  default="ibm_strasbourg")
    parser.add_argument("--token",    default=None)
    parser.add_argument("--shots",    type=int, default=8192)
    parser.add_argument("--q-anc",   type=int, default=72)
    parser.add_argument("--q-fwd",   type=int, default=62)
    parser.add_argument("--q-inv",   type=int, default=81)
    parser.add_argument("--steps",   nargs='+', type=int,
                        default=[2, 4, 6, 8, 10, 12],
                        help="Ouroboros step counts to sweep")
    parser.add_argument("--phi-cal", type=float, default=None,
                        help="Skip calibration; use this offset (degrees)")
    parser.add_argument("--sim-only", action="store_true")
    args = parser.parse_args()

    # --- Ideal predictions ---
    print("\n== P1: Berry Phase Separation ==========================")
    pred = berry_phase_prediction()
    print(f"\nFull-cycle (n=12) eigenphases:")
    for i, (r, d) in enumerate(zip(pred["eigenphases_rad"],
                                    pred["eigenphases_deg"])):
        print(f"  lambda_{i}: {r:+.4f} rad  ({d:+.2f} deg)")
    print(f"\nTotal geometric phase <00|U_12|00>:")
    print(f"  delta = {pred['total_phase_rad']:+.4f} rad  "
          f"({pred['total_phase_deg']:+.2f} deg)")
    print(f"  |M00| = {pred['m00_magnitude']:.4f}")

    print(f"\nIdeal sweep:")
    for n in args.steps:
        s = expected_signal(n)
        print(f"  n={n:2d}: <X>={s['m00_re']:+.4f}  <Y>={s['m00_im']:+.4f}  "
              f"delta={s['delta_deg']:+.2f} deg  |M00|={s['magnitude']:.4f}")

    if args.sim_only:
        return

    # --- Hardware ---
    token = args.token or os.environ.get("IBM_QUANTUM_TOKEN")
    service = QiskitRuntimeService(
        channel="ibm_quantum_platform", token=token
    ) if token else QiskitRuntimeService(channel="ibm_quantum_platform")
    backend = service.backend(args.backend)
    print(f"\nBackend: {backend.name}  ({backend.num_qubits} qubits)")
    print(f"anc={args.q_anc}  q+={args.q_fwd}  q-={args.q_inv}")

    # Step 1: Calibration
    if args.phi_cal is not None:
        phi_cal = np.radians(args.phi_cal)
        cal_data = {"phi_cal_rad": phi_cal,
                    "phi_cal_deg": args.phi_cal,
                    "source": "manual"}
        print(f"\nUsing manual calibration: phi_cal = {args.phi_cal:.2f} deg")
    else:
        phi_cal, cal_data = run_calibration(
            backend, args.shots, args.q_anc, args.q_fwd, args.q_inv)

    # Step 2: Calibrated sweep
    sweep = run_calibrated_sweep(
        backend, phi_cal, args.shots,
        args.q_anc, args.q_fwd, args.q_inv, args.steps)

    # --- Analysis ---
    print(f"\n== P1 Results ===========================================")
    print(f"Calibration offset: {np.degrees(phi_cal):+.2f} deg")
    print(f"\n{'n':>3} | {'delta_hw':>10} | {'delta_ideal':>11} | "
          f"{'error':>8} | {'|M00|_hw':>8}")
    print("-" * 58)
    for entry in sweep:
        print(f"{entry['n_steps']:>3} | "
              f"{entry['delta_hw_deg']:>+10.2f} | "
              f"{entry['ideal']['delta_deg']:>+11.2f} | "
              f"{entry['delta_error_deg']:>+8.2f} | "
              f"{entry['magnitude_hw']:>8.4f}")

    # Full-cycle Berry phase
    full_cycle = [e for e in sweep if e["n_steps"] == 12]
    if full_cycle:
        fc = full_cycle[0]
        print(f"\nFull-cycle Berry phase (n=12):")
        print(f"  Hardware:  {fc['delta_hw_rad']:+.4f} rad  "
              f"({fc['delta_hw_deg']:+.2f} deg)")
        print(f"  Predicted: {pred['total_phase_rad']:+.4f} rad  "
              f"({pred['total_phase_deg']:+.2f} deg)")

    # --- Save ---
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "experiment": "P1_berry_phase_calibrated_zpgpw",
        "prediction": "Berry phase separation = 7.13 rad",
        "calibration": cal_data,
        "sweep": sweep,
        "ideal_prediction": pred,
        "backend": backend.name,
        "qubits": {"anc": args.q_anc, "q_fwd": args.q_fwd, "q_inv": args.q_inv},
        "shots": args.shots,
        "timestamp": datetime.now().isoformat(),
    }
    path = RESULTS_DIR / f"p1_berry_{backend.name}_{ts}.json"
    with open(path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults -> {path}")


if __name__ == "__main__":
    main()
