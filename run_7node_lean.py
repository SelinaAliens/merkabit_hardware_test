"""
Lean 7-node Eisenstein cell test — baselines only, no error sweep.
Measures detection rate, Fano factor, and rotation gap.
"""
import json, sys, numpy as np
sys.stdout.reconfigure(encoding='utf-8')

from qiskit import transpile
from qiskit_aer import AerSimulator
from qubit_mapper import EisensteinCell, GATES
from ouroboros_circuit import find_valid_assignment
from multi_merkabit_circuit import (
    build_multi_merkabit_circuit, analyze_multi_results
)

backend = AerSimulator()
cell = EisensteinCell(radius=1)
cell.summary()

assignment = find_valid_assignment(cell, seed=42)
print(f"\nBase assignment: {[GATES[a] for a in assignment]}")

SHOTS = 4096
results = {}

for tau in [1, 5, 12]:
    print(f"\n{'='*60}")
    print(f"tau = {tau}")
    print(f"{'='*60}")

    qc, meta = build_multi_merkabit_circuit(cell, assignment, tau=tau)
    qc_t = transpile(qc, backend, optimization_level=1)

    n_cx = qc_t.count_ops().get('cx', 0)
    print(f"Circuit: {qc_t.depth()} depth, {n_cx} CX, {qc_t.num_qubits} qubits")

    job = backend.run(qc_t, shots=SHOTS)
    counts = job.result().get_counts()
    result = analyze_multi_results(counts, cell, tau)

    print(f"Detection rate: {result['detection_rate']:.4f}")
    print(f"Fano factor: {result['fano_factor']:.4f} "
          f"({'SUB-Poissonian' if result['sub_poissonian'] else 'super-Poissonian'})")
    print(f"Mean syndrome weight: {result['mean_syndrome_weight']:.2f}")
    print(f"Per-round Fano: {[f'{f:.4f}' for f in result['per_round_fano']]}")

    # Edge breakdown
    print(f"\nEdge fire rates:")
    for e_idx, (i, j) in enumerate(cell.edges):
        chi_i = cell.chirality[i]
        chi_j = cell.chirality[j]
        diff = abs(chi_i - chi_j)
        rate = result['edge_fire_rates'][e_idx]
        label = 'COUNTER-ROTATING' if diff == 2 else f'step-{diff}'
        print(f"  ({i},{j}) chi=({chi_i:+d},{chi_j:+d}) diff={diff} "
              f"rate={rate:.4f} [{label}]")

    results[f'tau_{tau}'] = result

# Rotation gap
print(f"\n{'='*60}")
print("ROTATION GAP SUMMARY")
print(f"{'='*60}")
for tau_key in ['tau_1', 'tau_5', 'tau_12']:
    if tau_key in results:
        r = results[tau_key]
        tau_val = r['tau']
        print(f"  tau={tau_val:>2}: det={r['detection_rate']:.4f}, "
              f"Fano={r['fano_factor']:.4f}, "
              f"per-round-F={np.mean(r['per_round_fano']):.4f}")

if 'tau_1' in results and 'tau_5' in results:
    gap = results['tau_5']['detection_rate'] - results['tau_1']['detection_rate']
    print(f"\n  ROTATION GAP (tau=5 vs tau=1): {gap*100:.1f} pp")

if 'tau_1' in results and 'tau_12' in results:
    gap12 = results['tau_12']['detection_rate'] - results['tau_1']['detection_rate']
    print(f"  ROTATION GAP (tau=12 vs tau=1): {gap12*100:.1f} pp")

# Save
with open('outputs/full_7node_lean.json', 'w') as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nSaved to outputs/full_7node_lean.json")
