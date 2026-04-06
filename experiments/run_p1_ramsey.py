#!/usr/bin/env python3
"""
P1 (Alternative): Ramsey Interferometry for Berry Phase — No Ancilla
====================================================================

Measures the Berry phase directly on the data qubits without a
controlled-U0 ancilla circuit. Avoids the depth penalty of ctrl-U0
(which doubled CX count and introduced the 43 deg offset).

Strategy: Ramsey sequence on the RELATIVE phase between forward and
inverse spinors.

Circuit:
  q+ (62): |0> -- Ry(pi/2) -- U0_n -- Ry(-pi/2) -- measure
  q- (81): |0> -- Ry(pi/2) -- U0_n -- Ry(-pi/2) -- measure

The Ry(pi/2) prepares |+> on both qubits. After U0_n, the accumulated
geometric phase rotates the Bloch vector. The closing Ry(-pi/2) maps
the phase into a population measurement:

  P(0) = (1 + cos(delta_geo + delta_dyn)) / 2

To separate geometric from dynamical phase:
  Run 1: Forward cycle   (chirality +1): delta_total = delta_geo + delta_dyn
  Run 2: Reversed cycle  (chirality -1): delta_total = -delta_geo + delta_dyn
  Berry phase = (delta_fwd - delta_rev) / 2

The reversed cycle swaps P gate signs: Rz(+p) on q+, Rz(-p) on q-.
This is the Z2 chirality flip — reversed = forward with P sign swapped.

Depth: only single-qubit gates (Rz, Rx, Ry). Transpiled depth ~ 6.
No CX gates. No ancilla. Maximum signal, minimum noise.

Sweep n = 1..12 to trace out delta(n) and extract the full-cycle Berry phase.

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

RESULTS_DIR = Path(__file__).parent.parent / "outputs" / "p1_ramsey"

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


# --- Circuit builders --------------------------------------------------------

def _append_u0(qc, q_fwd, q_inv, n_steps, forward=True):
    """Append n ouroboros steps. forward=False swaps P gate signs (Z2 reversal)."""
    for k in range(n_steps):
        p, rz, rx = get_gate_angles(k)
        if forward:
            qc.rz(rz - p, q_fwd)
            qc.rz(rz + p, q_inv)
        else:
            # Reversed chirality: swap P sign
            qc.rz(rz + p, q_fwd)
            qc.rz(rz - p, q_inv)
        qc.rx(rx, q_fwd)
        qc.rx(rx, q_inv)


def build_ramsey_circuit(n_steps: int, forward: bool = True,
                         tomography_axis: str = 'Z') -> QuantumCircuit:
    """
    Ramsey interferometry on the merkabit.

    tomography_axis:
      'Z': Ry(pi/2) -- U0_n -- Ry(-pi/2) -- measure (phase -> population)
      'X': Ry(pi/2) -- U0_n -- measure (X-basis readout via Ry prep)
      'Y': Rx(-pi/2) -- U0_n -- Rx(pi/2) -- measure (Y-basis readout)
    """
    qr = QuantumRegister(2, 'q')
    cr = ClassicalRegister(2, 'c')
    qc = QuantumCircuit(qr, cr)

    if tomography_axis == 'Z':
        # Prepare |+> state
        qc.ry(np.pi / 2, qr[0])
        qc.ry(np.pi / 2, qr[1])
        # Apply ouroboros
        _append_u0(qc, 0, 1, n_steps, forward)
        # Close Ramsey: map phase to population
        qc.ry(-np.pi / 2, qr[0])
        qc.ry(-np.pi / 2, qr[1])
    elif tomography_axis == 'X':
        # Prepare |+>
        qc.ry(np.pi / 2, qr[0])
        qc.ry(np.pi / 2, qr[1])
        # Apply ouroboros
        _append_u0(qc, 0, 1, n_steps, forward)
        # No closing rotation — measure in X basis (via H)
        qc.h(qr[0])
        qc.h(qr[1])
    elif tomography_axis == 'Y':
        # Prepare in Y eigenstate
        qc.rx(-np.pi / 2, qr[0])
        qc.rx(-np.pi / 2, qr[1])
        # Apply ouroboros
        _append_u0(qc, 0, 1, n_steps, forward)
        # Close
        qc.rx(np.pi / 2, qr[0])
        qc.rx(np.pi / 2, qr[1])

    qc.measure(qr[0], cr[0])
    qc.measure(qr[1], cr[1])
    return qc


# --- Ideal simulation ---------------------------------------------------------

def simulate_ramsey(n_steps: int, forward: bool = True) -> dict:
    """Ideal Ramsey signal via statevector."""
    from qiskit.quantum_info import Statevector
    results = {}
    for axis in ('Z', 'X', 'Y'):
        qc = build_ramsey_circuit(n_steps, forward, axis)
        qc_no_m = qc.remove_final_measurements(inplace=False)
        sv = Statevector(qc_no_m)
        probs = sv.probabilities_dict()
        p00 = probs.get('00', 0.0)
        p01 = probs.get('01', 0.0)
        p10 = probs.get('10', 0.0)
        p11 = probs.get('11', 0.0)
        # Per-qubit expectation values
        z_fwd = (p00 + p01) - (p10 + p11)  # <Z> on q+
        z_inv = (p00 + p10) - (p01 + p11)  # <Z> on q-
        zz = p00 - p01 - p10 + p11         # <ZZ>
        results[axis] = {
            "probs": probs,
            "z_fwd": float(z_fwd),
            "z_inv": float(z_inv),
            "zz": float(zz),
        }
    return results


# --- Hardware runner ----------------------------------------------------------

def run_circuit(backend, qc, layout, shots, label):
    print(f"\n-- {label} " + "-" * max(0, 55 - len(label)))
    print(f"   Abstract depth: {qc.depth()}   gates: {qc.size()}")
    pm = generate_preset_pass_manager(
        optimization_level=1, backend=backend, initial_layout=layout)
    transpiled = pm.run(qc)
    print(f"   Transpiled depth: {transpiled.depth()}")
    sampler = Sampler(backend)
    job = sampler.run([transpiled], shots=shots)
    print(f"   Job ID: {job.job_id()}  -- waiting ...")
    result = job.result()
    counts = result[0].data.c.get_counts()
    total = sum(counts.values())
    probs = {k: v / total for k, v in counts.items()}
    p00 = probs.get('00', 0.0)
    p01 = probs.get('01', 0.0)
    p10 = probs.get('10', 0.0)
    p11 = probs.get('11', 0.0)
    z_fwd = (p00 + p01) - (p10 + p11)
    z_inv = (p00 + p10) - (p01 + p11)
    zz = p00 - p01 - p10 + p11
    print(f"   <Z+>={z_fwd:+.4f}  <Z->={z_inv:+.4f}  <ZZ>={zz:+.4f}")
    return {
        "label": label, "counts": counts, "shots": total, "probs": probs,
        "z_fwd": z_fwd, "z_inv": z_inv, "zz": zz,
        "transpiled_depth": transpiled.depth(),
        "job_id": job.job_id(),
    }


def run_ramsey_sweep(backend, shots, q_fwd, q_inv, step_list):
    """Run forward and reversed Ramsey for each n, extract Berry phase."""
    layout = [q_fwd, q_inv]
    results = []

    for n in step_list:
        entry = {"n_steps": n}

        for direction, forward in [("fwd", True), ("rev", False)]:
            dir_data = {}
            for axis in ('Z',):  # Z-axis Ramsey is the primary signal
                qc = build_ramsey_circuit(n, forward, axis)
                r = run_circuit(backend, qc, layout, shots,
                                f"Ramsey n={n} {direction} {axis}")
                dir_data[axis] = r
            entry[direction] = dir_data

        # Extract per-qubit phases from Z-axis Ramsey
        # P(0) = (1 + cos(delta))/2 => delta = arccos(2*P(0) - 1)
        # Using <Z> = cos(delta) directly
        z_fwd_f = entry["fwd"]["Z"]["z_fwd"]
        z_fwd_r = entry["rev"]["Z"]["z_fwd"]
        z_inv_f = entry["fwd"]["Z"]["z_inv"]
        z_inv_r = entry["rev"]["Z"]["z_inv"]

        # Berry phase on q+ = (delta_fwd - delta_rev) / 2
        # delta = arccos(<Z>), but sign from full tomography
        # For now: use <Z> difference as proxy
        entry["z_fwd_diff"] = z_fwd_f - z_fwd_r
        entry["z_inv_diff"] = z_inv_f - z_inv_r
        entry["zz_fwd"] = entry["fwd"]["Z"]["zz"]
        entry["zz_rev"] = entry["rev"]["Z"]["zz"]
        entry["zz_diff"] = entry["fwd"]["Z"]["zz"] - entry["rev"]["Z"]["zz"]

        results.append(entry)
        print(f"\n   n={n}: <Z+>_fwd-rev = {entry['z_fwd_diff']:+.4f}  "
              f"<Z->_fwd-rev = {entry['z_inv_diff']:+.4f}  "
              f"<ZZ>_diff = {entry['zz_diff']:+.4f}")

    return results


# --- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="P1: Ramsey interferometry for Berry phase (no ancilla)")
    parser.add_argument("--backend",  default="ibm_strasbourg")
    parser.add_argument("--token",    default=None)
    parser.add_argument("--shots",    type=int, default=8192)
    parser.add_argument("--q-fwd",   type=int, default=62)
    parser.add_argument("--q-inv",   type=int, default=81)
    parser.add_argument("--steps",   nargs='+', type=int,
                        default=[1, 2, 3, 4, 6, 8, 10, 12],
                        help="Ouroboros step counts to sweep")
    parser.add_argument("--sim-only", action="store_true")
    args = parser.parse_args()

    print("\n== P1 Ramsey: Berry Phase Without Ancilla ===============")
    print("Strategy: forward vs reversed chirality Ramsey interferometry")
    print("Berry phase = (delta_fwd - delta_rev) / 2\n")

    # Ideal predictions
    print("Ideal Ramsey signals (noiseless):")
    for n in args.steps:
        sim_f = simulate_ramsey(n, forward=True)
        sim_r = simulate_ramsey(n, forward=False)
        z_diff = sim_f['Z']['z_fwd'] - sim_r['Z']['z_fwd']
        print(f"  n={n:2d}: <Z+>_fwd={sim_f['Z']['z_fwd']:+.4f}  "
              f"<Z+>_rev={sim_r['Z']['z_fwd']:+.4f}  "
              f"diff={z_diff:+.4f}  "
              f"<ZZ>_fwd={sim_f['Z']['zz']:+.4f}  "
              f"<ZZ>_rev={sim_r['Z']['zz']:+.4f}")

    if args.sim_only:
        return

    # Hardware
    token = args.token or os.environ.get("IBM_QUANTUM_TOKEN")
    service = QiskitRuntimeService(
        channel="ibm_quantum_platform", token=token
    ) if token else QiskitRuntimeService(channel="ibm_quantum_platform")
    backend = service.backend(args.backend)
    print(f"\nBackend: {backend.name}  ({backend.num_qubits} qubits)")
    print(f"q+={args.q_fwd}  q-={args.q_inv}")

    sweep = run_ramsey_sweep(backend, args.shots, args.q_fwd, args.q_inv,
                             args.steps)

    # Summary
    print(f"\n== P1 Ramsey Results ====================================")
    print(f"{'n':>3} | {'<Z+>_fwd':>9} | {'<Z+>_rev':>9} | "
          f"{'diff':>7} | {'<ZZ>_fwd':>9} | {'<ZZ>_rev':>9}")
    print("-" * 65)
    for e in sweep:
        print(f"{e['n_steps']:>3} | "
              f"{e['fwd']['Z']['z_fwd']:>+9.4f} | "
              f"{e['rev']['Z']['z_fwd']:>+9.4f} | "
              f"{e['z_fwd_diff']:>+7.4f} | "
              f"{e['zz_fwd']:>+9.4f} | "
              f"{e['zz_rev']:>+9.4f}")

    # Save
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "experiment": "P1_ramsey_berry_phase",
        "prediction": "Berry phase separation = 7.13 rad",
        "method": "forward_vs_reversed_chirality_ramsey",
        "sweep": sweep,
        "backend": backend.name,
        "qubits": {"q_fwd": args.q_fwd, "q_inv": args.q_inv},
        "shots": args.shots,
        "timestamp": datetime.now().isoformat(),
    }
    path = RESULTS_DIR / f"p1_ramsey_{backend.name}_{ts}.json"
    with open(path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults -> {path}")


if __name__ == "__main__":
    main()
