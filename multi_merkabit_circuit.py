"""
Multi-Merkabit Circuit — 3-Node Triangle and 7-Node Eisenstein Cell
====================================================================
Extends from single-merkabit (intra-node gates) to multi-merkabit
(inter-node syndrome extraction across the Eisenstein lattice).

Single merkabit: 2 qubits, ouroboros cycling, P gate asymmetry.
Multi-merkabit: multiple nodes on the Eisenstein lattice, with
pentachoric closure checked across EDGES BETWEEN merkabits.

This is where the rotation gap lives. Detection depends on whether
the absent gate at node i matches the absent gate at node j —
which only changes with time if the chiralities differ (counter-rotation).

Hierarchy:
  3-merkabit triangle:  6 data + 3 ancilla =  9 qubits (minimal test)
  7-merkabit cell:     14 data + 12 ancilla = 26 qubits (full Eisenstein)

Selina Stenberg with Claude Anthropic, April 2026
"""

import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit import transpile
from collections import defaultdict

from qubit_mapper import EisensteinCell, NUM_GATES, GATES
from ouroboros_circuit import (
    absent_gate, get_gate_angles, find_valid_assignment,
    OUROBOROS_PERIOD
)


# ═══════════════════════════════════════════════════════════════
# 3-MERKABIT TRIANGLE (minimal multi-merkabit test)
# ═══════════════════════════════════════════════════════════════

class TriangleCell:
    """
    Minimal multi-merkabit structure: 3 nodes in a triangle.
    One node from each Z3 sublattice: chirality {0, +1, -1}.
    3 edges connecting all pairs.

    This is the smallest structure that has:
    - All three chirality classes
    - Counter-rotating nodes (chi=+1 vs chi=-1)
    - Inter-node pentachoric detection
    - The rotation gap
    """

    def __init__(self):
        # Three nodes: centre, forward, inverse
        self.num_nodes = 3
        self.coords = [(0, 0), (1, 0), (0, 1)]
        self.chirality = [0, +1, -1]
        self.sublattice = [0, 1, 2]
        self.coordination = [2, 2, 2]

        # Three edges: all pairs
        self.edges = [(0, 1), (0, 2), (1, 2)]
        self.num_edges = 3

        # Neighbors
        self.neighbours = defaultdict(list)
        for i, j in self.edges:
            self.neighbours[i].append(j)
            self.neighbours[j].append(i)

    def summary(self):
        print(f"Triangle cell: {self.num_nodes} merkabits, {self.num_edges} edges")
        for i in range(self.num_nodes):
            chi = self.chirality[i]
            label = {0: 'centre', 1: 'forward', -1: 'inverse'}[chi]
            print(f"  Merkabit {i}: chi={chi:+d} ({label})")
        print(f"  Edges: {self.edges}")
        print(f"  Qubit budget: {self.num_nodes * 2} data + "
              f"{self.num_edges} ancilla = "
              f"{self.num_nodes * 2 + self.num_edges} total")


# ═══════════════════════════════════════════════════════════════
# MULTI-MERKABIT CIRCUIT BUILDER
# ═══════════════════════════════════════════════════════════════

def build_multi_merkabit_circuit(cell, base_assignment, tau=5,
                                  inject_error=None, shots_label=None):
    """
    Build the full multi-merkabit circuit.

    Each merkabit node i has:
      - q_u[i]: forward spinor qubit (index 2*i)
      - q_v[i]: inverse spinor qubit (index 2*i + 1)

    Each edge (i,j) has:
      - ancilla[e]: syndrome qubit (index 2*num_nodes + e)

    Per ouroboros step k:
      1. Apply gate layer (all nodes in parallel):
         P(+p, -p), Rz(rz, rz), Rx(rx, rx) per node
      2. Syndrome extraction (inter-node):
         For each edge (i,j): CNOT(q_u[i], anc) then CNOT(q_u[j], anc)
         Measure ancilla -> classical bit
         Reset ancilla

    Detection: ancilla fires if absent_i(t) == absent_j(t),
    which means the edge fails pentachoric closure.
    """
    n_nodes = cell.num_nodes
    n_edges = cell.num_edges
    n_data = n_nodes * 2
    n_ancilla = n_edges
    n_qubits = n_data + n_ancilla
    n_classical = tau * n_edges

    # Qubit assignment
    node_qu = {i: 2 * i for i in range(n_nodes)}       # forward spinor
    node_qv = {i: 2 * i + 1 for i in range(n_nodes)}   # inverse spinor
    edge_anc = {e: n_data + idx for idx, e in enumerate(cell.edges)}

    qr = QuantumRegister(n_qubits, 'q')
    cr = ClassicalRegister(n_classical, 'c')
    qc = QuantumCircuit(qr, cr)

    # ── Initialize dual-spinor state ──
    # Each merkabit starts in |0>|0> (both spinors in ground state)
    # The P gate will create the asymmetric phase evolution
    # For a more physical initialization, prepare a superposition:
    for i in range(n_nodes):
        # Put forward spinor in |+> = H|0>
        qc.h(node_qu[i])
        # Inverse spinor stays in |0> initially
        # The P gate asymmetry will differentiate them over time

    qc.barrier()

    # ── Optional error injection ──
    if inject_error is not None:
        err_node, err_type = inject_error
        qu = node_qu[err_node]
        qv = node_qv[err_node]

        if err_type == 'X':
            # Bit-flip on forward spinor
            qc.x(qu)
        elif err_type == 'Z':
            # Phase-flip on forward spinor
            qc.z(qu)
        elif err_type == 'phase':
            # Small coherent rotation (more physical)
            qc.rx(0.3, qu)
        elif err_type == 'asymmetric':
            # Break the P-gate symmetry (destroy standing wave)
            qc.rz(np.pi / 4, qu)
            qc.rz(np.pi / 4, qv)  # Same sign = symmetric = NOT a merkabit
        qc.barrier()

    # ── Ouroboros steps with inter-node syndrome extraction ──
    for t in range(tau):

        # Gate layer: apply ouroboros step to each merkabit node
        for i in range(n_nodes):
            chi = cell.chirality[i]
            base = base_assignment[i]
            abs_g = absent_gate(base, chi, t)
            p_ang, rz_ang, rx_ang = get_gate_angles(t, abs_g)

            qu = node_qu[i]
            qv = node_qv[i]

            # P gate: ASYMMETRIC (the merkabit signature)
            qc.rz(+p_ang, qu)   # Forward: +phi
            qc.rz(-p_ang, qv)   # Inverse: -phi

            # Rz gate: symmetric
            qc.rz(rz_ang, qu)
            qc.rz(rz_ang, qv)

            # Rx gate: symmetric
            qc.rx(rx_ang, qu)
            qc.rx(rx_ang, qv)

        qc.barrier()

        # Syndrome extraction: INTER-NODE parity checks
        # For each edge (i,j): check if the two merkabits
        # have compatible absent gates (pentachoric closure)
        for e_idx, (i, j) in enumerate(cell.edges):
            anc = edge_anc[(i, j)]

            # CNOT from forward spinor of node i to ancilla
            qc.cx(node_qu[i], anc)
            # CNOT from forward spinor of node j to ancilla
            qc.cx(node_qu[j], anc)

        qc.barrier()

        # Measure all ancillas
        for e_idx, (i, j) in enumerate(cell.edges):
            anc = edge_anc[(i, j)]
            bit_idx = t * n_edges + e_idx
            qc.measure(anc, cr[bit_idx])

        # Reset ancillas for next round (except last round)
        if t < tau - 1:
            for (i, j) in cell.edges:
                qc.reset(edge_anc[(i, j)])
            qc.barrier()

    return qc, {
        'node_qu': node_qu,
        'node_qv': node_qv,
        'edge_anc': edge_anc,
        'n_qubits': n_qubits,
        'n_classical': n_classical,
    }


# ═══════════════════════════════════════════════════════════════
# DETECTION ANALYSIS
# ═══════════════════════════════════════════════════════════════

def analyze_multi_results(counts, cell, tau):
    """Analyze syndrome measurements from multi-merkabit circuit."""
    total_shots = sum(counts.values())
    n_edges = cell.num_edges

    syndrome_weights = []
    per_round_weights = [[] for _ in range(tau)]
    per_edge_fires = [0] * n_edges
    any_detection = 0

    for bitstring, count in counts.items():
        bits = bitstring[::-1]  # Qiskit reverses
        total_weight = bits.count('1')
        syndrome_weights.extend([total_weight] * count)

        if total_weight > 0:
            any_detection += count

        # Per-round breakdown
        for t in range(tau):
            round_bits = bits[t * n_edges: (t + 1) * n_edges]
            round_weight = round_bits.count('1')
            per_round_weights[t].extend([round_weight] * count)

            # Per-edge fires
            for e_idx in range(n_edges):
                if t * n_edges + e_idx < len(bits) and bits[t * n_edges + e_idx] == '1':
                    per_edge_fires[e_idx] += count

    syndrome_weights = np.array(syndrome_weights, dtype=float)
    mean_w = np.mean(syndrome_weights)
    var_w = np.var(syndrome_weights, ddof=1)
    fano = var_w / mean_w if mean_w > 0 else 0

    # Per-round Fano
    per_round_fano = []
    for t in range(tau):
        rw = np.array(per_round_weights[t], dtype=float)
        rm = np.mean(rw)
        rv = np.var(rw, ddof=1)
        rf = rv / rm if rm > 0 else 0
        per_round_fano.append(float(rf))

    # Per-edge fire rates
    edge_fire_rates = [per_edge_fires[e] / (total_shots * tau)
                       for e in range(n_edges)]

    # Edge chirality classification
    edge_chi_diff = []
    for (i, j) in cell.edges:
        chi_i = cell.chirality[i]
        chi_j = cell.chirality[j]
        diff = abs(chi_i - chi_j)
        edge_chi_diff.append(diff)

    return {
        'total_shots': total_shots,
        'tau': tau,
        'detection_rate': any_detection / total_shots,
        'mean_syndrome_weight': float(mean_w),
        'var_syndrome_weight': float(var_w),
        'fano_factor': float(fano),
        'sub_poissonian': fano < 1.0,
        'per_round_fano': per_round_fano,
        'edge_fire_rates': edge_fire_rates,
        'edge_chi_diff': edge_chi_diff,
    }


# ═══════════════════════════════════════════════════════════════
# ROTATION GAP TEST
# ═══════════════════════════════════════════════════════════════

def run_rotation_gap_test(cell, shots=8192, backend=None):
    """
    The core multi-merkabit test:
    Compare detection at tau=1 (B31 static) vs tau=5 (T75 dynamic).

    The rotation gap should appear on edges between nodes with
    different chirality — those are the counter-rotating pairs.
    """
    if backend is None:
        from qiskit_aer import AerSimulator
        backend = AerSimulator()

    assignment = find_valid_assignment(cell, seed=42)
    print(f"Base assignment: {[GATES[a] for a in assignment]}")

    results = {}

    for tau in [1, 5, 12]:
        print(f"\n--- tau = {tau} ---")

        # No-error baseline
        qc, meta = build_multi_merkabit_circuit(
            cell, assignment, tau=tau)
        qc_t = transpile(qc, backend, optimization_level=1)
        print(f"  Circuit: {qc_t.depth()} depth, "
              f"{qc_t.count_ops().get('cx', 0)} CX gates, "
              f"{qc_t.num_qubits} qubits")

        job = backend.run(qc_t, shots=shots)
        counts = job.result().get_counts()
        result = analyze_multi_results(counts, cell, tau)

        print(f"  Detection rate: {result['detection_rate']:.3f}")
        print(f"  Fano factor: {result['fano_factor']:.4f} "
              f"({'sub-Poissonian' if result['sub_poissonian'] else 'super-Poissonian'})")
        print(f"  Per-round Fano: {[f'{f:.4f}' for f in result['per_round_fano']]}")
        print(f"  Edge fire rates: {[f'{r:.3f}' for r in result['edge_fire_rates']]}")

        # Per-edge breakdown by chirality difference
        for e_idx, (i, j) in enumerate(cell.edges):
            chi_i = cell.chirality[i]
            chi_j = cell.chirality[j]
            diff = abs(chi_i - chi_j)
            rate = result['edge_fire_rates'][e_idx]
            label = 'counter-rotating' if diff == 2 else 'single-step'
            print(f"    Edge ({i},{j}): chi=({chi_i:+d},{chi_j:+d}), "
                  f"diff={diff}, fire_rate={rate:.3f} [{label}]")

        # Error injection sweep
        error_types = ['X', 'Z', 'phase', 'asymmetric']
        for err_type in error_types:
            for node in range(cell.num_nodes):
                qc_err, _ = build_multi_merkabit_circuit(
                    cell, assignment, tau=tau,
                    inject_error=(node, err_type))
                qc_err_t = transpile(qc_err, backend, optimization_level=1)
                job_err = backend.run(qc_err_t, shots=shots)
                counts_err = job_err.result().get_counts()
                res_err = analyze_multi_results(counts_err, cell, tau)
                print(f"  Error {err_type} @ node {node} (chi={cell.chirality[node]:+d}): "
                      f"det={res_err['detection_rate']:.3f}, "
                      f"Fano={res_err['fano_factor']:.4f}")

        results[f'tau_{tau}'] = result

    # Rotation gap
    if 'tau_1' in results and 'tau_5' in results:
        gap = results['tau_5']['detection_rate'] - results['tau_1']['detection_rate']
        print(f"\n{'='*60}")
        print(f"ROTATION GAP: {gap*100:.1f} pp")
        print(f"  tau=1: det={results['tau_1']['detection_rate']:.3f}, "
              f"Fano={results['tau_1']['fano_factor']:.4f}")
        print(f"  tau=5: det={results['tau_5']['detection_rate']:.3f}, "
              f"Fano={results['tau_5']['fano_factor']:.4f}")
        if 'tau_12' in results:
            print(f"  tau=12: det={results['tau_12']['detection_rate']:.3f}, "
                  f"Fano={results['tau_12']['fano_factor']:.4f}")

    return results


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import json, argparse

    parser = argparse.ArgumentParser(
        description='Multi-Merkabit Circuit Test')
    parser.add_argument('--cell', choices=['triangle', 'full'],
                        default='triangle')
    parser.add_argument('--shots', type=int, default=8192)
    parser.add_argument('--output', default='outputs/multi_merkabit_results.json')
    args = parser.parse_args()

    print("=" * 70)
    print("MULTI-MERKABIT EXPERIMENT")
    print("=" * 70)

    if args.cell == 'triangle':
        cell = TriangleCell()
        print("\n3-MERKABIT TRIANGLE (minimal multi-merkabit test)")
    else:
        cell = EisensteinCell(radius=1)
        print("\n7-MERKABIT EISENSTEIN CELL (full pentachoric)")

    cell.summary()
    print()

    results = run_rotation_gap_test(cell, shots=args.shots)

    # Save
    from pathlib import Path
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {output_path}")
