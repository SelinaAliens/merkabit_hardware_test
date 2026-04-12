#!/usr/bin/env python3
"""
P5: Discrete Time Crystal Survival on Hardware
================================================

Prediction P5: The merkabit ouroboros cycle exhibits DTC-like behaviour —
the Floquet-driven system locks to a subharmonic of the drive frequency
and this locking survives perturbation.

DTC signature: period-doubling. Under the ouroboros drive with period T=12,
the system should exhibit a response at period 2T (24 steps), visible as
a persistent oscillation in <ZZ> or <Z> that does not decay to zero even
under perturbation.

Strategy:
  1. CLEAN DTC: Run U0 for n=1..48 steps (4T), measure <ZZ> at each step.
     Look for period-2T oscillation in <ZZ>(n).
  2. PERTURBED DTC: Add small random perturbations to gate angles (epsilon)
     and check if the oscillation survives.
  3. CONTROL: Run with all P gates removed (unpaired, no chirality).
     DTC should NOT appear in the control.

DTC test observable: autocorrelation of <ZZ>(n) at lag T and 2T.
  C(lag) = <ZZ(n) * ZZ(n+lag)> averaged over n.
  DTC: C(2T) > C(T) (period doubling: 2T correlation stronger than T).

Also measure: Fourier spectrum of <ZZ>(n). DTC peak at frequency 1/(2T).

Circuit: identical to P2 stroboscopic, but with analysis focused on
oscillation persistence rather than return probability.

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

RESULTS_DIR = Path(__file__).parent.parent / "outputs" / "p5_dtc"

T_CYCLE    = 12
STEP_PHASE = 2 * np.pi / T_CYCLE
GATES      = ['S', 'R', 'T', 'F', 'P']


def get_gate_angles(k: int, epsilon: float = 0.0,
                    rng: np.random.Generator = None) -> tuple[float, float, float]:
    """Gate angles with optional perturbation epsilon."""
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
    if epsilon > 0 and rng is not None:
        p  *= (1 + epsilon * rng.standard_normal())
        rz *= (1 + epsilon * rng.standard_normal())
        rx *= (1 + epsilon * rng.standard_normal())
    return p, rz, rx


# --- Circuit builder ----------------------------------------------------------

def build_dtc_circuit(n_steps: int, paired: bool = True,
                      epsilon: float = 0.0, seed: int = 42) -> QuantumCircuit:
    """
    n steps of ouroboros with optional perturbation.

    paired=True: full merkabit (P gate active)
    paired=False: control (no P gate asymmetry)
    epsilon>0: random perturbation of gate angles
    """
    rng = np.random.default_rng(seed) if epsilon > 0 else None
    qr = QuantumRegister(2, 'q')
    cr = ClassicalRegister(2, 'c')
    qc = QuantumCircuit(qr, cr)
    for k in range(n_steps):
        p, rz, rx = get_gate_angles(k, epsilon, rng)
        if paired:
            qc.rz(rz - p, qr[0])
            qc.rz(rz + p, qr[1])
        else:
            qc.rz(rz, qr[0])
            qc.rz(rz, qr[1])
        qc.rx(rx, qr[0])
        qc.rx(rx, qr[1])
    qc.measure(qr[0], cr[0])
    qc.measure(qr[1], cr[1])
    return qc


# --- Ideal computation --------------------------------------------------------

def compute_ideal_zz_series(n_max, paired=True, epsilon=0.0, seed=42):
    """Compute ideal <ZZ>(n) for n=1..n_max."""
    rng = np.random.default_rng(seed) if epsilon > 0 else None
    zz_series = []
    U = np.eye(4, dtype=complex)
    state0 = np.array([1, 0, 0, 0], dtype=complex)
    ZZ = np.diag([1, -1, -1, 1])  # Z tensor Z

    for k in range(n_max):
        p, rz, rx = get_gate_angles(k, epsilon, rng)
        if paired:
            Rz_f = np.diag([np.exp(-1j*(rz-p)/2), np.exp(1j*(rz-p)/2)])
            Rz_i = np.diag([np.exp(-1j*(rz+p)/2), np.exp(1j*(rz+p)/2)])
        else:
            Rz_f = np.diag([np.exp(-1j*rz/2), np.exp(1j*rz/2)])
            Rz_i = Rz_f.copy()
        c = np.cos(rx/2); s = -1j*np.sin(rx/2)
        Rx = np.array([[c, s], [s, c]])
        U = np.kron(Rx @ Rz_f, Rx @ Rz_i) @ U
        psi = U @ state0
        zz_val = float(np.real(psi.conj() @ ZZ @ psi))
        zz_series.append(zz_val)

    return zz_series


def analyze_dtc_signal(zz_series: list, T: int = 12) -> dict:
    """Analyze <ZZ> time series for DTC signatures."""
    zz = np.array(zz_series)
    n = len(zz)

    # Fourier analysis
    fft = np.fft.rfft(zz)
    freqs = np.fft.rfftfreq(n, d=1.0)
    power = np.abs(fft)**2

    # Find peaks at 1/T and 1/(2T)
    f_T = 1.0 / T
    f_2T = 1.0 / (2 * T)
    idx_T = np.argmin(np.abs(freqs - f_T))
    idx_2T = np.argmin(np.abs(freqs - f_2T))

    # Autocorrelation at lag T and 2T
    if n > 2 * T:
        acf_T = np.mean(zz[:n-T] * zz[T:n])
        acf_2T = np.mean(zz[:n-2*T] * zz[2*T:n])
    else:
        acf_T = acf_2T = float('nan')

    return {
        "power_at_T": float(power[idx_T]),
        "power_at_2T": float(power[idx_2T]),
        "freq_at_T": float(freqs[idx_T]),
        "freq_at_2T": float(freqs[idx_2T]),
        "acf_lag_T": float(acf_T),
        "acf_lag_2T": float(acf_2T),
        "dtc_ratio": float(power[idx_2T] / (power[idx_T] + 1e-30)),
        "mean_zz": float(np.mean(zz)),
        "std_zz": float(np.std(zz)),
    }


# --- Hardware runner ----------------------------------------------------------

def run_dtc_sweep(backend, shots, q_fwd, q_inv, step_list, paired, epsilon, seed):
    """
    Run DTC measurement for steps in step_list.

    All circuits are batched into a single sampler.run() call — one IBM job
    per sweep, not one job per step.
    """
    layout = [q_fwd, q_inv]
    mode = "paired" if paired else "unpaired"
    eps_str = f" eps={epsilon}" if epsilon > 0 else ""
    print(f"Building {len(step_list)} circuits ({mode}{eps_str}) and transpiling...")

    # Build and transpile all circuits up front
    pm = generate_preset_pass_manager(
        optimization_level=1, backend=backend, initial_layout=layout)
    transpiled_list = []
    raw_circuits = []
    for n in step_list:
        qc = build_dtc_circuit(n, paired, epsilon, seed)
        transpiled_list.append(pm.run(qc))
        raw_circuits.append(qc)
        if n <= 3 or n % 12 == 0 or n == step_list[-1]:
            print(f"  n={n:3d}: abstract depth={qc.depth()} "
                  f"transpiled depth={transpiled_list[-1].depth()}")

    # Single batched job
    print(f"Submitting batch of {len(transpiled_list)} circuits...")
    sampler = Sampler(backend)
    job = sampler.run(transpiled_list, shots=shots)
    print(f"Batch job ID: {job.job_id()}  -- waiting ...")
    batch_result = job.result()

    # Parse results by index
    zz_series = []
    raw_data = []
    for idx, n in enumerate(step_list):
        counts = batch_result[idx].data.c.get_counts()
        total = sum(counts.values())
        p00 = counts.get('00', 0) / total
        p01 = counts.get('01', 0) / total
        p10 = counts.get('10', 0) / total
        p11 = counts.get('11', 0) / total
        zz = p00 - p01 - p10 + p11

        zz_series.append(zz)
        raw_data.append({
            "n": n, "zz": zz, "p00": p00, "p01": p01, "p10": p10, "p11": p11,
            "counts": counts, "shots": total, "batch_job_id": job.job_id(),
            "circuit_index": idx,
            "transpiled_depth": transpiled_list[idx].depth(),
        })

        if n <= 3 or n % 12 == 0 or n == step_list[-1]:
            print(f"  n={n:3d}: <ZZ>={zz:+.4f}  P(00)={p00:.4f}  "
                  f"depth={transpiled_list[idx].depth()}")

    return zz_series, raw_data


# --- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="P5: DTC survival on hardware")
    parser.add_argument("--backend",  default="ibm_strasbourg")
    parser.add_argument("--token",    default=None)
    parser.add_argument("--shots",    type=int, default=4096)
    parser.add_argument("--q-fwd",   type=int, default=62)
    parser.add_argument("--q-inv",   type=int, default=81)
    parser.add_argument("--n-max",   type=int, default=48,
                        help="Max steps (default 48 = 4T)")
    parser.add_argument("--stride",  type=int, default=1,
                        help="Step stride (default 1; use 2 to halve circuit count)")
    parser.add_argument("--epsilon", type=float, default=0.0,
                        help="Perturbation strength (0 = clean)")
    parser.add_argument("--seed",    type=int, default=42)
    parser.add_argument("--sim-only", action="store_true")
    args = parser.parse_args()

    step_list = list(range(1, args.n_max + 1, args.stride))

    print("\n== P5: Discrete Time Crystal Survival ====================")
    print(f"Drive period T = {T_CYCLE} steps")
    print(f"DTC signature: subharmonic at 2T = {2*T_CYCLE} steps")
    print(f"Sweep: n = 1..{args.n_max} (stride {args.stride}, {len(step_list)} circuits/run)")
    if args.epsilon > 0:
        print(f"Perturbation: epsilon = {args.epsilon}")

    # Ideal computation
    print("\n-- Ideal <ZZ> series (paired, clean) --")
    ideal_clean = compute_ideal_zz_series(args.n_max, paired=True, epsilon=0.0)
    dtc_clean = analyze_dtc_signal(ideal_clean, T_CYCLE)
    print(f"   Power at 1/T:  {dtc_clean['power_at_T']:.4f}")
    print(f"   Power at 1/2T: {dtc_clean['power_at_2T']:.4f}")
    print(f"   DTC ratio (2T/T): {dtc_clean['dtc_ratio']:.4f}")
    print(f"   ACF lag-T:  {dtc_clean['acf_lag_T']:+.4f}")
    print(f"   ACF lag-2T: {dtc_clean['acf_lag_2T']:+.4f}")

    print("\n-- Ideal <ZZ> series (unpaired control) --")
    ideal_ctrl = compute_ideal_zz_series(args.n_max, paired=False, epsilon=0.0)
    dtc_ctrl = analyze_dtc_signal(ideal_ctrl, T_CYCLE)
    print(f"   Power at 1/T:  {dtc_ctrl['power_at_T']:.4f}")
    print(f"   Power at 1/2T: {dtc_ctrl['power_at_2T']:.4f}")
    print(f"   DTC ratio (2T/T): {dtc_ctrl['dtc_ratio']:.4f}")

    if args.epsilon > 0:
        print(f"\n-- Ideal <ZZ> series (paired, eps={args.epsilon}) --")
        ideal_pert = compute_ideal_zz_series(
            args.n_max, paired=True, epsilon=args.epsilon, seed=args.seed)
        dtc_pert = analyze_dtc_signal(ideal_pert, T_CYCLE)
        print(f"   Power at 1/2T: {dtc_pert['power_at_2T']:.4f}")
        print(f"   DTC ratio: {dtc_pert['dtc_ratio']:.4f}")

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

    all_results = {}

    # Run 1: Paired (merkabit active)
    print("\n=== Run 1: Paired (merkabit DTC) ===")
    zz_paired, raw_paired = run_dtc_sweep(
        backend, args.shots, args.q_fwd, args.q_inv,
        step_list, paired=True, epsilon=args.epsilon, seed=args.seed)
    dtc_hw_paired = analyze_dtc_signal(zz_paired, T_CYCLE)
    all_results["paired"] = {
        "zz_series": zz_paired, "raw": raw_paired, "dtc": dtc_hw_paired}

    # Run 2: Unpaired control
    print("\n=== Run 2: Unpaired control ===")
    zz_ctrl, raw_ctrl = run_dtc_sweep(
        backend, args.shots, args.q_fwd, args.q_inv,
        step_list, paired=False, epsilon=0.0, seed=args.seed)
    dtc_hw_ctrl = analyze_dtc_signal(zz_ctrl, T_CYCLE)
    all_results["unpaired"] = {
        "zz_series": zz_ctrl, "raw": raw_ctrl, "dtc": dtc_hw_ctrl}

    # Run 3: Perturbed (if epsilon > 0)
    if args.epsilon > 0:
        print(f"\n=== Run 3: Paired + perturbation (eps={args.epsilon}) ===")
        zz_pert, raw_pert = run_dtc_sweep(
            backend, args.shots, args.q_fwd, args.q_inv,
            step_list, paired=True, epsilon=args.epsilon, seed=args.seed)
        dtc_hw_pert = analyze_dtc_signal(zz_pert, T_CYCLE)
        all_results["perturbed"] = {
            "zz_series": zz_pert, "raw": raw_pert, "dtc": dtc_hw_pert}

    # Summary
    print(f"\n== P5 DTC Summary =======================================")
    print(f"{'Mode':>12} | {'Pwr 1/T':>8} | {'Pwr 1/2T':>9} | "
          f"{'DTC ratio':>9} | {'ACF-T':>7} | {'ACF-2T':>7}")
    print("-" * 65)
    for mode, data in all_results.items():
        d = data["dtc"]
        print(f"{mode:>12} | {d['power_at_T']:>8.3f} | "
              f"{d['power_at_2T']:>9.3f} | "
              f"{d['dtc_ratio']:>9.3f} | "
              f"{d['acf_lag_T']:>+7.3f} | "
              f"{d['acf_lag_2T']:>+7.3f}")

    dtc_confirmed = dtc_hw_paired["dtc_ratio"] > 1.0
    print(f"\nDTC ratio > 1 (subharmonic dominant): {'YES' if dtc_confirmed else 'NO'}")
    paired_vs_ctrl = (dtc_hw_paired["power_at_2T"] /
                      (dtc_hw_ctrl["power_at_2T"] + 1e-30))
    print(f"Paired/Control 2T power ratio: {paired_vs_ctrl:.2f}x")

    # Save
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "experiment": "P5_dtc_survival",
        "prediction": "DTC subharmonic at 2T survives perturbation",
        "results": {mode: {"dtc_analysis": d["dtc"], "zz_series": d["zz_series"]}
                    for mode, d in all_results.items()},
        "ideal": {
            "clean": {"dtc": dtc_clean, "zz": ideal_clean},
            "control": {"dtc": dtc_ctrl, "zz": ideal_ctrl},
        },
        "backend": backend.name,
        "qubits": {"q_fwd": args.q_fwd, "q_inv": args.q_inv},
        "shots": args.shots,
        "epsilon": args.epsilon,
        "n_max": args.n_max,
        "stride": args.stride,
        "step_list": step_list,
        "timestamp": datetime.now().isoformat(),
    }
    path = RESULTS_DIR / f"p5_dtc_{backend.name}_{ts}.json"
    with open(path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults -> {path}")


if __name__ == "__main__":
    main()
