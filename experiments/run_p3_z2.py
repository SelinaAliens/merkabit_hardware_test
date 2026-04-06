#!/usr/bin/env python3
"""
P3: Z2 Symmetry Verification on Hardware
==========================================

Prediction P3: The merkabit has exact Z2 symmetry under chirality reversal.
Swapping P gate signs (forward <-> inverse) produces a state whose
Berry phase is exactly negated: gamma_rev = -gamma_norm to machine precision.

This was verified in simulation (R_locking_test.py) to 1e-16. On hardware,
we test whether the Z2 symmetry survives noise.

Strategy:
  1. Run U0_n (forward chirality) and measure output distribution
  2. Run U0_n (reversed chirality: swap P signs on q+ and q-) and measure
  3. Compare: if Z2 exact, the probability distributions should be
     related by a specific symmetry transformation.

For the P gate:
  Forward: Rz(-p) on q+, Rz(+p) on q-
  Reversed: Rz(+p) on q+, Rz(-p) on q-  (swap roles)

Z2 test: P_fwd(|ij>) should equal P_rev(|ji>) if Z2 swaps q+ <-> q-.
More precisely: the output state under reversal is the q+/q- swap of
the forward state, so P_rev(|01>) = P_fwd(|10>) and vice versa.

We measure Z2 fidelity = sum_ij |P_fwd(ij) - P_rev(ji)| / 2.
Perfect Z2: fidelity = 0.

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

RESULTS_DIR = Path(__file__).parent.parent / "outputs" / "p3_z2"

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

def build_z2_circuit(n_steps: int, forward: bool = True) -> QuantumCircuit:
    """
    U0_n with forward or reversed chirality.

    Forward: Rz(rz-p) on q+, Rz(rz+p) on q-
    Reversed: Rz(rz+p) on q+, Rz(rz-p) on q-  (P sign swap)
    """
    qr = QuantumRegister(2, 'q')
    cr = ClassicalRegister(2, 'c')
    qc = QuantumCircuit(qr, cr)
    for k in range(n_steps):
        p, rz, rx = get_gate_angles(k)
        if forward:
            qc.rz(rz - p, qr[0])
            qc.rz(rz + p, qr[1])
        else:
            qc.rz(rz + p, qr[0])
            qc.rz(rz - p, qr[1])
        qc.rx(rx, qr[0])
        qc.rx(rx, qr[1])
    qc.measure(qr[0], cr[0])
    qc.measure(qr[1], cr[1])
    return qc


# --- Ideal simulation ---------------------------------------------------------

def simulate_z2(n_steps: int) -> dict:
    """Compute ideal output for forward and reversed, check Z2."""
    from qiskit.quantum_info import Statevector

    results = {}
    for label, forward in [("fwd", True), ("rev", False)]:
        qc = build_z2_circuit(n_steps, forward)
        qc_no_m = qc.remove_final_measurements(inplace=False)
        sv = Statevector(qc_no_m)
        probs = sv.probabilities_dict()
        results[label] = {k: probs.get(k, 0.0) for k in ['00', '01', '10', '11']}

    # Z2 check: P_fwd(ij) vs P_rev(ji)
    swap_map = {'00': '00', '01': '10', '10': '01', '11': '11'}
    z2_error = sum(abs(results["fwd"][k] - results["rev"][swap_map[k]])
                   for k in ['00', '01', '10', '11']) / 2
    return {"fwd": results["fwd"], "rev": results["rev"],
            "z2_error_ideal": z2_error}


# --- Hardware runner ----------------------------------------------------------

def run_z2_experiment(backend, shots, q_fwd, q_inv, step_list):
    """Run forward and reversed circuits for each n."""
    layout = [q_fwd, q_inv]
    results = []

    for n in step_list:
        entry = {"n_steps": n}
        ideal = simulate_z2(n)
        entry["ideal"] = ideal

        for label, forward in [("fwd", True), ("rev", False)]:
            qc = build_z2_circuit(n, forward)
            print(f"\n-- Z2 n={n} {label} " + "-" * 35)
            print(f"   Abstract depth: {qc.depth()}")

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
            probs = {k: counts.get(k, 0) / total for k in ['00', '01', '10', '11']}

            entry[label] = {
                "probs": probs, "counts": counts, "shots": total,
                "transpiled_depth": transpiled.depth(),
                "job_id": job.job_id(),
            }
            print(f"   P(00)={probs['00']:.4f}  P(01)={probs['01']:.4f}  "
                  f"P(10)={probs['10']:.4f}  P(11)={probs['11']:.4f}")

        # Z2 fidelity: compare P_fwd(ij) with P_rev(ji)
        swap_map = {'00': '00', '01': '10', '10': '01', '11': '11'}
        z2_error_hw = sum(
            abs(entry["fwd"]["probs"][k] - entry["rev"]["probs"][swap_map[k]])
            for k in ['00', '01', '10', '11']
        ) / 2

        # Also compare ZZ correlations
        zz_fwd = (entry["fwd"]["probs"]['00'] + entry["fwd"]["probs"]['11']
                  - entry["fwd"]["probs"]['01'] - entry["fwd"]["probs"]['10'])
        zz_rev = (entry["rev"]["probs"]['00'] + entry["rev"]["probs"]['11']
                  - entry["rev"]["probs"]['01'] - entry["rev"]["probs"]['10'])

        entry["z2_error_hw"] = z2_error_hw
        entry["z2_error_ideal"] = ideal["z2_error_ideal"]
        entry["zz_fwd"] = zz_fwd
        entry["zz_rev"] = zz_rev
        entry["zz_sum"] = zz_fwd + zz_rev  # should be ~0 if Z2 exact (odd under swap)

        results.append(entry)
        print(f"\n   Z2 error: hw={z2_error_hw:.4f}  ideal={ideal['z2_error_ideal']:.6f}")
        print(f"   <ZZ>_fwd={zz_fwd:+.4f}  <ZZ>_rev={zz_rev:+.4f}  "
              f"sum={zz_fwd + zz_rev:+.4f}")

    return results


# --- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="P3: Z2 symmetry verification on hardware")
    parser.add_argument("--backend",  default="ibm_strasbourg")
    parser.add_argument("--token",    default=None)
    parser.add_argument("--shots",    type=int, default=8192)
    parser.add_argument("--q-fwd",   type=int, default=62)
    parser.add_argument("--q-inv",   type=int, default=81)
    parser.add_argument("--steps",   nargs='+', type=int,
                        default=[4, 6, 8, 12],
                        help="Ouroboros step counts to test")
    parser.add_argument("--sim-only", action="store_true")
    args = parser.parse_args()

    print("\n== P3: Z2 Symmetry Verification =========================")
    print("Prediction: gamma_rev = -gamma_norm (exact to 1e-16 in sim)")
    print("Test: P_fwd(|ij>) = P_rev(|ji>) under chirality reversal\n")

    # Ideal
    print("Ideal Z2 check:")
    for n in args.steps:
        sim = simulate_z2(n)
        print(f"  n={n:2d}: Z2 error = {sim['z2_error_ideal']:.2e}  "
              f"(expect ~0)")
        for k in ['00', '01', '10', '11']:
            swap_map = {'00': '00', '01': '10', '10': '01', '11': '11'}
            print(f"    |{k}> fwd={sim['fwd'][k]:.6f}  "
                  f"rev[swap]={sim['rev'][swap_map[k]]:.6f}")

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

    sweep = run_z2_experiment(backend, args.shots,
                              args.q_fwd, args.q_inv, args.steps)

    # Summary
    print(f"\n== P3 Results ===========================================")
    print(f"{'n':>3} | {'Z2_err_hw':>10} | {'Z2_err_ideal':>12} | "
          f"{'<ZZ>_fwd':>9} | {'<ZZ>_rev':>9} | {'<ZZ>_sum':>9}")
    print("-" * 68)
    for e in sweep:
        print(f"{e['n_steps']:>3} | "
              f"{e['z2_error_hw']:>10.4f} | "
              f"{e['z2_error_ideal']:>12.2e} | "
              f"{e['zz_fwd']:>+9.4f} | "
              f"{e['zz_rev']:>+9.4f} | "
              f"{e['zz_sum']:>+9.4f}")

    mean_z2 = np.mean([e["z2_error_hw"] for e in sweep])
    print(f"\nMean Z2 error (hardware): {mean_z2:.4f}")
    print(f"Z2 CONFIRMED if error < readout noise (~0.03)")

    # Save
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "experiment": "P3_z2_symmetry",
        "prediction": "Z2 exact: gamma_rev = -gamma_norm",
        "sweep": sweep,
        "mean_z2_error": mean_z2,
        "backend": backend.name,
        "qubits": {"q_fwd": args.q_fwd, "q_inv": args.q_inv},
        "shots": args.shots,
        "timestamp": datetime.now().isoformat(),
    }
    path = RESULTS_DIR / f"p3_z2_{backend.name}_{ts}.json"
    with open(path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults -> {path}")


if __name__ == "__main__":
    main()
