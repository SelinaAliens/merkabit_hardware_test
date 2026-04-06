#!/usr/bin/env python3
"""
ROTATION GAP ON HARDWARE — The Critical Next Step
===================================================

All pentachoric circuit results so far are from classical simulation.
Hardware execution of the full multi-merkabit protocol is pending.
This script bridges that gap.

The rotation gap = detection_rate(dynamic) - detection_rate(static).

In simulation:
  - 3-merkabit triangle: gap = 5.0 pp (tau=5 vs tau=1)
  - Fano factor: F ~ 0.54 (sub-Poissonian, anti-bunched)

On hardware, the challenge is:
  - Syndrome extraction requires CX gates (inter-node parity checks)
  - Each round: 2 CX per edge = 6 CX for 3 edges
  - tau=5 → 30 CX gates + single-qubit ouroboros layers
  - Decoherence budget: ~100-150 CX before signal is lost

Strategy — staged approach:
  STAGE 1: Triangle (3 nodes, 9 qubits) at tau=1,3,5
    - 6 data + 3 ancilla = 9 qubits
    - Needs: 3 pairs of connected data qubits, 3 ancilla qubits
    - Each ancilla connected to forward spinors of both endpoint nodes
    - Use validated ibm_strasbourg region around qubits 58-81

  STAGE 2: If Stage 1 works, extend to full 7-node (26 qubits)

Qubit layout for triangle on ibm_strasbourg (Eagle r3 heavy-hex):
  Node 0 (chi=0, centre):  q_u=62, q_v=72   ← validated pair from ZPMB
  Node 1 (chi=+1, fwd):    q_u=81, q_v=80
  Node 2 (chi=-1, inv):    q_u=58, q_v=59

  Edge (0,1) ancilla: 71  (connects 62-71 and 81-71? check coupling)
  Edge (0,2) ancilla: 61  (connects 62-61 and 58-61? check coupling)
  Edge (1,2) ancilla: 79  (connects 81-79? and 58-79? check coupling)

  NOTE: The exact ancilla qubits depend on ibm_strasbourg coupling map.
  This script auto-discovers valid placements from the backend.

What we measure:
  1. Syndrome weight distribution → Fano factor (expect sub-Poissonian)
  2. Detection rate vs tau → rotation gap (expect dynamic > static)
  3. Per-edge fire rate vs chirality difference → counter-rotating
     edges should fire more than same-chirality edges
  4. Error injection → paired circuit should detect injected errors
     at higher rate than unpaired control

Authors: Stenberg & Hetland, April 2026
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from collections import defaultdict

import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

RESULTS_DIR = Path(__file__).parent.parent / "outputs" / "rotation_gap"

T_CYCLE    = 12
STEP_PHASE = 2 * np.pi / T_CYCLE
GATES      = ['S', 'R', 'T', 'F', 'P']
NUM_GATES  = 5


def get_gate_angles(k: int, absent_idx: int) -> tuple[float, float, float]:
    """Gate angles for step k with given absent gate index."""
    gate_label = GATES[absent_idx]
    p  = STEP_PHASE
    sym = STEP_PHASE / 3
    w  = 2 * np.pi * k / T_CYCLE
    rx = sym * (1.0 + 0.5 * np.cos(w))
    rz = sym * (1.0 + 0.5 * np.cos(w + 2 * np.pi / 3))
    if gate_label == 'S': rz *= 0.4;  rx *= 1.3
    elif gate_label == 'R': rx *= 0.4; rz *= 1.3
    elif gate_label == 'T': rx *= 0.7; rz *= 0.7
    elif gate_label == 'P': p  *= 0.6; rx *= 1.8; rz *= 1.5
    return p, rz, rx


def absent_gate(base: int, chirality: int, t: int) -> int:
    return (base + chirality * t) % NUM_GATES


# --- Triangle cell definition ------------------------------------------------

class TriangleCell:
    """Minimal 3-node multi-merkabit: centre, forward, inverse."""
    def __init__(self):
        self.num_nodes = 3
        self.chirality = [0, +1, -1]
        self.edges = [(0, 1), (0, 2), (1, 2)]
        self.num_edges = 3
        self.neighbours = defaultdict(list)
        for i, j in self.edges:
            self.neighbours[i].append(j)
            self.neighbours[j].append(i)


def find_valid_assignment(cell, seed=42):
    """Find base absent-gate assignment where adjacent nodes differ."""
    rng = np.random.default_rng(seed)
    for _ in range(10000):
        assignment = [int(rng.integers(0, NUM_GATES))
                      for _ in range(cell.num_nodes)]
        if all(assignment[i] != assignment[j] for i, j in cell.edges):
            return assignment
    # Fallback: manually chosen valid assignment
    return [0, 1, 2]


# --- Qubit mapping discovery --------------------------------------------------

def discover_triangle_layout(backend):
    """
    Discover a valid 9-qubit triangle layout on the backend.

    Needs:
      - 3 data-qubit PAIRS (each pair = directly connected qubits)
      - 3 ancilla qubits, one per edge
      - Each edge ancilla connected to the forward spinor (q_u) of both endpoints

    Returns dict with node_qu, node_qv, edge_anc mappings.
    """
    cmap = backend.coupling_map
    adj = defaultdict(set)
    for q1, q2 in cmap.get_edges():
        adj[q1].add(q2)
        adj[q2].add(q1)

    # Find all directly connected pairs
    pairs = []
    seen = set()
    for q1, q2 in cmap.get_edges():
        key = (min(q1, q2), max(q1, q2))
        if key not in seen:
            pairs.append(key)
            seen.add(key)

    # Try to find 3 pairs where each pair of pairs shares an ancilla neighbor
    best_layout = None
    best_score = -1

    for i in range(len(pairs)):
        qa0, qb0 = pairs[i]
        for j in range(i + 1, len(pairs)):
            qa1, qb1 = pairs[j]
            if {qa1, qb1} & {qa0, qb0}:
                continue  # Overlapping
            for k in range(j + 1, len(pairs)):
                qa2, qb2 = pairs[k]
                if {qa2, qb2} & {qa0, qb0, qa1, qb1}:
                    continue

                # For each pair, q_u = first, q_v = second
                # Try both orientations for each pair
                for orient in range(8):
                    qu = [0, 0, 0]
                    qv = [0, 0, 0]
                    qu[0] = qa0 if (orient & 1) == 0 else qb0
                    qv[0] = qb0 if (orient & 1) == 0 else qa0
                    qu[1] = qa1 if (orient & 2) == 0 else qb1
                    qv[1] = qb1 if (orient & 2) == 0 else qa1
                    qu[2] = qa2 if (orient & 4) == 0 else qb2
                    qv[2] = qb2 if (orient & 4) == 0 else qa2

                    used = {qu[0], qv[0], qu[1], qv[1], qu[2], qv[2]}

                    # Find ancillas for each edge
                    edge_anc = {}
                    valid = True
                    for ei, (ni, nj) in enumerate([(0,1), (0,2), (1,2)]):
                        # Ancilla must connect to qu[ni] AND qu[nj]
                        candidates = (adj[qu[ni]] & adj[qu[nj]]) - used
                        if not candidates:
                            valid = False
                            break
                        anc = min(candidates)  # Deterministic
                        edge_anc[(ni, nj)] = anc
                        used.add(anc)

                    if not valid:
                        continue

                    # Score: prefer qubits near the ZPMB-validated region
                    center = 70  # Near the validated 62/72/81 region
                    score = -sum(abs(q - center) for q in used)

                    if score > best_score:
                        best_score = score
                        best_layout = {
                            "node_qu": {n: qu[n] for n in range(3)},
                            "node_qv": {n: qv[n] for n in range(3)},
                            "edge_anc": edge_anc,
                            "used_qubits": sorted(used),
                        }

    return best_layout


def manual_triangle_layout():
    """
    Fallback: manual layout for ibm_strasbourg.
    Based on the validated ZPMB region (62/72/81).

    heavy-hex neighbors of 62: [72, 61, 63]
    heavy-hex neighbors of 72: [62, 81, 71, 73]
    heavy-hex neighbors of 81: [72, 80, 82]

    Node 0 (centre):  qu=62, qv=63
    Node 1 (fwd):     qu=72, qv=73
    Node 2 (inv):     qu=81, qv=80

    Edge (0,1) anc: needs connect to qu[0]=62 AND qu[1]=72
      → 62-72 direct! No ancilla needed if we use direct CX.
      But for syndrome: ancilla must be separate.
      → Check: what connects to both 62 and 72?

    This may need adaptation based on actual coupling map.
    """
    return {
        "node_qu": {0: 62, 1: 72, 2: 81},
        "node_qv": {0: 63, 1: 73, 2: 80},
        "edge_anc": {(0, 1): 71, (0, 2): 61, (1, 2): 82},
        "note": "Manual fallback — verify against actual coupling map",
    }


# --- Circuit builder ----------------------------------------------------------

def build_triangle_circuit(cell, assignment, layout, tau,
                           paired=True, inject_error=None):
    """
    Build multi-merkabit triangle circuit for hardware.

    Per ouroboros step k:
      1. Intra-node gates: P(+p,-p), Rz, Rx on each merkabit
      2. Inter-node syndrome: CX(qu[i], anc), CX(qu[j], anc), measure anc

    Total CX per round: 2 * num_edges = 6
    Total CX for tau rounds: 6 * tau
    """
    node_qu = layout["node_qu"]
    node_qv = layout["node_qv"]
    edge_anc = layout["edge_anc"]
    all_qubits = sorted(set(
        list(node_qu.values()) + list(node_qv.values()) +
        list(edge_anc.values())
    ))
    n_physical = max(all_qubits) + 1

    n_classical = tau * cell.num_edges
    qr = QuantumRegister(n_physical, 'q')
    cr = ClassicalRegister(n_classical, 'c')
    qc = QuantumCircuit(qr, cr)

    # Initialize forward spinors in |+> (matching simulation protocol)
    for i in range(cell.num_nodes):
        qc.h(node_qu[i])
    qc.barrier()

    # Error injection
    if inject_error is not None:
        err_node, err_type = inject_error
        qu = node_qu[err_node]
        if err_type == 'X':
            qc.x(qu)
        elif err_type == 'Z':
            qc.z(qu)
        elif err_type == 'phase':
            qc.rx(0.3, qu)
        qc.barrier()

    # Ouroboros steps with syndrome extraction
    for t in range(tau):
        # Gate layer: all nodes in parallel
        for i in range(cell.num_nodes):
            chi = cell.chirality[i]
            base = assignment[i]
            abs_g = absent_gate(base, chi, t)
            p_ang, rz_ang, rx_ang = get_gate_angles(t, abs_g)

            qu = node_qu[i]
            qv = node_qv[i]

            if paired:
                qc.rz(rz_ang + p_ang, qu)   # Forward: merged Rz + P
                qc.rz(rz_ang - p_ang, qv)   # Inverse: merged Rz - P
            else:
                qc.rz(rz_ang, qu)
                qc.rz(rz_ang, qv)

            qc.rx(rx_ang, qu)
            qc.rx(rx_ang, qv)

        qc.barrier()

        # Syndrome extraction: CX from forward spinors to edge ancillas
        for e_idx, (i, j) in enumerate(cell.edges):
            anc = edge_anc[(i, j)]
            qc.cx(node_qu[i], anc)
            qc.cx(node_qu[j], anc)

        qc.barrier()

        # Measure ancillas
        for e_idx, (i, j) in enumerate(cell.edges):
            anc = edge_anc[(i, j)]
            bit_idx = t * cell.num_edges + e_idx
            qc.measure(anc, cr[bit_idx])

        # Reset ancillas (except last round)
        if t < tau - 1:
            for (i, j) in cell.edges:
                qc.reset(edge_anc[(i, j)])
            qc.barrier()

    return qc


# --- Analysis -----------------------------------------------------------------

def analyze_syndrome(counts, cell, tau):
    """Analyze syndrome measurements for rotation gap."""
    total_shots = sum(counts.values())
    n_edges = cell.num_edges

    syndrome_weights = []
    per_round_weights = [[] for _ in range(tau)]
    per_edge_fires = [0] * n_edges
    any_detection = 0

    for bitstring, count in counts.items():
        bits = bitstring[::-1]  # Qiskit bit ordering
        total_weight = bits.count('1')
        syndrome_weights.extend([total_weight] * count)
        if total_weight > 0:
            any_detection += count

        for t in range(tau):
            round_bits = bits[t * n_edges: (t + 1) * n_edges]
            round_weight = round_bits.count('1')
            per_round_weights[t].extend([round_weight] * count)
            for e_idx in range(n_edges):
                idx = t * n_edges + e_idx
                if idx < len(bits) and bits[idx] == '1':
                    per_edge_fires[e_idx] += count

    sw = np.array(syndrome_weights, dtype=float)
    mean_w = np.mean(sw)
    var_w = np.var(sw, ddof=1) if len(sw) > 1 else 0
    fano = var_w / mean_w if mean_w > 1e-10 else float('nan')

    per_round_fano = []
    for t in range(tau):
        rw = np.array(per_round_weights[t], dtype=float)
        rm = np.mean(rw)
        rv = np.var(rw, ddof=1) if len(rw) > 1 else 0
        rf = rv / rm if rm > 1e-10 else float('nan')
        per_round_fano.append(float(rf))

    edge_fire_rates = [per_edge_fires[e] / (total_shots * tau)
                       for e in range(n_edges)]

    return {
        "total_shots": total_shots,
        "tau": tau,
        "detection_rate": any_detection / total_shots,
        "mean_syndrome_weight": float(mean_w),
        "var_syndrome_weight": float(var_w),
        "fano_factor": float(fano),
        "sub_poissonian": fano < 1.0,
        "per_round_fano": per_round_fano,
        "edge_fire_rates": edge_fire_rates,
    }


# --- Hardware runner ----------------------------------------------------------

def run_rotation_gap(backend, cell, assignment, layout, shots, tau_list,
                     do_control=True, do_error_inject=False):
    """Run the full rotation gap experiment."""
    results = {}

    for tau in tau_list:
        print(f"\n{'='*60}")
        print(f"  tau = {tau} (paired, no error)")
        print(f"{'='*60}")

        qc = build_triangle_circuit(cell, assignment, layout, tau, paired=True)
        print(f"  Abstract depth: {qc.depth()}")
        print(f"  Gate count: {qc.size()}")

        pm = generate_preset_pass_manager(
            optimization_level=1, backend=backend)
        transpiled = pm.run(qc)
        td = transpiled.depth()
        cx_count = transpiled.count_ops().get('cx', 0) + transpiled.count_ops().get('ecr', 0)
        print(f"  Transpiled depth: {td}   CX/ECR gates: {cx_count}")

        if td > 300:
            print(f"  WARNING: depth {td} > 300 — decoherence likely dominant")

        sampler = Sampler(backend)
        job = sampler.run([transpiled], shots=shots)
        print(f"  Job ID: {job.job_id()}  -- waiting ...")
        result = job.result()
        counts = result[0].data.c.get_counts()

        analysis = analyze_syndrome(counts, cell, tau)
        analysis["transpiled_depth"] = td
        analysis["cx_count"] = cx_count
        analysis["job_id"] = job.job_id()
        analysis["counts_summary"] = dict(sorted(
            counts.items(), key=lambda x: -x[1])[:10])

        print(f"  Detection rate: {analysis['detection_rate']:.4f}")
        print(f"  Fano factor: {analysis['fano_factor']:.4f} "
              f"({'SUB-POISSONIAN' if analysis['sub_poissonian'] else 'super-Poissonian'})")
        print(f"  Per-round Fano: {[f'{f:.3f}' for f in analysis['per_round_fano']]}")
        print(f"  Edge fire rates: {[f'{r:.3f}' for r in analysis['edge_fire_rates']]}")

        # Per-edge chirality analysis
        for e_idx, (i, j) in enumerate(cell.edges):
            chi_i, chi_j = cell.chirality[i], cell.chirality[j]
            diff = abs(chi_i - chi_j)
            rate = analysis["edge_fire_rates"][e_idx]
            label = "counter-rotating" if diff == 2 else "mixed"
            print(f"    Edge ({i},{j}): chi=({chi_i:+d},{chi_j:+d}) "
                  f"diff={diff} rate={rate:.4f} [{label}]")

        results[f"paired_tau{tau}"] = analysis

        # Control: unpaired (no P gate)
        if do_control:
            print(f"\n  --- Control: unpaired, tau={tau} ---")
            qc_ctrl = build_triangle_circuit(
                cell, assignment, layout, tau, paired=False)
            transpiled_ctrl = pm.run(qc_ctrl)
            sampler_ctrl = Sampler(backend)
            job_ctrl = sampler_ctrl.run([transpiled_ctrl], shots=shots)
            print(f"  Job ID: {job_ctrl.job_id()}")
            result_ctrl = job_ctrl.result()
            counts_ctrl = result_ctrl[0].data.c.get_counts()
            analysis_ctrl = analyze_syndrome(counts_ctrl, cell, tau)
            analysis_ctrl["job_id"] = job_ctrl.job_id()
            results[f"unpaired_tau{tau}"] = analysis_ctrl
            print(f"  Control detection: {analysis_ctrl['detection_rate']:.4f}")
            print(f"  Control Fano: {analysis_ctrl['fano_factor']:.4f}")

        # Error injection
        if do_error_inject and tau >= 3:
            for err_type in ['X', 'Z', 'phase']:
                for node in range(cell.num_nodes):
                    qc_err = build_triangle_circuit(
                        cell, assignment, layout, tau, paired=True,
                        inject_error=(node, err_type))
                    transpiled_err = pm.run(qc_err)
                    sampler_err = Sampler(backend)
                    job_err = sampler_err.run([transpiled_err], shots=shots)
                    result_err = job_err.result()
                    counts_err = result_err[0].data.c.get_counts()
                    analysis_err = analyze_syndrome(counts_err, cell, tau)
                    key = f"error_{err_type}_node{node}_tau{tau}"
                    results[key] = {
                        "detection_rate": analysis_err["detection_rate"],
                        "fano_factor": analysis_err["fano_factor"],
                    }
                    print(f"  Error {err_type}@node{node}: "
                          f"det={analysis_err['detection_rate']:.4f} "
                          f"Fano={analysis_err['fano_factor']:.4f}")

    return results


# --- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Rotation Gap: multi-merkabit hardware experiment")
    parser.add_argument("--backend",  default="ibm_strasbourg")
    parser.add_argument("--token",    default=None)
    parser.add_argument("--shots",    type=int, default=8192)
    parser.add_argument("--tau",     nargs='+', type=int, default=[1, 3, 5],
                        help="Ouroboros step counts (default: 1,3,5)")
    parser.add_argument("--no-control", action="store_true",
                        help="Skip unpaired control runs")
    parser.add_argument("--error-inject", action="store_true",
                        help="Run error injection tests")
    parser.add_argument("--manual-layout", action="store_true",
                        help="Use manual qubit layout instead of auto-discovery")
    parser.add_argument("--sim-only", action="store_true")
    args = parser.parse_args()

    cell = TriangleCell()
    assignment = find_valid_assignment(cell)

    print("\n== ROTATION GAP: Multi-Merkabit on Hardware ==============")
    print(f"Cell: 3-merkabit triangle")
    print(f"Chiralities: {cell.chirality}")
    print(f"Base assignment: {[GATES[a] for a in assignment]}")
    print(f"Tau sweep: {args.tau}")
    print(f"Budget: 9 qubits, 6 CX/round, {max(args.tau)*6} CX max")

    # Simulation preview
    if args.sim_only:
        print("\n-- Simulation only --")
        try:
            from qiskit_aer import AerSimulator
            sim_backend = AerSimulator()
            # Use a simple virtual layout for simulation
            sim_layout = {
                "node_qu": {0: 0, 1: 2, 2: 4},
                "node_qv": {0: 1, 1: 3, 2: 5},
                "edge_anc": {(0, 1): 6, (0, 2): 7, (1, 2): 8},
            }
            for tau in args.tau:
                qc = build_triangle_circuit(
                    cell, assignment, sim_layout, tau, paired=True)
                from qiskit import transpile
                qc_t = transpile(qc, sim_backend, optimization_level=1)
                job = sim_backend.run(qc_t, shots=args.shots)
                counts = job.result().get_counts()
                analysis = analyze_syndrome(counts, cell, tau)
                print(f"\n  tau={tau}: det={analysis['detection_rate']:.4f}  "
                      f"Fano={analysis['fano_factor']:.4f}  "
                      f"sub-P={'YES' if analysis['sub_poissonian'] else 'NO'}")
                print(f"    Edge rates: {[f'{r:.3f}' for r in analysis['edge_fire_rates']]}")

            # Rotation gap
            if len(args.tau) >= 2:
                # Compare first and last tau
                print(f"\n  Simulation rotation gap pending (run both tau values)")
        except ImportError:
            print("  qiskit_aer not installed — skip simulation")
        return

    # Hardware
    token = args.token or os.environ.get("IBM_QUANTUM_TOKEN")
    service = QiskitRuntimeService(
        channel="ibm_quantum_platform", token=token
    ) if token else QiskitRuntimeService(channel="ibm_quantum_platform")
    backend = service.backend(args.backend)
    print(f"\nBackend: {backend.name}  ({backend.num_qubits} qubits)")

    # Qubit layout
    if args.manual_layout:
        layout = manual_triangle_layout()
        print(f"Using manual layout: {layout}")
    else:
        print("Auto-discovering triangle layout on coupling map...")
        layout = discover_triangle_layout(backend)
        if layout is None:
            print("Auto-discovery failed. Falling back to manual layout.")
            layout = manual_triangle_layout()
        else:
            print(f"Found layout using qubits: {layout['used_qubits']}")

    print(f"\nLayout:")
    for n in range(3):
        chi = cell.chirality[n]
        print(f"  Node {n} (chi={chi:+d}): qu={layout['node_qu'][n]}, "
              f"qv={layout['node_qv'][n]}")
    for (i, j), anc in layout["edge_anc"].items():
        print(f"  Edge ({i},{j}): ancilla={anc}")

    # Run experiment
    results = run_rotation_gap(
        backend, cell, assignment, layout, args.shots, args.tau,
        do_control=not args.no_control,
        do_error_inject=args.error_inject)

    # Rotation gap summary
    print(f"\n== ROTATION GAP SUMMARY =================================")
    print(f"{'Config':>20} | {'tau':>3} | {'Det Rate':>8} | "
          f"{'Fano':>6} | {'Sub-P':>5}")
    print("-" * 55)
    for key, data in sorted(results.items()):
        if "detection_rate" in data:
            sub_p = "YES" if data.get("sub_poissonian", False) else "NO"
            tau_val = data.get("tau", "?")
            print(f"{key:>20} | {tau_val:>3} | "
                  f"{data['detection_rate']:>8.4f} | "
                  f"{data['fano_factor']:>6.4f} | {sub_p:>5}")

    # Compute rotation gap
    for tau in args.tau:
        paired_key = f"paired_tau{tau}"
        unpaired_key = f"unpaired_tau{tau}"
        if paired_key in results and unpaired_key in results:
            gap = (results[paired_key]["detection_rate"] -
                   results[unpaired_key]["detection_rate"])
            print(f"\nRotation gap at tau={tau}: {gap*100:+.2f} pp")
            print(f"  Paired: {results[paired_key]['detection_rate']:.4f}")
            print(f"  Unpaired: {results[unpaired_key]['detection_rate']:.4f}")

    # Static vs dynamic gap
    if "paired_tau1" in results and len(args.tau) > 1:
        max_tau = max(args.tau)
        max_key = f"paired_tau{max_tau}"
        if max_key in results:
            dynamic_gap = (results[max_key]["detection_rate"] -
                           results["paired_tau1"]["detection_rate"])
            print(f"\nDynamic rotation gap (tau={max_tau} vs tau=1): "
                  f"{dynamic_gap*100:+.2f} pp")
            print(f"  Simulation prediction: ~5.0 pp")

    # Save
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "experiment": "rotation_gap_hardware",
        "prediction": "detection_dynamic > detection_static, Fano < 1",
        "cell": "triangle_3node",
        "chiralities": cell.chirality,
        "assignment": [GATES[a] for a in assignment],
        "layout": {str(k): v for k, v in layout.items()
                   if k != "used_qubits"},
        "results": results,
        "backend": backend.name,
        "shots": args.shots,
        "tau_list": args.tau,
        "timestamp": datetime.now().isoformat(),
    }
    path = RESULTS_DIR / f"rotation_gap_{backend.name}_{ts}.json"
    with open(path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults -> {path}")


if __name__ == "__main__":
    main()
