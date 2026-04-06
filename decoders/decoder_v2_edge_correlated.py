#!/usr/bin/env python3
"""
CORRELATED DECODER v2 -- Edge-Mediated Error Model
====================================================

v1 FAILURE: BFS-order Markov chain couldn't produce target Fano/adj_corr
at large cell sizes. Anti-bunching diluted through shells.

v2 FIX: Edge-mediated correlations. Each EDGE has a shared noise variable.
Node error probability depends on the noise state of ALL its edges.
This is physically correct: IBM ECR gate noise is edge-local.

Model:
  1. Each edge (i,j) draws a shared noise variable z_ij ~ Bernoulli(q)
  2. Node i's effective error probability = p * (1 - alpha * f(z_neighbors))
     where f sums the noise state of all edges touching node i
  3. Anti-bunching emerges because: if edge (i,j) is "hot" (z=1),
     both i and j see elevated noise, but the TOTAL error count is
     suppressed because the noise is shared (not independent)

Parameters alpha and q calibrated to match IBM Fano=0.856 and adj_corr=0.074.

Selina Stenberg with Claude Anthropic
"""

import sys
import numpy as np
from time import perf_counter
from scipy.stats import norm

sys.path.insert(0, r"C:\Users\selin\OneDrive\Desktop\Code")
from lattice_scaling_simulation import EisensteinCell, DynamicPentachoricCode, NUM_GATES

# ============================================================================
# IBM HARDWARE PARAMETERS
# ============================================================================
TARGET_FANO = 0.856
TARGET_ADJ_CORR = 0.074
TAU_B31 = 1
TAU_T75 = 5


# ============================================================================
# EDGE-MEDIATED ERROR MODEL
# ============================================================================

class EdgeCorrelatedErrorModel:
    """
    Error model where correlations propagate through edges (couplers),
    not through BFS ordering.

    Physical basis: IBM ECR gate noise is shared between the two qubits
    it connects. This creates:
    - Positive adjacent correlation (both qubits see same coupler noise)
    - Sub-Poissonian total count (shared noise reduces variance)

    Method:
    1. Each edge draws shared noise z ~ Bernoulli(edge_activation_prob)
    2. Node i counts its "hot" edges: h_i = sum of z over edges touching i
    3. Node error prob = p * (base_rate + coupling * h_i / degree_i)
       with a global normalization to keep mean error rate = p
    4. Anti-bunching: nodes with many hot edges have CORRELATED errors,
       but the sharing reduces total count variance below Poisson
    """

    def __init__(self, target_fano=TARGET_FANO, target_adj_corr=TARGET_ADJ_CORR):
        self.target_fano = target_fano
        self.target_adj_corr = target_adj_corr
        # Parameters to calibrate
        self.edge_prob = 0.3       # probability each edge is "hot"
        self.coupling = 0.5       # how much hot edges affect error prob
        self.antibunch = 0.15     # global anti-bunching (reduces variance)

    def generate_errors(self, cell, p_phys, rng):
        """Generate spatially correlated errors via edge noise."""
        n = cell.num_nodes

        # Step 1: Activate edges
        edge_active = rng.random(len(cell.edges)) < self.edge_prob

        # Step 2: Count hot edges per node
        hot_count = np.zeros(n)
        for idx, (i, j) in enumerate(cell.edges):
            if edge_active[idx]:
                hot_count[i] += 1
                hot_count[j] += 1

        # Degree of each node
        degree = np.array([len(cell.neighbours[i]) for i in range(n)], dtype=float)
        degree = np.maximum(degree, 1.0)

        # Step 3: Compute per-node error probability
        # Normalized hot fraction: how many of my edges are hot
        hot_frac = hot_count / degree

        # Base probability with coupling to hot edges
        # Nodes with more hot edges are more likely to error
        # but the SHARING creates sub-Poissonian statistics
        p_node = p_phys * (1.0 + self.coupling * (hot_frac - self.edge_prob))

        # Anti-bunching: if many neighbors would also error, reduce probability
        # This is the key sub-Poissonian mechanism
        # Estimate neighbor error likelihood from their hot fractions
        for i in range(n):
            nbr_hot = np.mean([hot_frac[j] for j in cell.neighbours[i]]) if cell.neighbours[i] else 0
            # If neighbors are likely to error (high hot_frac), reduce our prob
            p_node[i] *= (1.0 - self.antibunch * nbr_hot)

        p_node = np.clip(p_node, 0.0, 1.0)

        # Step 4: Generate errors
        errors = {}
        for i in range(n):
            if rng.random() < p_node[i]:
                errors[i] = int(rng.integers(0, NUM_GATES))

        return errors

    def measure_stats(self, cell, p_phys, rng, n_samples=5000):
        """Measure Fano factor and adjacent correlation."""
        counts = []
        adj_i_list = []
        adj_j_list = []

        for _ in range(n_samples):
            errors = self.generate_errors(cell, p_phys, rng)
            counts.append(len(errors))
            errored = set(errors.keys())
            for i, j in cell.edges:
                adj_i_list.append(1 if i in errored else 0)
                adj_j_list.append(1 if j in errored else 0)

        counts = np.array(counts, dtype=float)
        mean_c = np.mean(counts)
        if mean_c > 0.01:
            fano = np.var(counts) / mean_c
        else:
            fano = 1.0

        a = np.array(adj_i_list)
        b = np.array(adj_j_list)
        if np.std(a) > 0 and np.std(b) > 0:
            adj_corr = np.corrcoef(a, b)[0, 1]
        else:
            adj_corr = 0.0

        return fano, adj_corr, mean_c

    def calibrate(self, cell, p_ref=0.01, n_samples=5000, seed=123):
        """3D grid search over (edge_prob, coupling, antibunch)."""
        rng = np.random.default_rng(seed)
        best_err = float('inf')
        best_params = (self.edge_prob, self.coupling, self.antibunch)

        print(f"    Calibrating 3D grid (edge_prob x coupling x antibunch)...")

        # Coarse grid
        for ep in np.linspace(0.1, 0.8, 8):
            for cp in np.linspace(0.1, 2.0, 8):
                for ab in np.linspace(0.05, 0.6, 8):
                    self.edge_prob = ep
                    self.coupling = cp
                    self.antibunch = ab
                    fano, adj, _ = self.measure_stats(cell, p_ref, rng,
                                                       min(n_samples, 1000))
                    err = (fano - self.target_fano)**2 + \
                          5.0 * (adj - self.target_adj_corr)**2  # weight adj_corr more
                    if err < best_err:
                        best_err = err
                        best_params = (ep, cp, ab)

        # Fine refinement around best
        ep0, cp0, ab0 = best_params
        for ep in np.linspace(max(0.05, ep0-0.1), min(0.95, ep0+0.1), 8):
            for cp in np.linspace(max(0.05, cp0-0.3), cp0+0.3, 8):
                for ab in np.linspace(max(0.01, ab0-0.1), min(0.8, ab0+0.1), 8):
                    self.edge_prob = ep
                    self.coupling = cp
                    self.antibunch = ab
                    fano, adj, _ = self.measure_stats(cell, p_ref, rng, n_samples)
                    err = (fano - self.target_fano)**2 + \
                          5.0 * (adj - self.target_adj_corr)**2
                    if err < best_err:
                        best_err = err
                        best_params = (ep, cp, ab)

        self.edge_prob, self.coupling, self.antibunch = best_params
        fano, adj, mean_c = self.measure_stats(cell, p_ref, rng, n_samples)
        return fano, adj, mean_c


# ============================================================================
# SYNDROME COLLECTION
# ============================================================================

def collect_syndrome(cell, code, assignment, errors, tau):
    syndrome = {}
    for t in range(tau):
        for node in range(cell.num_nodes):
            absent = code.absent_gate(assignment[node], cell.chirality[node], t)
            if node in errors and errors[node] == absent:
                syndrome[(node, t)] = None  # invisible
            elif node in errors:
                syndrome[(node, t)] = 'inconsistent'
            else:
                syndrome[(node, t)] = absent
    return syndrome


# ============================================================================
# DECODERS
# ============================================================================

class PoissonDecoder:
    """Standard majority-vote decoder."""
    def decode(self, cell, code, assignment, syndrome, tau):
        predictions = {}
        for node in range(cell.num_nodes):
            inconsistent_count = sum(
                1 for t in range(tau)
                if syndrome.get((node, t)) == 'inconsistent')
            if inconsistent_count > tau / 2:
                predictions[node] = code.absent_gate(
                    assignment[node], cell.chirality[node], 0)
        return predictions


class CorrelatedDecoder:
    """
    Bayesian decoder with edge-mediated anti-bunching prior.

    Key difference from v1: the prior is applied at the EDGE level,
    matching the physical error model.
    """
    def __init__(self, fano=TARGET_FANO, adj_corr=TARGET_ADJ_CORR):
        self.fano = fano
        self.adj_corr = adj_corr
        self.antibunch_factor = 1.0 - (1.0 - fano)  # 0.856

    def decode(self, cell, code, assignment, syndrome, tau):
        n = cell.num_nodes

        # Pass 1: raw evidence per node
        raw_score = np.zeros(n)
        for node in range(n):
            for t in range(tau):
                s = syndrome.get((node, t))
                if s == 'inconsistent':
                    raw_score[node] += 1.0
                elif s is None:
                    raw_score[node] += 0.3
        raw_score /= max(tau, 1)

        # Pass 2: edge-level belief propagation
        # For each edge, compute joint evidence
        edge_belief = np.zeros(len(cell.edges))
        for idx, (i, j) in enumerate(cell.edges):
            # If both endpoints have evidence, the shared noise is likely
            # This INCREASES confidence in both
            edge_belief[idx] = raw_score[i] * raw_score[j] * (1 + self.adj_corr * 10)

        # Accumulate edge beliefs back to nodes
        belief = raw_score.copy()
        node_edge_support = np.zeros(n)
        for idx, (i, j) in enumerate(cell.edges):
            node_edge_support[i] += edge_belief[idx]
            node_edge_support[j] += edge_belief[idx]

        # Normalize by degree
        degree = np.array([max(len(cell.neighbours[i]), 1) for i in range(n)], dtype=float)
        node_edge_support /= degree

        # Pass 3: anti-bunching correction
        # If too many neighbors are flagged, reduce belief (sub-Poisson prior)
        for iteration in range(3):
            new_belief = raw_score.copy()
            for node in range(n):
                # Neighbor evidence
                nbr_beliefs = [belief[nbr] for nbr in cell.neighbours[node]]
                if nbr_beliefs:
                    avg_nbr = np.mean(nbr_beliefs)
                    n_nbr_flagged = sum(1 for b in nbr_beliefs if b > 0.5)

                    # Anti-bunching: suppress if neighbors already flagged
                    if n_nbr_flagged > 0:
                        new_belief[node] *= self.antibunch_factor ** n_nbr_flagged

                    # But boost if THIS node has strong evidence and neighbors don't
                    if raw_score[node] > 0.5 and avg_nbr < 0.3:
                        new_belief[node] *= 1.0 + (1.0 - self.fano)  # +0.144 boost

                # Add edge support
                new_belief[node] += node_edge_support[node] * 0.1

            belief = new_belief

        # Pass 4: Fano-constrained thresholding
        # Sub-Poisson: total flagged should be LESS than Poisson expects
        candidates = [(node, belief[node]) for node in range(n) if belief[node] > 0.3]
        candidates.sort(key=lambda x: -x[1])

        # Expected errors at current error rate (estimate from syndrome density)
        syndrome_density = np.mean(raw_score)
        expected_errors = max(1, n * syndrome_density * self.fano)

        predictions = {}
        for node, b in candidates:
            if len(predictions) >= expected_errors * 1.5:
                break  # Fano cap: don't flag more than sub-Poisson allows
            if b > 0.5:
                predictions[node] = code.absent_gate(
                    assignment[node], cell.chirality[node], 0)

        return predictions


# ============================================================================
# EVALUATION
# ============================================================================

def evaluate_decoders(cell, code, error_model, poisson_dec, correlated_dec,
                      p_values, n_trials, n_assignments, seed, tau):
    rng = np.random.default_rng(seed)
    assignments, _ = code.find_valid_assignments(rng, n_assignments)
    if not assignments:
        print("  ERROR: No valid assignments found!")
        return {}

    n_assign = len(assignments)
    trials_per_assign = max(1, n_trials // n_assign)

    results = {}
    for p in p_values:
        poisson_fails = 0
        correlated_fails = 0
        # Track discordant pairs for McNemar
        poisson_only_fail = 0  # Poisson wrong, Correlated right
        correlated_only_fail = 0  # Correlated wrong, Poisson right
        total = 0

        for assignment in assignments:
            for _ in range(trials_per_assign):
                errors = error_model.generate_errors(cell, p, rng)
                syndrome = collect_syndrome(cell, code, assignment, errors, tau)
                p_pred = poisson_dec.decode(cell, code, assignment, syndrome, tau)
                c_pred = correlated_dec.decode(cell, code, assignment, syndrome, tau)

                actual_set = set(errors.items())
                p_fail = len(actual_set.symmetric_difference(set(p_pred.items()))) > 0
                c_fail = len(actual_set.symmetric_difference(set(c_pred.items()))) > 0

                if p_fail:
                    poisson_fails += 1
                if c_fail:
                    correlated_fails += 1
                if p_fail and not c_fail:
                    poisson_only_fail += 1
                if c_fail and not p_fail:
                    correlated_only_fail += 1
                total += 1

        p_ler = poisson_fails / total if total > 0 else 0
        c_ler = correlated_fails / total if total > 0 else 0
        improvement = ((poisson_fails - correlated_fails) /
                       max(1, poisson_fails))

        # McNemar's test (proper paired comparison)
        disc = poisson_only_fail + correlated_only_fail
        if disc > 0:
            chi2 = (poisson_only_fail - correlated_only_fail)**2 / disc
            from scipy.stats import chi2 as chi2_dist
            p_val = 1.0 - chi2_dist.cdf(chi2, df=1)
        else:
            p_val = 1.0

        results[p] = {
            'total': total,
            'poisson_LER': p_ler,
            'correlated_LER': c_ler,
            'improvement_pct': improvement * 100,
            'p_value': p_val,
            'poisson_only_fail': poisson_only_fail,
            'correlated_only_fail': correlated_only_fail,
        }

    return results


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 70)
    print("CORRELATED DECODER v2 -- Edge-Mediated Error Model")
    print(f"Target: Fano={TARGET_FANO}, adj_corr={TARGET_ADJ_CORR}")
    print("=" * 70)

    P_VALUES = [1e-3, 1e-2, 1e-1]

    poisson_dec = PoissonDecoder()
    correlated_dec = CorrelatedDecoder(fano=TARGET_FANO, adj_corr=TARGET_ADJ_CORR)

    configs = {
        1: {'n_trials': 5000, 'n_assignments': 50},
        2: {'n_trials': 4000, 'n_assignments': 40},
        3: {'n_trials': 3000, 'n_assignments': 30},
        4: {'n_trials': 2000, 'n_assignments': 25},
        5: {'n_trials': 1500, 'n_assignments': 20},
        6: {'n_trials': 1000, 'n_assignments': 15},
    }

    all_b31 = {}
    all_t75 = {}

    for radius in range(1, 7):
        cell = EisensteinCell(radius)
        code = DynamicPentachoricCode(cell)
        error_model = EdgeCorrelatedErrorModel()
        cfg = configs[radius]

        print(f"\n{'=' * 70}")
        print(f"{cell.num_nodes}-NODE CELL (radius {radius})")
        print(f"  Interior: {sum(1 for i in range(cell.num_nodes) if len(cell.neighbours[i]) == 6)}"
              f"  Boundary: {sum(1 for i in range(cell.num_nodes) if len(cell.neighbours[i]) < 6)}"
              f"  Edges: {len(cell.edges)}")
        print(f"{'=' * 70}")

        # Calibrate
        t0 = perf_counter()
        fano, adj, mean_c = error_model.calibrate(cell, p_ref=0.01, n_samples=3000)
        dt = perf_counter() - t0
        print(f"  Calibrated in {dt:.0f}s:")
        print(f"    Fano:     target={TARGET_FANO:.3f}  measured={fano:.3f}  err={abs(fano-TARGET_FANO):.4f}")
        print(f"    adj_corr: target={TARGET_ADJ_CORR:.3f}  measured={adj:.3f}  err={abs(adj-TARGET_ADJ_CORR):.4f}")
        print(f"    mean errors/trial: {mean_c:.2f}")
        print(f"    params: edge_prob={error_model.edge_prob:.3f}, coupling={error_model.coupling:.3f}, antibunch={error_model.antibunch:.3f}")

        # tau=1
        print(f"\n  --- tau=1: B31 STATIC ---")
        t0 = perf_counter()
        res_b31 = evaluate_decoders(cell, code, error_model, poisson_dec,
                                     correlated_dec, P_VALUES,
                                     n_trials=cfg['n_trials'],
                                     n_assignments=cfg['n_assignments'],
                                     seed=42+radius, tau=TAU_B31)
        dt = perf_counter() - t0
        print(f"  Time: {dt:.1f}s")
        print(f"  {'p':>8s}  {'P_LER':>10s}  {'C_LER':>10s}  {'Impr':>7s}  {'p-val':>8s}  {'P_only':>6s}  {'C_only':>6s}")
        for p in P_VALUES:
            r = res_b31[p]
            sig = '*' if r['p_value'] < 0.05 else ''
            print(f"  {p:8.0e}  {r['poisson_LER']:10.4f}  {r['correlated_LER']:10.4f}  "
                  f"{r['improvement_pct']:6.1f}%  {r['p_value']:8.4f}{sig}  "
                  f"{r['poisson_only_fail']:6d}  {r['correlated_only_fail']:6d}")
        all_b31[cell.num_nodes] = res_b31

        # tau=5
        print(f"\n  --- tau=5: T75 DYNAMIC ---")
        t0 = perf_counter()
        res_t75 = evaluate_decoders(cell, code, error_model, poisson_dec,
                                     correlated_dec, P_VALUES,
                                     n_trials=cfg['n_trials'],
                                     n_assignments=cfg['n_assignments'],
                                     seed=42+radius, tau=TAU_T75)
        dt = perf_counter() - t0
        print(f"  Time: {dt:.1f}s")
        print(f"  {'p':>8s}  {'P_LER':>10s}  {'C_LER':>10s}  {'Impr':>7s}  {'p-val':>8s}  {'P_only':>6s}  {'C_only':>6s}")
        for p in P_VALUES:
            r = res_t75[p]
            sig = '*' if r['p_value'] < 0.05 else ''
            print(f"  {p:8.0e}  {r['poisson_LER']:10.4f}  {r['correlated_LER']:10.4f}  "
                  f"{r['improvement_pct']:6.1f}%  {r['p_value']:8.4f}{sig}  "
                  f"{r['poisson_only_fail']:6d}  {r['correlated_only_fail']:6d}")
        all_t75[cell.num_nodes] = res_t75

    # ================================================================
    # FINAL SCALING TABLE
    # ================================================================
    print(f"\n{'=' * 70}")
    print("SCALING TABLE: IMPROVEMENT (%) vs CELL SIZE")
    print(f"{'=' * 70}")

    for label, results_dict in [("tau=1 B31 (REAL QUBITS)", all_b31),
                                  ("tau=5 T75 (MERKABIT)", all_t75)]:
        print(f"\n  {label}")
        rmap = {7:1, 19:2, 37:3, 61:4, 91:5, 127:6}
        print(f"  {'Nodes':>5s}  {'R':>2s}  ", end="")
        for p in P_VALUES:
            print(f" p={p:.0e} ", end="")
        print()

        for n_nodes in sorted(results_dict.keys()):
            r = rmap.get(n_nodes, '?')
            print(f"  {n_nodes:5d}  {r:>2}  ", end="")
            for p in P_VALUES:
                res = results_dict[n_nodes].get(p)
                if res:
                    imp = res['improvement_pct']
                    sig = '*' if res['p_value'] < 0.05 else ' '
                    print(f" {imp:5.1f}%{sig}", end="")
                else:
                    print(f"   N/A  ", end="")
            print()

    # Trend analysis
    print(f"\n{'=' * 70}")
    print("TREND: tau=1 improvement at p=1e-2 vs cell size")
    print(f"{'=' * 70}")
    p_test = 1e-2
    nodes_list = sorted(all_b31.keys())
    imps = []
    for n_nodes in nodes_list:
        res = all_b31[n_nodes].get(p_test)
        if res:
            imps.append(res['improvement_pct'])
            print(f"  {n_nodes:>5d} nodes: {res['improvement_pct']:6.1f}%  (P_LER={res['poisson_LER']:.4f}, C_LER={res['correlated_LER']:.4f})")

    if len(imps) >= 4:
        # Linear regression on improvement vs log(nodes)
        x = np.log(np.array(nodes_list[:len(imps)]))
        y = np.array(imps)
        slope = np.polyfit(x, y, 1)[0]
        print(f"\n  Slope (improvement vs ln(nodes)): {slope:.2f} %/ln(node)")
        if slope > 0:
            print(f"  >>> IMPROVEMENT GROWS WITH CELL SIZE")
            print(f"  >>> Correlated decoder becomes MORE valuable at scale")
        elif slope < -1:
            print(f"  >>> Improvement DECREASES with cell size")
            print(f"  >>> Hardware rotation (T75) needed for scaling advantage")
        else:
            print(f"  >>> Improvement approximately constant across scales")


if __name__ == '__main__':
    main()
