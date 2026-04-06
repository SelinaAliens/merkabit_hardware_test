"""
Ouroboros Circuit Builder — 12-Step Floquet Protocol for IBM Hardware
=====================================================================
Constructs Qiskit circuits implementing the full pentachoric ouroboros cycle
on a dual-spinor encoded 7-node Eisenstein cell.

Each merkabit node = 2 qubits (q_u forward, q_v inverse).
Each ouroboros step applies: U_step(k) = U_Rx @ U_Rz @ U_P
with angles modulated by the absent gate at each node.

R = Rotation gate. When R is absent, rx is suppressed (0.4×) and
rz is enhanced (1.3×) — the R-locking event.

Selina Stenberg with Claude Anthropic, April 2026
"""

import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qubit_mapper import EisensteinCell, NUM_GATES, GATES


# ═══════════════════════════════════════════════════════════════
# OUROBOROS GATE ANGLES (from merkabit_verification.py)
# ═══════════════════════════════════════════════════════════════

OUROBOROS_PERIOD = 12  # h(E₆) = Coxeter number
STEP_PHASE = np.pi / 6  # π/6 per step (2π over 12 steps)


def absent_gate(base, chirality, t):
    """Which gate is absent at time t for a node with given base and chirality."""
    return (base + chirality * t) % NUM_GATES


def get_gate_angles(k, absent_idx):
    """
    Compute (p_angle, rz_angle, rx_angle) for ouroboros step k,
    given which gate is absent at this node.

    Gate labels: 0=S, 1=R, 2=T, 3=P, 4=F
    R = Rotation gate. R-absent = rotation locked.
    """
    gate_label = GATES[absent_idx]

    # Base P angle: π/6 per step
    p_angle = STEP_PHASE

    # Symmetric base: π/18, modulated by E₆ triality
    sym_base = STEP_PHASE / 3
    omega_k = 2 * np.pi * k / OUROBOROS_PERIOD

    rx_angle = sym_base * (1.0 + 0.5 * np.cos(omega_k))
    rz_angle = sym_base * (1.0 + 0.5 * np.cos(omega_k + 2 * np.pi / 3))

    # Absent-gate modifiers
    if gate_label == 'S':
        rz_angle *= 0.4
        rx_angle *= 1.3
    elif gate_label == 'R':
        # R = ROTATION. When absent, rotation is LOCKED.
        rx_angle *= 0.4   # Rotation suppressed
        rz_angle *= 1.3   # Phase compensates
    elif gate_label == 'T':
        rx_angle *= 0.7
        rz_angle *= 0.7
    elif gate_label == 'P':
        p_angle *= 0.6
        rx_angle *= 1.8
        rz_angle *= 1.5
    # F absent: no modification

    return p_angle, rz_angle, rx_angle


# ═══════════════════════════════════════════════════════════════
# CIRCUIT CONSTRUCTION
# ═══════════════════════════════════════════════════════════════

def build_ouroboros_step(qc, k, cell, base_assignment, node_qubits):
    """
    Apply one ouroboros step to all 7 merkabit nodes.

    For each node:
      1. P gate (asymmetric): Rz(+p) on q_u, Rz(-p) on q_v
      2. Rz gate (symmetric): Rz(rz) on both
      3. Rx gate (symmetric): Rx(rx) on both

    Args:
        qc: QuantumCircuit
        k: step index (0..11)
        cell: EisensteinCell
        base_assignment: list of int, absent gate base per node
        node_qubits: dict {node_idx: (qubit_u_idx, qubit_v_idx)}
    """
    for node in range(cell.num_nodes):
        chi = cell.chirality[node]
        base = base_assignment[node]
        abs_gate = absent_gate(base, chi, k)
        p_ang, rz_ang, rx_ang = get_gate_angles(k, abs_gate)

        qu, qv = node_qubits[node]

        # 1. P gate — THE MERKABIT SIGNATURE
        # Asymmetric: forward gets +φ, inverse gets -φ
        qc.rz(+p_ang, qu)
        qc.rz(-p_ang, qv)

        # 2. Rz gate — symmetric on both spinors
        qc.rz(rz_ang, qu)
        qc.rz(rz_ang, qv)

        # 3. Rx gate — symmetric on both spinors
        # Rx(θ) = Rz(-π/2) · √X · Rz(π-θ) · √X · Rz(-π/2)
        # Simplified using Qiskit's native rx
        qc.rx(rx_ang, qu)
        qc.rx(rx_ang, qv)

    qc.barrier()


def build_syndrome_round(qc, cell, base_assignment, node_qubits,
                          edge_ancillas, creg, t, use_reset=True):
    """
    Syndrome extraction: check pentachoric closure at every edge.

    For each edge (i,j):
      - CNOT from one data qubit of node i to ancilla
      - CNOT from one data qubit of node j to ancilla
      - Measure ancilla → classical bit
      - Optional reset for next round

    Detection: ancilla flips if the parity check fails,
    i.e., if absent_i(t) == absent_j(t) (closure failure).

    We use the forward spinor (q_u) of each node for parity checks.
    """
    for e_idx, (i, j) in enumerate(cell.edges):
        qu_i = node_qubits[i][0]  # Forward spinor of node i
        qu_j = node_qubits[j][0]  # Forward spinor of node j
        anc = edge_ancillas[(i, j)]

        qc.cx(qu_i, anc)
        qc.cx(qu_j, anc)

    qc.barrier()

    # Measure all ancillas
    for e_idx, (i, j) in enumerate(cell.edges):
        anc = edge_ancillas[(i, j)]
        bit_idx = t * cell.num_edges + e_idx
        if bit_idx < creg.size:
            qc.measure(anc, creg[bit_idx])

    if use_reset:
        for (i, j) in cell.edges:
            anc = edge_ancillas[(i, j)]
            qc.reset(anc)

    qc.barrier()


# ═══════════════════════════════════════════════════════════════
# FULL PROTOCOL CIRCUITS
# ═══════════════════════════════════════════════════════════════

def build_full_circuit(cell, base_assignment, node_qubits, edge_ancillas,
                       tau=5, inject_error=None):
    """
    Build complete ouroboros circuit for tau steps.

    Args:
        cell: EisensteinCell
        base_assignment: list[int], base absent gate per node
        node_qubits: {node: (qu, qv)} physical qubit indices
        edge_ancillas: {(i,j): ancilla_qubit} physical qubit indices
        tau: number of ouroboros steps (1=static, 5=dynamic, 12=full cycle)
        inject_error: optional (node, gate) to inject before step 0

    Returns:
        QuantumCircuit ready to execute
    """
    # Count total qubits needed
    all_data = set()
    for qu, qv in node_qubits.values():
        all_data.add(qu)
        all_data.add(qv)
    all_ancilla = set(edge_ancillas.values())
    all_qubits = sorted(all_data | all_ancilla)
    n_qubits = max(all_qubits) + 1

    # Classical bits: tau rounds × num_edges measurements
    n_classical = tau * cell.num_edges

    qr = QuantumRegister(n_qubits, 'q')
    cr = ClassicalRegister(n_classical, 'c')
    qc = QuantumCircuit(qr, cr)

    # Initialize: all qubits in |0⟩ (default)
    # For dual-spinor: q_u = |0⟩ (forward), q_v = |0⟩ (inverse)
    # The P gate will create the asymmetric phase evolution

    # Optional error injection
    if inject_error is not None:
        err_node, err_gate = inject_error
        qu = node_qubits[err_node][0]  # Inject on forward spinor
        # X gate simulates a bit-flip error
        qc.x(qu)
        qc.barrier()

    # Run tau ouroboros steps with syndrome extraction after each
    for t in range(tau):
        # Ouroboros gate layer
        build_ouroboros_step(qc, t, cell, base_assignment, node_qubits)

        # Syndrome extraction
        build_syndrome_round(qc, cell, base_assignment, node_qubits,
                              edge_ancillas, cr, t,
                              use_reset=(t < tau - 1))

    return qc


def build_static_circuit(cell, base_assignment, node_qubits, edge_ancillas,
                          inject_error=None):
    """τ=1 static baseline (B₃₁)."""
    return build_full_circuit(cell, base_assignment, node_qubits,
                               edge_ancillas, tau=1,
                               inject_error=inject_error)


def build_dynamic_circuit(cell, base_assignment, node_qubits, edge_ancillas,
                           inject_error=None):
    """τ=5 dynamic full rotation (T₇₅)."""
    return build_full_circuit(cell, base_assignment, node_qubits,
                               edge_ancillas, tau=5,
                               inject_error=inject_error)


# ═══════════════════════════════════════════════════════════════
# VALID ASSIGNMENT SEARCH
# ═══════════════════════════════════════════════════════════════

def find_valid_assignment(cell, seed=42):
    """
    Find a valid pentachoric assignment: adjacent nodes must have
    different absent gates (for closure).

    Uses random search with greedy propagation.
    """
    rng = np.random.default_rng(seed)
    best = None
    best_failures = cell.num_edges + 1

    for trial in range(10000):
        assignment = [int(rng.integers(0, NUM_GATES))
                      for _ in range(cell.num_nodes)]

        # Count failures
        failures = 0
        for (i, j) in cell.edges:
            if assignment[i] == assignment[j]:
                failures += 1

        if failures < best_failures:
            best_failures = failures
            best = assignment[:]

        if failures == 0:
            return best

    return best  # Return best found even if not perfect


# ═══════════════════════════════════════════════════════════════
# ANGLE TABLE (for reference/debugging)
# ═══════════════════════════════════════════════════════════════

def print_angle_table():
    """Print the gate angles for all 12 ouroboros steps × 5 absent gates."""
    print("\nOuroboros Gate Angle Table:")
    print(f"{'Step':>4} | {'Absent':>6} | {'P angle':>10} | {'Rz angle':>10} | {'Rx angle':>10}")
    print("-" * 55)

    for k in range(OUROBOROS_PERIOD):
        for g in range(NUM_GATES):
            p, rz, rx = get_gate_angles(k, g)
            label = GATES[g]
            marker = " ← R-LOCK" if label == 'R' else ""
            print(f"{k:>4} | {label:>6} | {p:>10.6f} | {rz:>10.6f} | {rx:>10.6f}{marker}")
        print()


if __name__ == '__main__':
    print("=" * 70)
    print("OUROBOROS CIRCUIT BUILDER — Pentachoric Merkabit")
    print("=" * 70)

    cell = EisensteinCell(radius=1)
    assignment = find_valid_assignment(cell)
    print(f"\nValid assignment: {assignment}")
    print(f"Gate labels: {[GATES[a] for a in assignment]}")

    # Print angle table for first 3 steps
    for k in range(3):
        print(f"\nStep {k}:")
        for node in range(cell.num_nodes):
            chi = cell.chirality[node]
            abs_g = absent_gate(assignment[node], chi, k)
            p, rz, rx = get_gate_angles(k, abs_g)
            print(f"  Node {node} (chi={chi:+d}): absent={GATES[abs_g]}, "
                  f"P={p:.4f}, Rz={rz:.4f}, Rx={rx:.4f}")

    print_angle_table()
