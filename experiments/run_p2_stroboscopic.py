#!/usr/bin/env python3
"""
P2: Stroboscopic Coherence — Quasi-Period 3.3T Detection
=========================================================

Prediction P2: The ouroboros cycle has a quasi-period of 3.3T, where T = 12
ouroboros steps (one Coxeter period). After 3.3 full cycles (~40 steps),
the system should return close to its initial state, with coherence
peaking at multiples of 3.3T.

Strategy: Run U0 for n = 1..60 steps (covering 0 to 5T) and measure
the return probability P(|00>) at each step. Plot P(n) and look for:
  1. Quasi-periodic recurrences at n ~ 40, 80 (multiples of 3.3T ~ 39.6)
  2. Coherence decay envelope (from hardware noise)
  3. Comparison with simple exponential decay (null hypothesis)

The stroboscopic return probability is:
  P_return(n) = |<00|U0_n|00>|^2

On hardware, this is simply Pr(|00>) after n ouroboros steps.

Circuit (simple, low depth):
  q+ (62): |0> -- U0_n -- measure
  q- (81): |0> -- U0_n -- measure

All single-qubit gates. Transpiled depth scales linearly with n
but stays low (no CX gates).

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

RESULTS_DIR = Path(__file__).parent.parent / "outputs" / "p2_stroboscopic"

T_CYCLE    = 12
STEP_PHASE = 2 * np.pi / T_CYCLE
GATES      = ['S', 'R', 'T', 'F', 'P']
QUASI_PERIOD = 3.3 * T_CYCLE  # ~39.6 steps


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


# --- Ideal computation -------------------------------------------------------

def compute_return_probability(n_steps: int) -> dict:
    """Compute |<00|U0_n|00>|^2 from matrix multiplication."""
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
    return {
        "n": n_steps,
        "p_return": float(abs(m00)**2),
        "phase_rad": float(np.angle(m00)),
        "magnitude": float(abs(m00)),
    }


def compute_ideal_sweep(step_list):
    """Full ideal sweep."""
    return [compute_return_probability(n) for n in step_list]


# --- Circuit builder ----------------------------------------------------------

def build_stroboscopic_circuit(n_steps: int) -> QuantumCircuit:
    """n steps of U0, then measure both qubits."""
    qr = QuantumRegister(2, 'q')
    cr = ClassicalRegister(2, 'c')
    qc = QuantumCircuit(qr, cr)
    for k in range(n_steps):
        p, rz, rx = get_gate_angles(k)
        qc.rz(rz - p, qr[0])
        qc.rz(rz + p, qr[1])
        qc.rx(rx, qr[0])
        qc.rx(rx, qr[1])
    qc.measure(qr[0], cr[0])
    qc.measure(qr[1], cr[1])
    return qc


# --- Hardware runner ----------------------------------------------------------

def run_stroboscopic_sweep(backend, shots, q_fwd, q_inv, step_list):
    """Run stroboscopic measurement for each n in step_list."""
    layout = [q_fwd, q_inv]
    results = []

    for n in step_list:
        qc = build_stroboscopic_circuit(n)
        label = f"Strobo n={n}"
        print(f"\n-- {label} " + "-" * 40)
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
        p00 = counts.get('00', 0) / total
        p01 = counts.get('01', 0) / total
        p10 = counts.get('10', 0) / total
        p11 = counts.get('11', 0) / total
        zz = p00 - p01 - p10 + p11

        ideal = compute_return_probability(n)

        entry = {
            "n_steps": n,
            "p_return_hw": p00,
            "p_return_ideal": ideal["p_return"],
            "zz_hw": zz,
            "phase_ideal": ideal["phase_rad"],
            "counts": counts,
            "shots": total,
            "transpiled_depth": transpiled.depth(),
            "job_id": job.job_id(),
        }
        results.append(entry)
        print(f"   P(|00>)_hw = {p00:.4f}  ideal = {ideal['p_return']:.4f}  "
              f"<ZZ> = {zz:+.4f}")

    return results


# --- Analysis -----------------------------------------------------------------

def find_recurrences(sweep, threshold=0.5):
    """Find n values where P_return exceeds threshold (quasi-period peaks)."""
    peaks = []
    for i in range(1, len(sweep) - 1):
        p = sweep[i]["p_return_ideal"]
        if (p > sweep[i-1]["p_return_ideal"] and
            p > sweep[i+1]["p_return_ideal"] and
            p > threshold):
            peaks.append(sweep[i]["n_steps"])
    return peaks


# --- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="P2: Stroboscopic coherence for quasi-period 3.3T")
    parser.add_argument("--backend",  default="ibm_strasbourg")
    parser.add_argument("--token",    default=None)
    parser.add_argument("--shots",    type=int, default=8192)
    parser.add_argument("--q-fwd",   type=int, default=62)
    parser.add_argument("--q-inv",   type=int, default=81)
    parser.add_argument("--n-max",   type=int, default=60,
                        help="Maximum ouroboros steps (default 60 = 5T)")
    parser.add_argument("--stride",  type=int, default=1,
                        help="Step stride (default 1; use 2 for faster sweep)")
    parser.add_argument("--sim-only", action="store_true")
    args = parser.parse_args()

    step_list = list(range(1, args.n_max + 1, args.stride))

    print("\n== P2: Stroboscopic Coherence ============================")
    print(f"Prediction: quasi-period = 3.3T = {QUASI_PERIOD:.1f} steps")
    print(f"Sweep: n = 1..{args.n_max} (stride {args.stride})")

    # Ideal computation
    ideal_sweep = compute_ideal_sweep(step_list)

    # Find ideal recurrence peaks
    peaks = find_recurrences(ideal_sweep, threshold=0.3)
    print(f"\nIdeal recurrence peaks (P_return > 0.3): n = {peaks}")
    print(f"Expected at multiples of {QUASI_PERIOD:.1f}: "
          f"{[round(QUASI_PERIOD * m) for m in range(1, 4)]}")

    # Print ideal P_return at key points
    print(f"\nIdeal return probability at key steps:")
    key_steps = [12, 24, 36, 39, 40, 41, 48, 60]
    for n in key_steps:
        if n <= args.n_max:
            r = compute_return_probability(n)
            marker = " <-- 3.3T" if abs(n - QUASI_PERIOD) < 2 else ""
            marker += " <-- T" if n % 12 == 0 else ""
            print(f"  n={n:3d} ({n/12:.1f}T): P_return = {r['p_return']:.4f}  "
                  f"phase = {r['phase_rad']:+.4f} rad{marker}")

    if args.sim_only:
        return

    # Hardware
    token = args.token or os.environ.get("IBM_QUANTUM_TOKEN")
    service = QiskitRuntimeService(
        channel="ibm_quantum_platform", token=token
    ) if token else QiskitRuntimeService(channel="ibm_quantum_platform")
    backend = service.backend(args.backend)
    print(f"\nBackend: {backend.name}  ({backend.num_qubits} qubits)")
    print(f"q+={args.q_fwd}  q-={args.q_inv}  shots={args.shots}")

    sweep = run_stroboscopic_sweep(backend, args.shots,
                                   args.q_fwd, args.q_inv, step_list)

    # Summary table
    print(f"\n== P2 Results ===========================================")
    print(f"{'n':>3} | {'n/T':>5} | {'P_hw':>6} | {'P_ideal':>7} | {'<ZZ>':>6}")
    print("-" * 42)
    for e in sweep:
        n = e["n_steps"]
        marker = " *" if abs(n - QUASI_PERIOD) < 2 else ""
        print(f"{n:>3} | {n/12:>5.1f} | {e['p_return_hw']:>6.4f} | "
              f"{e['p_return_ideal']:>7.4f} | {e['zz_hw']:>+6.4f}{marker}")

    # Check for quasi-period signature
    near_3T = [e for e in sweep
               if abs(e["n_steps"] - QUASI_PERIOD) < 3]
    if near_3T:
        best = max(near_3T, key=lambda x: x["p_return_hw"])
        print(f"\nBest return near 3.3T (n={best['n_steps']}): "
              f"P_hw = {best['p_return_hw']:.4f}")

    # Save
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "experiment": "P2_stroboscopic_coherence",
        "prediction": f"quasi-period = 3.3T = {QUASI_PERIOD:.1f} steps",
        "sweep": sweep,
        "ideal_peaks": peaks,
        "backend": backend.name,
        "qubits": {"q_fwd": args.q_fwd, "q_inv": args.q_inv},
        "shots": args.shots,
        "n_max": args.n_max,
        "stride": args.stride,
        "timestamp": datetime.now().isoformat(),
    }
    path = RESULTS_DIR / f"p2_strobo_{backend.name}_{ts}.json"
    with open(path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults -> {path}")


if __name__ == "__main__":
    main()
