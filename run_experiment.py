"""
Pentachoric Merkabit Experiment — Main Entry Point
====================================================
Runs the full ouroboros protocol on classical simulator or IBM hardware.

Usage:
  python run_experiment.py --mode classical --tau 5 --shots 8192
  python run_experiment.py --mode hardware --backend ibm_strasbourg --tau 5

Measures:
  - Detection rate at τ=1 (B₃₁ static) and τ=5 (T₇₅ dynamic)
  - Rotation gap: Δ = detection(τ=5) − detection(τ=1)
  - Per-chirality breakdown
  - Fano factor of syndrome counts
  - Full error injection sweep (7 nodes × 4 error gates = 28 configs)

Selina Stenberg with Claude Anthropic, April 2026
"""

import argparse
import json
import numpy as np
from pathlib import Path
from collections import defaultdict

from qubit_mapper import EisensteinCell, NUM_GATES, GATES
from ouroboros_circuit import (
    build_full_circuit, find_valid_assignment, absent_gate
)


# ═══════════════════════════════════════════════════════════════
# SIMPLE QUBIT ASSIGNMENT (for simulation mode)
# ═══════════════════════════════════════════════════════════════

def simple_qubit_assignment(cell):
    """
    Simple sequential qubit assignment for simulator.
    Node i: q_u = 2*i, q_v = 2*i + 1
    Edge ancillas start after data qubits.
    """
    node_qubits = {}
    for i in range(cell.num_nodes):
        node_qubits[i] = (2 * i, 2 * i + 1)

    edge_ancillas = {}
    ancilla_start = 2 * cell.num_nodes
    for e_idx, (i, j) in enumerate(cell.edges):
        edge_ancillas[(i, j)] = ancilla_start + e_idx

    return node_qubits, edge_ancillas


# ═══════════════════════════════════════════════════════════════
# DETECTION ANALYSIS
# ═══════════════════════════════════════════════════════════════

def analyze_detection(counts, cell, tau, inject_error=None):
    """
    Analyze syndrome measurement results.

    counts: dict {bitstring: count} from Qiskit execution
    Each bitstring has tau * num_edges bits.

    Returns detection statistics.
    """
    total_shots = sum(counts.values())
    n_edges = cell.num_edges

    # Per-shot syndrome analysis
    syndrome_weights = []  # Total syndrome activations per shot
    any_detection = 0  # Shots with at least one syndrome activation

    for bitstring, count in counts.items():
        # Qiskit bitstrings are reversed
        bits = bitstring[::-1]
        weight = bits.count('1')
        syndrome_weights.extend([weight] * count)
        if weight > 0:
            any_detection += count

    syndrome_weights = np.array(syndrome_weights, dtype=float)

    # Fano factor
    mean_w = np.mean(syndrome_weights)
    var_w = np.var(syndrome_weights, ddof=1)
    fano = var_w / mean_w if mean_w > 0 else 0

    # Detection rate (fraction of shots with any syndrome activation)
    detection_rate = any_detection / total_shots

    # Per-round syndrome counts
    round_detections = []
    for t in range(tau):
        round_count = 0
        for bitstring, count in counts.items():
            bits = bitstring[::-1]
            round_bits = bits[t * n_edges: (t + 1) * n_edges]
            if '1' in round_bits:
                round_count += count
        round_detections.append(round_count / total_shots)

    return {
        'total_shots': total_shots,
        'detection_rate': detection_rate,
        'mean_syndrome_weight': float(mean_w),
        'var_syndrome_weight': float(var_w),
        'fano_factor': float(fano),
        'sub_poissonian': fano < 1.0,
        'per_round_detection': round_detections,
        'inject_error': inject_error,
    }


# ═══════════════════════════════════════════════════════════════
# ERROR INJECTION SWEEP
# ═══════════════════════════════════════════════════════════════

def run_error_sweep(cell, base_assignment, node_qubits, edge_ancillas,
                    tau, shots, backend=None):
    """
    Inject every possible single-gate error and measure detection.
    7 nodes × 4 error gates per node (excluding the absent gate) = 28 configs.
    Plus one no-error baseline.
    """
    from qiskit import transpile

    results = []

    # Get simulator or hardware backend
    if backend is None:
        from qiskit_aer import AerSimulator
        backend = AerSimulator()

    # No-error baseline
    print("  Running baseline (no error)...")
    qc = build_full_circuit(cell, base_assignment, node_qubits,
                             edge_ancillas, tau=tau)
    qc_t = transpile(qc, backend, optimization_level=1)
    job = backend.run(qc_t, shots=shots)
    counts = job.result().get_counts()
    baseline = analyze_detection(counts, cell, tau)
    baseline['label'] = 'baseline'
    results.append(baseline)
    print(f"    Baseline: detection={baseline['detection_rate']:.3f}, "
          f"Fano={baseline['fano_factor']:.4f}")

    # Error injection sweep
    for node in range(cell.num_nodes):
        for gate in range(NUM_GATES):
            # Skip if this gate is the absent gate (no error to inject)
            if gate == base_assignment[node]:
                continue

            print(f"  Injecting error: node={node} (chi={cell.chirality[node]:+d}), "
                  f"gate={GATES[gate]}...")

            qc = build_full_circuit(cell, base_assignment, node_qubits,
                                     edge_ancillas, tau=tau,
                                     inject_error=(node, gate))
            qc_t = transpile(qc, backend, optimization_level=1)
            job = backend.run(qc_t, shots=shots)
            counts = job.result().get_counts()

            result = analyze_detection(counts, cell, tau,
                                        inject_error=(node, gate))
            result['label'] = f'node{node}_gate{GATES[gate]}'
            result['node'] = node
            result['chirality'] = cell.chirality[node]
            result['error_gate'] = gate
            results.append(result)

            detected = result['detection_rate'] > baseline['detection_rate'] + 0.01
            print(f"    Detection={result['detection_rate']:.3f}, "
                  f"Fano={result['fano_factor']:.4f}, "
                  f"{'DETECTED' if detected else 'MISSED'}")

    return results


# ═══════════════════════════════════════════════════════════════
# ROTATION GAP MEASUREMENT
# ═══════════════════════════════════════════════════════════════

def measure_rotation_gap(cell, base_assignment, node_qubits, edge_ancillas,
                          shots, backend=None):
    """
    The central measurement: detection at τ=1 vs τ=5.
    """
    print("\n" + "=" * 70)
    print("ROTATION GAP MEASUREMENT")
    print("=" * 70)

    # τ=1 (B₃₁ static baseline)
    print("\n--- τ=1 (B₃₁ Static) ---")
    results_t1 = run_error_sweep(cell, base_assignment, node_qubits,
                                  edge_ancillas, tau=1, shots=shots,
                                  backend=backend)

    # τ=5 (T₇₅ dynamic full rotation)
    print("\n--- τ=5 (T₇₅ Dynamic) ---")
    results_t5 = run_error_sweep(cell, base_assignment, node_qubits,
                                  edge_ancillas, tau=5, shots=shots,
                                  backend=backend)

    # Compute rotation gap
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    # Overall detection rates (excluding baseline)
    det_t1 = [r['detection_rate'] for r in results_t1 if r['label'] != 'baseline']
    det_t5 = [r['detection_rate'] for r in results_t5 if r['label'] != 'baseline']

    mean_t1 = np.mean(det_t1)
    mean_t5 = np.mean(det_t5)
    gap = mean_t5 - mean_t1

    print(f"\nOverall detection rate:")
    print(f"  τ=1 (B₃₁): {mean_t1:.1%}")
    print(f"  τ=5 (T₇₅): {mean_t5:.1%}")
    print(f"  Rotation gap: {gap:.1%} ({gap*100:.1f} pp)")

    # Per-chirality breakdown
    for chi_val, chi_name in [(0, 'Centre'), (+1, 'Sub1 (+1)'), (-1, 'Sub2 (-1)')]:
        det1_chi = [r['detection_rate'] for r in results_t1
                    if r.get('chirality') == chi_val]
        det5_chi = [r['detection_rate'] for r in results_t5
                    if r.get('chirality') == chi_val]
        if det1_chi and det5_chi:
            m1 = np.mean(det1_chi)
            m5 = np.mean(det5_chi)
            print(f"  {chi_name}: τ=1={m1:.1%}, τ=5={m5:.1%}, gap={m5-m1:.1%}")

    # Fano factors
    fano_t1 = [r['fano_factor'] for r in results_t1]
    fano_t5 = [r['fano_factor'] for r in results_t5]
    print(f"\nFano factor:")
    print(f"  τ=1: {np.mean(fano_t1):.4f} ± {np.std(fano_t1):.4f}")
    print(f"  τ=5: {np.mean(fano_t5):.4f} ± {np.std(fano_t5):.4f}")

    return {
        'tau1': results_t1,
        'tau5': results_t5,
        'mean_detection_t1': float(mean_t1),
        'mean_detection_t5': float(mean_t5),
        'rotation_gap_pp': float(gap * 100),
        'fano_t1_mean': float(np.mean(fano_t1)),
        'fano_t5_mean': float(np.mean(fano_t5)),
    }


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='Pentachoric Merkabit Experiment')
    parser.add_argument('--mode', choices=['classical', 'hardware'],
                        default='classical')
    parser.add_argument('--backend', default='ibm_strasbourg',
                        help='IBM backend name (hardware mode)')
    parser.add_argument('--tau', type=int, default=5,
                        help='Detection window depth (1, 5, or 12)')
    parser.add_argument('--shots', type=int, default=8192)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--full-gap', action='store_true',
                        help='Run full rotation gap measurement (τ=1 AND τ=5)')
    parser.add_argument('--output', default='outputs/merkabit_results.json')
    args = parser.parse_args()

    print("=" * 70)
    print("PENTACHORIC MERKABIT EXPERIMENT")
    print(f"Mode: {args.mode} | tau={args.tau} | Shots={args.shots}")
    print("=" * 70)

    # Build cell
    cell = EisensteinCell(radius=1)
    cell.summary()

    # Find valid assignment
    assignment = find_valid_assignment(cell, seed=args.seed)
    print(f"\nBase assignment: {[GATES[a] for a in assignment]}")

    # Qubit mapping
    node_qubits, edge_ancillas = simple_qubit_assignment(cell)
    print(f"Node qubits: {node_qubits}")
    print(f"Edge ancillas: {edge_ancillas}")

    # Backend
    backend = None
    if args.mode == 'classical':
        from qiskit_aer import AerSimulator
        backend = AerSimulator()
        print("\nUsing AerSimulator (classical)")
    else:
        from qiskit_ibm_runtime import QiskitRuntimeService
        service = QiskitRuntimeService()
        backend = service.backend(args.backend)
        print(f"\nUsing IBM hardware: {args.backend}")

    # Run experiment
    if args.full_gap:
        results = measure_rotation_gap(cell, assignment, node_qubits,
                                        edge_ancillas, args.shots, backend)
    else:
        print(f"\nRunning error sweep at τ={args.tau}...")
        results = run_error_sweep(cell, assignment, node_qubits,
                                   edge_ancillas, tau=args.tau,
                                   shots=args.shots, backend=backend)

    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {output_path}")


if __name__ == '__main__':
    main()
