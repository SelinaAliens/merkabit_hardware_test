#!/usr/bin/env python3
"""
CORRELATED DECODER v2 (FAST) -- Edge-Mediated, Single Calibration
==================================================================

KEY INSIGHT: Edge-mediated correlations are LOCAL. Parameters calibrated
on radius-2 (19 nodes) should transfer to all cell sizes because each
edge contributes the same local correlation regardless of total cell size.

This avoids the 6x recalibration cost of v2.

Selina Stenberg with Claude Anthropic
"""

import sys
import numpy as np
from time import perf_counter
from scipy.stats import norm, chi2 as chi2_dist

sys.path.insert(0, r"C:\Users\selin\OneDrive\Desktop\Code")
from lattice_scaling_simulation import EisensteinCell, DynamicPentachoricCode, NUM_GATES

TARGET_FANO = 0.856
TARGET_ADJ_CORR = 0.074
TAU_B31 = 1
TAU_T75 = 5


class EdgeCorrelatedErrorModel:
    """Edge-mediated spatially correlated error model."""

    def __init__(self):
        self.edge_prob = 0.3
        self.coupling = 0.5
        self.antibunch = 0.15

    def generate_errors(self, cell, p_phys, rng):
        n = cell.num_nodes
        edge_active = rng.random(len(cell.edges)) < self.edge_prob

        hot_count = np.zeros(n)
        for idx, (i, j) in enumerate(cell.edges):
            if edge_active[idx]:
                hot_count[i] += 1
                hot_count[j] += 1

        degree = np.array([max(len(cell.neighbours[i]), 1) for i in range(n)], dtype=float)
        hot_frac = hot_count / degree

        p_node = np.full(n, p_phys)

        # Edge coupling: nodes with hot edges more likely to error
        p_node *= (1.0 + self.coupling * (hot_frac - self.edge_prob))

        # Anti-bunching: if my neighbors' edges are also hot, reduce MY probability
        for i in range(n):
            if cell.neighbours[i]:
                nbr_hot = np.mean([hot_frac[j] for j in cell.neighbours[i]])
                p_node[i] *= (1.0 - self.antibunch * nbr_hot)

        p_node = np.clip(p_node, 0.0, 1.0)

        errors = {}
        for i in range(n):
            if rng.random() < p_node[i]:
                errors[i] = int(rng.integers(0, NUM_GATES))
        return errors

    def measure_stats(self, cell, p_phys, rng, n_samples=3000):
        counts = []
        adj_same = 0
        adj_total = 0

        for _ in range(n_samples):
            errors = self.generate_errors(cell, p_phys, rng)
            counts.append(len(errors))
            errored = set(errors.keys())
            for i, j in cell.edges:
                ei = 1 if i in errored else 0
                ej = 1 if j in errored else 0
                adj_same += ei * ej
                adj_total += 1

        counts = np.array(counts, dtype=float)
        mean_c = np.mean(counts)
        fano = np.var(counts) / max(mean_c, 1e-10) if mean_c > 0.01 else 1.0

        # Adjacent correlation: P(both error) vs P(i error)*P(j error)
        p_edge_both = adj_same / max(adj_total, 1)
        p_node_err = mean_c / cell.num_nodes
        if p_node_err > 0 and p_node_err < 1:
            # Pearson correlation from contingency
            adj_corr = (p_edge_both - p_node_err**2) / (p_node_err * (1 - p_node_err))
        else:
            adj_corr = 0.0

        return fano, adj_corr, mean_c

    def calibrate(self, cell, p_ref=0.01, n_samples=3000, seed=123):
        rng = np.random.default_rng(seed)
        best_err = float('inf')
        best_params = (self.edge_prob, self.coupling, self.antibunch)

        # Coarse 3D grid
        ep_range = np.linspace(0.1, 0.7, 7)
        cp_range = np.linspace(0.2, 3.0, 7)
        ab_range = np.linspace(0.05, 0.5, 7)

        for ep in ep_range:
            for cp in cp_range:
                for ab in ab_range:
                    self.edge_prob = ep
                    self.coupling = cp
                    self.antibunch = ab
                    fano, adj, _ = self.measure_stats(cell, p_ref, rng, 500)
                    err = (fano - TARGET_FANO)**2 + 5.0 * (adj - TARGET_ADJ_CORR)**2
                    if err < best_err:
                        best_err = err
                        best_params = (ep, cp, ab)

        # Fine grid around best
        ep0, cp0, ab0 = best_params
        for ep in np.linspace(max(0.05, ep0-0.1), min(0.9, ep0+0.1), 7):
            for cp in np.linspace(max(0.1, cp0-0.4), cp0+0.4, 7):
                for ab in np.linspace(max(0.01, ab0-0.08), min(0.7, ab0+0.08), 7):
                    self.edge_prob = ep
                    self.coupling = cp
                    self.antibunch = ab
                    fano, adj, _ = self.measure_stats(cell, p_ref, rng, n_samples)
                    err = (fano - TARGET_FANO)**2 + 5.0 * (adj - TARGET_ADJ_CORR)**2
                    if err < best_err:
                        best_err = err
                        best_params = (ep, cp, ab)

        self.edge_prob, self.coupling, self.antibunch = best_params
        fano, adj, mean_c = self.measure_stats(cell, p_ref, rng, n_samples)
        return fano, adj, mean_c


def collect_syndrome(cell, code, assignment, errors, tau):
    syndrome = {}
    for t in range(tau):
        for node in range(cell.num_nodes):
            absent = code.absent_gate(assignment[node], cell.chirality[node], t)
            if node in errors and errors[node] == absent:
                syndrome[(node, t)] = None
            elif node in errors:
                syndrome[(node, t)] = 'inconsistent'
            else:
                syndrome[(node, t)] = absent
    return syndrome


class PoissonDecoder:
    def decode(self, cell, code, assignment, syndrome, tau):
        predictions = {}
        for node in range(cell.num_nodes):
            incon = sum(1 for t in range(tau) if syndrome.get((node, t)) == 'inconsistent')
            if incon > tau / 2:
                predictions[node] = code.absent_gate(assignment[node], cell.chirality[node], 0)
        return predictions


class CorrelatedDecoder:
    def __init__(self, fano=TARGET_FANO, adj_corr=TARGET_ADJ_CORR):
        self.fano = fano
        self.adj_corr = adj_corr

    def decode(self, cell, code, assignment, syndrome, tau):
        n = cell.num_nodes

        # Raw evidence
        raw = np.zeros(n)
        for node in range(n):
            for t in range(tau):
                s = syndrome.get((node, t))
                if s == 'inconsistent':
                    raw[node] += 1.0
                elif s is None:
                    raw[node] += 0.3
        raw /= max(tau, 1)

        # Edge-level belief: if both endpoints have evidence, boost both
        edge_support = np.zeros(n)
        for i, j in cell.edges:
            joint = raw[i] * raw[j]
            edge_support[i] += joint
            edge_support[j] += joint
        degree = np.array([max(len(cell.neighbours[i]), 1) for i in range(n)], dtype=float)
        edge_support /= degree

        # Belief propagation with anti-bunching
        belief = raw.copy()
        for _ in range(3):
            new_belief = raw.copy()
            for node in range(n):
                nbrs = cell.neighbours[node]
                if nbrs:
                    nbr_flagged = sum(1 for nb in nbrs if belief[nb] > 0.5)
                    avg_nbr = np.mean([belief[nb] for nb in nbrs])

                    # Anti-bunching: suppress if neighbors flagged
                    if nbr_flagged > 0:
                        new_belief[node] *= self.fano ** nbr_flagged

                    # Boost isolated errors (strong evidence, quiet neighbors)
                    if raw[node] > 0.5 and avg_nbr < 0.3:
                        new_belief[node] *= 1.0 + (1.0 - self.fano)

                new_belief[node] += edge_support[node] * 0.1
            belief = new_belief

        # Fano-constrained threshold
        syndrome_density = np.mean(raw)
        expected = max(1, n * syndrome_density * self.fano)

        candidates = sorted(range(n), key=lambda i: -belief[i])
        predictions = {}
        for node in candidates:
            if belief[node] <= 0.4:
                break
            if len(predictions) >= expected * 1.5:
                break
            predictions[node] = code.absent_gate(assignment[node], cell.chirality[node], 0)

        return predictions


def evaluate(cell, code, error_model, poisson_dec, correlated_dec,
             p_values, n_trials, n_assignments, seed, tau):
    rng = np.random.default_rng(seed)
    assignments, _ = code.find_valid_assignments(rng, n_assignments)
    if not assignments:
        return {}

    trials_per = max(1, n_trials // len(assignments))
    results = {}

    for p in p_values:
        pf, cf, po, co, total = 0, 0, 0, 0, 0
        for assign in assignments:
            for _ in range(trials_per):
                errors = error_model.generate_errors(cell, p, rng)
                syn = collect_syndrome(cell, code, assign, errors, tau)
                pp = poisson_dec.decode(cell, code, assign, syn, tau)
                cp = correlated_dec.decode(cell, code, assign, syn, tau)

                actual = set(errors.items())
                p_fail = len(actual.symmetric_difference(set(pp.items()))) > 0
                c_fail = len(actual.symmetric_difference(set(cp.items()))) > 0

                if p_fail: pf += 1
                if c_fail: cf += 1
                if p_fail and not c_fail: po += 1
                if c_fail and not p_fail: co += 1
                total += 1

        imp = (pf - cf) / max(1, pf) * 100
        disc = po + co
        if disc > 0:
            chi2_val = (po - co)**2 / disc
            pval = 1.0 - chi2_dist.cdf(chi2_val, df=1)
        else:
            pval = 1.0

        results[p] = {
            'poisson_LER': pf/total, 'correlated_LER': cf/total,
            'improvement': imp, 'p_value': pval,
            'p_only': po, 'c_only': co, 'total': total
        }
    return results


def main():
    print("=" * 70)
    print("CORRELATED DECODER v2 (FAST) -- Edge-Mediated")
    print(f"Target: Fano={TARGET_FANO}, adj_corr={TARGET_ADJ_CORR}")
    print("Strategy: calibrate on r=2 (19 nodes), transfer to all sizes")
    print("=" * 70)

    P_VALUES = [1e-3, 1e-2, 1e-1]
    poisson_dec = PoissonDecoder()
    correlated_dec = CorrelatedDecoder()

    # STEP 1: Calibrate on radius 2
    print("\n--- CALIBRATION on 19-node cell ---")
    cal_cell = EisensteinCell(2)
    error_model = EdgeCorrelatedErrorModel()
    t0 = perf_counter()
    fano, adj, mc = error_model.calibrate(cal_cell, p_ref=0.01, n_samples=3000)
    dt = perf_counter() - t0
    print(f"  Time: {dt:.0f}s")
    print(f"  Fano:     {fano:.4f} (target {TARGET_FANO})")
    print(f"  adj_corr: {adj:.4f} (target {TARGET_ADJ_CORR})")
    print(f"  Params: edge_prob={error_model.edge_prob:.3f}, "
          f"coupling={error_model.coupling:.3f}, antibunch={error_model.antibunch:.3f}")

    # STEP 2: Verify transfer to other cell sizes
    print("\n--- TRANSFER VERIFICATION ---")
    print(f"  {'Radius':>6s}  {'Nodes':>5s}  {'Fano':>8s}  {'adj_corr':>8s}  {'mean_err':>8s}")
    rng_verify = np.random.default_rng(999)
    for r in range(1, 7):
        cell = EisensteinCell(r)
        f, a, m = error_model.measure_stats(cell, 0.01, rng_verify, 3000)
        ok_f = "OK" if abs(f - TARGET_FANO) < 0.1 else "MISS"
        ok_a = "OK" if abs(a - TARGET_ADJ_CORR) < 0.05 else "MISS"
        print(f"  {r:>6d}  {cell.num_nodes:>5d}  {f:8.4f} {ok_f:>4s}  {a:8.4f} {ok_a:>4s}  {m:8.2f}")

    # STEP 3: Run decoder comparison at all sizes
    configs = {
        1: (5000, 50), 2: (4000, 40), 3: (3000, 30),
        4: (2000, 25), 5: (1500, 20), 6: (1000, 15)
    }

    all_b31 = {}
    all_t75 = {}

    for radius in range(1, 7):
        cell = EisensteinCell(radius)
        code = DynamicPentachoricCode(cell)
        n_trials, n_assign = configs[radius]

        print(f"\n{'='*60}")
        print(f"{cell.num_nodes}-NODE CELL (radius {radius})")
        print(f"{'='*60}")

        for tau, label, store in [(TAU_B31, "B31 tau=1", all_b31),
                                   (TAU_T75, "T75 tau=5", all_t75)]:
            t0 = perf_counter()
            res = evaluate(cell, code, error_model, poisson_dec, correlated_dec,
                          P_VALUES, n_trials, n_assign, seed=42+radius+tau, tau=tau)
            dt = perf_counter() - t0
            print(f"\n  {label} ({dt:.1f}s)")
            print(f"  {'p':>8s}  {'P_LER':>8s}  {'C_LER':>8s}  {'Impr':>7s}  {'pval':>8s}  {'P>C':>4s}  {'C>P':>4s}")
            for p in P_VALUES:
                r = res[p]
                s = '*' if r['p_value'] < 0.05 else ''
                print(f"  {p:8.0e}  {r['poisson_LER']:8.4f}  {r['correlated_LER']:8.4f}  "
                      f"{r['improvement']:6.1f}%  {r['p_value']:8.4f}{s}  "
                      f"{r['p_only']:4d}  {r['c_only']:4d}")
            store[cell.num_nodes] = res

    # FINAL TABLE
    print(f"\n{'='*60}")
    print("SCALING TABLE")
    print(f"{'='*60}")
    rmap = {7:1, 19:2, 37:3, 61:4, 91:5, 127:6}

    for label, data in [("tau=1 B31 REAL QUBITS", all_b31),
                         ("tau=5 T75 MERKABIT", all_t75)]:
        print(f"\n  {label}")
        print(f"  {'N':>5s} {'R':>2s}", end="")
        for p in P_VALUES:
            print(f"  p={p:.0e}", end="")
        print()
        for nn in sorted(data.keys()):
            print(f"  {nn:5d} {rmap[nn]:>2d}", end="")
            for p in P_VALUES:
                r = data[nn][p]
                s = '*' if r['p_value'] < 0.05 else ' '
                print(f"  {r['improvement']:5.1f}%{s}", end="")
            print()

    # SCALING TREND
    print(f"\n{'='*60}")
    print("TREND at p=1e-2")
    print(f"{'='*60}")
    for label, data in [("B31", all_b31), ("T75", all_t75)]:
        nodes = sorted(data.keys())
        imps = [data[n][1e-2]['improvement'] for n in nodes]
        print(f"\n  {label}:")
        for n, i in zip(nodes, imps):
            bar = '#' * max(0, int(i / 2))
            print(f"    {n:>5d}: {i:6.1f}% {bar}")
        if len(imps) >= 3:
            x = np.log(np.array(nodes))
            slope = np.polyfit(x, np.array(imps), 1)[0]
            print(f"  slope = {slope:.2f} %/ln(node)")


if __name__ == '__main__':
    main()
