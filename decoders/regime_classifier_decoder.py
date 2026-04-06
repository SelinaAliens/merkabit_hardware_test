#!/usr/bin/env python3
"""
REGIME CLASSIFIER DECODER -- "Stop Correcting What Isn't Broken"
================================================================

Paper 3: The Rotation Gap Is Not An Error

PARADIGM SHIFT: Standard QEC treats ALL syndrome activations as errors
to be corrected. But IBM hardware shows sub-Poissonian statistics
(Fano = 0.856), meaning the error process has cooperative structure.

This decoder classifies each node into one of two regimes BEFORE
deciding whether to correct:

  B31 (binary): Node behaves like independent Poisson noise.
                 → Standard correction applied.

  T75 (ternary): Node shows structured, anti-bunched behavior
                  consistent with ternary transitions.
                  → DO NOT CORRECT. The "error" is signal.

The hypothesis: a fraction of what standard decoders call "errors"
are actually valid ternary transitions that the binary measurement
basis misreads as noise. Correcting them DESTROYS information.

If LER_hybrid < LER_binary, standard QEC is actively destroying
information by correcting valid states.

Hardware evidence:
  - Fano = 0.856 (sub-Poissonian): self-organization measured as noise
  - adj_corr = 0.074: neighbor errors weakly correlated (structured)
  - T2 persistent (H~1.0): system maintaining ternary coherence
  - 13.5% of segments show alpha=4/3: fraction going ternary spontaneously
  - Distance-independent: physical error level, not decoder artifact

Selina Stenberg with Claude Anthropic
"""

import sys
import numpy as np
from time import perf_counter
from collections import Counter, defaultdict
from scipy.stats import chi2 as chi2_dist

sys.path.insert(0, r"C:\Users\selin\OneDrive\Desktop\Code")
from lattice_scaling_simulation import EisensteinCell, DynamicPentachoricCode, NUM_GATES

# ============================================================================
# HARDWARE-MEASURED CONSTANTS (from 756 IBM runs)
# ============================================================================

TARGET_FANO = 0.856       # Sub-Poissonian: 14.4% fewer events than Poisson
TARGET_ADJ_CORR = 0.074   # Positive neighbor correlation
TERNARY_FRACTION = 0.144  # 1 - Fano: fraction of "errors" that are structured
TAU_B31 = 1               # Real qubits: static, no rotation
TAU_T75 = 5               # Merkabit: full pentachoric scan

# Classification thresholds (derived from hardware statistics)
# A node is classified T75 if its LOCAL syndrome pattern is consistent
# with structured (anti-bunched) behavior rather than random noise
COORDINATION_THRESHOLD = 5  # Nodes with < this many neighbors have more freedom
ISOLATION_THRESHOLD = 0.3   # If neighbors are quiet, this node may be ternary


# ============================================================================
# EDGE-MEDIATED ERROR MODEL (hardware-calibrated)
# ============================================================================

class EdgeCorrelatedErrorModel:
    """
    Generates errors with IBM-measured statistics.
    Edge-mediated: shared ECR gate noise creates anti-bunching.
    """

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

        degree = np.array([max(len(cell.neighbours[i]), 1) for i in range(n)],
                          dtype=float)
        hot_frac = hot_count / degree
        p_node = np.full(n, p_phys)
        p_node *= (1.0 + self.coupling * (hot_frac - self.edge_prob))

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
        p_edge_both = adj_same / max(adj_total, 1)
        p_node_err = mean_c / cell.num_nodes
        if 0 < p_node_err < 1:
            adj_corr = (p_edge_both - p_node_err**2) / (p_node_err * (1 - p_node_err))
        else:
            adj_corr = 0.0
        return fano, adj_corr, mean_c

    def calibrate(self, cell, p_ref=0.01, n_samples=3000, seed=123):
        rng = np.random.default_rng(seed)
        best_err = float('inf')
        best_params = (self.edge_prob, self.coupling, self.antibunch)

        for ep in np.linspace(0.1, 0.7, 7):
            for cp in np.linspace(0.2, 3.0, 7):
                for ab in np.linspace(0.05, 0.5, 7):
                    self.edge_prob, self.coupling, self.antibunch = ep, cp, ab
                    fano, adj, _ = self.measure_stats(cell, p_ref, rng, 500)
                    err = (fano - TARGET_FANO)**2 + 5.0*(adj - TARGET_ADJ_CORR)**2
                    if err < best_err:
                        best_err = err
                        best_params = (ep, cp, ab)

        ep0, cp0, ab0 = best_params
        for ep in np.linspace(max(0.05, ep0-0.1), min(0.9, ep0+0.1), 7):
            for cp in np.linspace(max(0.1, cp0-0.4), cp0+0.4, 7):
                for ab in np.linspace(max(0.01, ab0-0.08), min(0.7, ab0+0.08), 7):
                    self.edge_prob, self.coupling, self.antibunch = ep, cp, ab
                    fano, adj, _ = self.measure_stats(cell, p_ref, rng, n_samples)
                    err = (fano - TARGET_FANO)**2 + 5.0*(adj - TARGET_ADJ_CORR)**2
                    if err < best_err:
                        best_err = err
                        best_params = (ep, cp, ab)

        self.edge_prob, self.coupling, self.antibunch = best_params
        return self.measure_stats(cell, p_ref, rng, n_samples)


# ============================================================================
# SYNDROME COLLECTION
# ============================================================================

def collect_syndrome(cell, code, assignment, errors, tau):
    """Standard syndrome: which nodes show inconsistencies at each time step."""
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


def collect_rich_syndrome(cell, code, assignment, errors, tau):
    """
    Rich syndrome with per-node metadata for regime classification.
    Returns: syndrome dict + per-node feature vectors.
    """
    n = cell.num_nodes
    syndrome = collect_syndrome(cell, code, assignment, errors, tau)

    # Per-node features for classification
    features = {}
    for node in range(n):
        # Count inconsistencies at this node
        incon = sum(1 for t in range(tau)
                    if syndrome.get((node, t)) == 'inconsistent')

        # Count inconsistencies at neighbors
        nbr_incon = []
        for nbr in cell.neighbours[node]:
            ni = sum(1 for t in range(tau)
                     if syndrome.get((nbr, t)) == 'inconsistent')
            nbr_incon.append(ni)

        mean_nbr_incon = np.mean(nbr_incon) if nbr_incon else 0.0
        coordination = cell.coordination[node]
        is_boundary = coordination < 6  # Full Eisenstein coordination is 6

        # Isolation score: high self-evidence, quiet neighbors = isolated error
        # This is the T75 signature: structured, not spreading randomly
        isolation = (incon / max(tau, 1)) - mean_nbr_incon / max(tau, 1)

        # Z3 consistency: does the node's error pattern respect Z3 symmetry?
        # On an Eisenstein lattice, chirality alternates. If a node's syndrome
        # is consistent with its chirality class, it may be a ternary transition
        chirality = cell.chirality[node]

        features[node] = {
            'incon': incon,
            'mean_nbr_incon': mean_nbr_incon,
            'coordination': coordination,
            'is_boundary': is_boundary,
            'isolation': isolation,
            'chirality': chirality,
            'syndrome_density': incon / max(tau, 1),
        }

    return syndrome, features


# ============================================================================
# DECODER 1: STANDARD BINARY (Poisson assumption)
# ============================================================================

class StandardBinaryDecoder:
    """
    Standard majority-vote decoder. Treats ALL syndrome activations as
    errors to be corrected. This is what IBM runs.
    """
    def decode(self, cell, code, assignment, syndrome, tau):
        predictions = {}
        for node in range(cell.num_nodes):
            incon = sum(1 for t in range(tau)
                        if syndrome.get((node, t)) == 'inconsistent')
            if incon > tau / 2:
                predictions[node] = code.absent_gate(
                    assignment[node], cell.chirality[node], 0)
        return predictions


# ============================================================================
# DECODER 2: CORRELATED BINARY (better priors, still corrects everything)
# ============================================================================

class CorrelatedBinaryDecoder:
    """
    Edge-correlated decoder from v2. Uses anti-bunching priors but still
    treats every flagged node as an error to correct. This is the "better
    binary decoder" — the baseline improvement from accounting for
    cooperative structure while still assuming binary basis.
    """
    def __init__(self, fano=TARGET_FANO, adj_corr=TARGET_ADJ_CORR):
        self.fano = fano
        self.adj_corr = adj_corr

    def decode(self, cell, code, assignment, syndrome, tau):
        n = cell.num_nodes
        raw = np.zeros(n)
        for node in range(n):
            for t in range(tau):
                s = syndrome.get((node, t))
                if s == 'inconsistent':
                    raw[node] += 1.0
                elif s is None:
                    raw[node] += 0.3
        raw /= max(tau, 1)

        edge_support = np.zeros(n)
        for i, j in cell.edges:
            joint = raw[i] * raw[j]
            edge_support[i] += joint
            edge_support[j] += joint
        degree = np.array([max(len(cell.neighbours[i]), 1) for i in range(n)],
                          dtype=float)
        edge_support /= degree

        belief = raw.copy()
        for _ in range(3):
            new_belief = raw.copy()
            for node in range(n):
                nbrs = cell.neighbours[node]
                if nbrs:
                    nbr_flagged = sum(1 for nb in nbrs if belief[nb] > 0.5)
                    avg_nbr = np.mean([belief[nb] for nb in nbrs])
                    if nbr_flagged > 0:
                        new_belief[node] *= self.fano ** nbr_flagged
                    if raw[node] > 0.5 and avg_nbr < 0.3:
                        new_belief[node] *= 1.0 + (1.0 - self.fano)
                new_belief[node] += edge_support[node] * 0.1
            belief = new_belief

        syndrome_density = np.mean(raw)
        expected = max(1, n * syndrome_density * self.fano)
        candidates = sorted(range(n), key=lambda i: -belief[i])
        predictions = {}
        for node in candidates:
            if belief[node] <= 0.4:
                break
            if len(predictions) >= expected * 1.5:
                break
            predictions[node] = code.absent_gate(
                assignment[node], cell.chirality[node], 0)
        return predictions


# ============================================================================
# DECODER 3: REGIME CLASSIFIER (the paradigm shift)
# ============================================================================

class RegimeClassifierDecoder:
    """
    THE KEY DECODER: Classifies nodes before correcting.

    For each node with syndrome activation:
      1. Compute local features (isolation, coordination, neighbor pattern)
      2. Classify as B31 (binary noise) or T75 (ternary transition)
      3. ONLY correct B31-classified nodes
      4. T75-classified nodes are LEFT ALONE — their "error" is signal

    Classification criteria for T75 (ternary):
      - ISOLATED: Node has syndrome activation but neighbors are quiet
        (anti-bunched pattern — the Z3 structure spaces events apart)
      - BOUNDARY: Reduced coordination gives more degrees of freedom
      - CONSISTENT: Error pattern matches chirality class expectations

    Classification criteria for B31 (binary noise):
      - CLUSTERED: Multiple adjacent nodes activated simultaneously
        (looks like random noise spreading, not structured transition)
      - INTERIOR: Full coordination constrains node to binary behavior
      - INCONSISTENT: Error pattern doesn't match Z3 structure
    """

    def __init__(self, fano=TARGET_FANO, adj_corr=TARGET_ADJ_CORR,
                 ternary_threshold=0.5):
        self.fano = fano
        self.adj_corr = adj_corr
        self.ternary_threshold = ternary_threshold  # Classification boundary

    def classify_node(self, node, features, cell):
        """
        Compute ternary probability for a node.
        Returns: float in [0, 1], where > threshold → T75 (don't correct).
        """
        f = features[node]

        if f['incon'] == 0:
            return 0.0  # No syndrome → nothing to classify

        score = 0.0

        # Feature 1: ISOLATION (strongest signal)
        # Anti-bunching means errors are spaced apart. A node with high
        # self-evidence but quiet neighbors is exhibiting the structured
        # pattern. This is the sub-Poissonian signature at the node level.
        if f['isolation'] > ISOLATION_THRESHOLD:
            score += 0.4  # Strong ternary indicator

        # Feature 2: BOUNDARY STATUS
        # Reduced coordination = more degrees of freedom = more likely
        # to express ternary structure. Interior nodes are locked binary
        # by their 6 fully-coordinated neighbors.
        if f['is_boundary']:
            score += 0.2

        # Feature 3: NEIGHBOR QUIESCENCE
        # If this node's syndrome is strong but neighbors are clean,
        # this is NOT spreading noise — it's a localized transition.
        # Random Poisson errors would occasionally hit neighbors too.
        if f['mean_nbr_incon'] < 0.5 and f['syndrome_density'] > 0.5:
            score += 0.2

        # Feature 4: COORDINATION-WEIGHTED DENSITY
        # At low coordination, even moderate syndrome evidence suggests
        # ternary transition (fewer neighbors to confirm binary basis)
        coord_factor = max(0, (6 - f['coordination']) / 6.0)
        score += 0.1 * coord_factor * f['syndrome_density']

        # Feature 5: CHIRALITY CONSISTENCY (Z3 structure)
        # On Eisenstein lattice, chirality classes have specific roles.
        # Chirality 0 (B31 ground state) is most likely binary.
        # Non-zero chirality nodes have ternary degree of freedom.
        if f['chirality'] != 0:
            score += 0.1

        return min(score, 1.0)

    def decode(self, cell, code, assignment, syndrome, features, tau):
        """
        Regime-aware decoding:
        1. For each flagged node, classify as B31 or T75
        2. Only correct B31-classified nodes
        3. Return classification alongside predictions
        """
        n = cell.num_nodes
        predictions = {}
        classifications = {}

        for node in range(n):
            incon = sum(1 for t in range(tau)
                        if syndrome.get((node, t)) == 'inconsistent')

            if incon <= tau / 2:
                classifications[node] = ('below_threshold', 0.0)
                continue

            # This node would be flagged by standard decoder.
            # Now classify: is this a binary error or ternary transition?
            ternary_prob = self.classify_node(node, features, cell)

            if ternary_prob >= self.ternary_threshold:
                # T75: DON'T CORRECT. This "error" is a ternary transition.
                classifications[node] = ('T75', ternary_prob)
                # We deliberately do NOT add to predictions
            else:
                # B31: Standard binary error. Correct normally.
                classifications[node] = ('B31', ternary_prob)
                predictions[node] = code.absent_gate(
                    assignment[node], cell.chirality[node], 0)

        return predictions, classifications


# ============================================================================
# EVALUATION ENGINE
# ============================================================================

def evaluate_three_decoders(cell, code, error_model, p_values,
                            n_trials, n_assignments, seed, tau,
                            ternary_thresholds=[0.3, 0.5, 0.7]):
    """
    Head-to-head comparison of three decoders:
      1. Standard binary (majority vote)
      2. Correlated binary (anti-bunching priors)
      3. Regime classifier (classify then correct)

    For the regime classifier, sweep over classification thresholds
    to find the optimal operating point.
    """
    rng = np.random.default_rng(seed)
    standard = StandardBinaryDecoder()
    correlated = CorrelatedBinaryDecoder()

    assignments, _ = code.find_valid_assignments(rng, n_assignments)
    if not assignments:
        return {}

    trials_per = max(1, n_trials // len(assignments))
    results = {}

    for p in p_values:
        # Counters for each decoder
        std_fail = 0
        cor_fail = 0
        regime_fails = {t: 0 for t in ternary_thresholds}

        # Classification statistics
        total_flagged = 0
        total_classified_t75 = {t: 0 for t in ternary_thresholds}
        total_t75_actually_error = {t: 0 for t in ternary_thresholds}
        total_t75_not_error = {t: 0 for t in ternary_thresholds}

        # Pairwise comparison (standard vs best regime)
        std_only = {t: 0 for t in ternary_thresholds}
        regime_only = {t: 0 for t in ternary_thresholds}

        total = 0

        for assign in assignments:
            for _ in range(trials_per):
                errors = error_model.generate_errors(cell, p, rng)
                syndrome, features = collect_rich_syndrome(
                    cell, code, assign, errors, tau)

                # Decoder 1: Standard binary
                std_pred = standard.decode(cell, code, assign, syndrome, tau)
                actual = set(errors.items())
                std_wrong = len(actual.symmetric_difference(set(std_pred.items()))) > 0
                if std_wrong:
                    std_fail += 1

                # Decoder 2: Correlated binary
                cor_pred = correlated.decode(cell, code, assign, syndrome, tau)
                cor_wrong = len(actual.symmetric_difference(set(cor_pred.items()))) > 0
                if cor_wrong:
                    cor_fail += 1

                # Decoder 3: Regime classifier (at each threshold)
                for thresh in ternary_thresholds:
                    regime = RegimeClassifierDecoder(ternary_threshold=thresh)
                    reg_pred, classifications = regime.decode(
                        cell, code, assign, syndrome, features, tau)

                    reg_wrong = len(actual.symmetric_difference(
                        set(reg_pred.items()))) > 0
                    if reg_wrong:
                        regime_fails[thresh] += 1

                    # Track classification accuracy
                    for node, (label, prob) in classifications.items():
                        if label == 'T75':
                            total_classified_t75[thresh] += 1
                            if node in errors:
                                total_t75_actually_error[thresh] += 1
                            else:
                                total_t75_not_error[thresh] += 1
                        elif label == 'B31':
                            total_flagged += 1  # only count once

                    # Pairwise: standard vs regime
                    if std_wrong and not reg_wrong:
                        std_only[thresh] += 1
                    if reg_wrong and not std_wrong:
                        regime_only[thresh] += 1

                total += 1

        # Compute metrics for each threshold
        thresh_results = {}
        for thresh in ternary_thresholds:
            imp_vs_std = (std_fail - regime_fails[thresh]) / max(1, std_fail) * 100
            imp_vs_cor = (cor_fail - regime_fails[thresh]) / max(1, cor_fail) * 100

            # McNemar test: standard vs regime
            disc = std_only[thresh] + regime_only[thresh]
            if disc > 0:
                chi2_val = (std_only[thresh] - regime_only[thresh])**2 / disc
                pval = 1.0 - chi2_dist.cdf(chi2_val, df=1)
            else:
                pval = 1.0

            # Classification accuracy: when we call something T75 and DON'T
            # correct it, how often was it actually NOT an error?
            t75_total = total_classified_t75[thresh]
            if t75_total > 0:
                t75_correct_rate = total_t75_not_error[thresh] / t75_total
                t75_error_rate = total_t75_actually_error[thresh] / t75_total
            else:
                t75_correct_rate = 0.0
                t75_error_rate = 0.0

            thresh_results[thresh] = {
                'regime_LER': regime_fails[thresh] / total,
                'improvement_vs_standard': imp_vs_std,
                'improvement_vs_correlated': imp_vs_cor,
                'p_value': pval,
                'std_only_fail': std_only[thresh],
                'regime_only_fail': regime_only[thresh],
                'n_classified_t75': t75_total,
                't75_correct_abstain': t75_correct_rate,  # Correctly didn't correct
                't75_missed_error': t75_error_rate,       # Missed a real error
            }

        results[p] = {
            'standard_LER': std_fail / total,
            'correlated_LER': cor_fail / total,
            'regime': thresh_results,
            'total': total,
        }

    return results


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 72)
    print("REGIME CLASSIFIER DECODER")
    print("'Stop Correcting What Isn't Broken'")
    print("=" * 72)
    print(f"\nHardware priors: Fano={TARGET_FANO}, adj_corr={TARGET_ADJ_CORR}")
    print(f"Ternary fraction (1-Fano): {TERNARY_FRACTION:.1%}")
    print(f"Classification thresholds: [0.3, 0.5, 0.7]")
    print()

    P_VALUES = [1e-3, 1e-2, 1e-1]
    THRESHOLDS = [0.3, 0.5, 0.7]

    # Calibrate error model
    print("--- CALIBRATING ERROR MODEL on 19-node cell ---")
    cal_cell = EisensteinCell(2)
    error_model = EdgeCorrelatedErrorModel()
    t0 = perf_counter()
    fano, adj, mc = error_model.calibrate(cal_cell, p_ref=0.01, n_samples=3000)
    dt = perf_counter() - t0
    print(f"  Time: {dt:.0f}s")
    print(f"  Achieved: Fano={fano:.4f}, adj_corr={adj:.4f}")
    print(f"  Params: edge_prob={error_model.edge_prob:.3f}, "
          f"coupling={error_model.coupling:.3f}, "
          f"antibunch={error_model.antibunch:.3f}")

    # Test configurations
    configs = {
        1: (4000, 40),
        2: (3000, 30),
        3: (2000, 25),
        4: (1500, 20),
    }

    all_results = {}

    for radius, (n_trials, n_assign) in configs.items():
        cell = EisensteinCell(radius)
        code = DynamicPentachoricCode(cell)
        n_nodes = cell.num_nodes

        # Count boundary vs interior
        n_boundary = sum(1 for i in range(n_nodes)
                         if cell.coordination[i] < 6)
        n_interior = n_nodes - n_boundary

        print(f"\n{'='*72}")
        print(f"{n_nodes}-NODE CELL (radius {radius})")
        print(f"  Interior (B31-locked): {n_interior}  |  "
              f"Boundary (T75-candidate): {n_boundary}  |  "
              f"Boundary fraction: {n_boundary/n_nodes:.1%}")
        print(f"{'='*72}")

        for tau, label in [(TAU_B31, "tau=1 (REAL QUBITS)"),
                           (TAU_T75, "tau=5 (MERKABIT)")]:
            print(f"\n  --- {label} ---")
            t0 = perf_counter()
            results = evaluate_three_decoders(
                cell, code, error_model, P_VALUES,
                n_trials, n_assign, seed=42+radius+tau, tau=tau,
                ternary_thresholds=THRESHOLDS)
            dt = perf_counter() - t0
            print(f"  ({dt:.1f}s)")

            for p in P_VALUES:
                r = results[p]
                print(f"\n  p = {p:.0e}  (N={r['total']})")
                print(f"    Standard binary LER:   {r['standard_LER']:.4f}")
                print(f"    Correlated binary LER: {r['correlated_LER']:.4f}")

                # Find best regime threshold
                best_thresh = min(THRESHOLDS,
                                  key=lambda t: r['regime'][t]['regime_LER'])
                best = r['regime'][best_thresh]

                print(f"    Regime classifier LER: {best['regime_LER']:.4f} "
                      f"(threshold={best_thresh})")
                print(f"    ┌─ vs Standard:   {best['improvement_vs_standard']:+.1f}%  "
                      f"p={best['p_value']:.4f}"
                      f"{'*' if best['p_value'] < 0.05 else ''}")
                print(f"    └─ vs Correlated: {best['improvement_vs_correlated']:+.1f}%")

                if best['n_classified_t75'] > 0:
                    print(f"    Classification: {best['n_classified_t75']} nodes → T75")
                    print(f"      Correct abstain (not real error): "
                          f"{best['t75_correct_abstain']:.1%}")
                    print(f"      Missed error (real error, didn't correct): "
                          f"{best['t75_missed_error']:.1%}")

                # Show all thresholds
                print(f"\n    {'Threshold':>9s}  {'LER':>8s}  {'vs Std':>8s}  "
                      f"{'vs Corr':>8s}  {'p-val':>8s}  {'N_T75':>6s}  "
                      f"{'Correct':>8s}")
                for t in THRESHOLDS:
                    tr = r['regime'][t]
                    sig = '*' if tr['p_value'] < 0.05 else ' '
                    print(f"    {t:9.1f}  {tr['regime_LER']:8.4f}  "
                          f"{tr['improvement_vs_standard']:+7.1f}%  "
                          f"{tr['improvement_vs_correlated']:+7.1f}%  "
                          f"{tr['p_value']:8.4f}{sig} "
                          f"{tr['n_classified_t75']:6d}  "
                          f"{tr['t75_correct_abstain']:7.1%}")

            all_results[(radius, tau)] = results

    # ====================================================================
    # SUMMARY TABLE
    # ====================================================================
    print(f"\n{'='*72}")
    print("SUMMARY: BEST REGIME CLASSIFIER vs STANDARD BINARY")
    print(f"{'='*72}")
    print(f"\n{'Nodes':>5s} {'tau':>3s} | {'Std LER':>8s} {'Cor LER':>8s} "
          f"{'Reg LER':>8s} | {'vs Std':>8s} {'vs Cor':>8s} | "
          f"{'p-val':>8s} {'N_T75':>6s} {'Abstain%':>8s}")
    print("-" * 90)

    for (radius, tau), results in sorted(all_results.items()):
        p = 1e-2  # Reference error rate
        if p not in results:
            continue
        r = results[p]
        best_thresh = min(THRESHOLDS,
                          key=lambda t: r['regime'][t]['regime_LER'])
        best = r['regime'][best_thresh]
        cell = EisensteinCell(radius)
        sig = '*' if best['p_value'] < 0.05 else ' '
        print(f"{cell.num_nodes:5d} {tau:3d} | "
              f"{r['standard_LER']:8.4f} {r['correlated_LER']:8.4f} "
              f"{best['regime_LER']:8.4f} | "
              f"{best['improvement_vs_standard']:+7.1f}% "
              f"{best['improvement_vs_correlated']:+7.1f}% | "
              f"{best['p_value']:8.4f}{sig}"
              f"{best['n_classified_t75']:6d} "
              f"{best['t75_correct_abstain']:7.1%}")

    # ====================================================================
    # THE KEY QUESTION
    # ====================================================================
    print(f"\n{'='*72}")
    print("THE PARADIGM TEST")
    print(f"{'='*72}")
    print("""
    If Regime LER < Standard LER:
      → Standard QEC is DESTROYING information by correcting valid states
      → The "errors" it corrects include ternary transitions
      → LESS correction = BETTER performance

    If Regime LER ≈ Standard LER:
      → Classification is neutral — ternary transitions don't affect LER
      → The structure is real but doesn't help or hurt

    If Regime LER > Standard LER:
      → The classifier is missing real errors
      → Ternary hypothesis not supported at this threshold
      → But check: does the classifier's "Correct Abstain" rate show
        that SOME abstentions were correct? If so, the signal exists
        but the threshold needs tuning.
    """)

    # Check: at the best threshold, what fraction of abstentions were correct?
    print("ABSTENTION ACCURACY (at p=1e-2, tau=1):")
    for radius in range(1, 5):
        key = (radius, TAU_B31)
        if key not in all_results:
            continue
        r = all_results[key][1e-2]
        cell = EisensteinCell(radius)
        for t in THRESHOLDS:
            tr = r['regime'][t]
            if tr['n_classified_t75'] > 0:
                print(f"  {cell.num_nodes:3d} nodes, thresh={t}: "
                      f"{tr['n_classified_t75']:4d} abstained, "
                      f"{tr['t75_correct_abstain']:.1%} correctly "
                      f"(were NOT real errors)")

    print("\nDone.")


if __name__ == '__main__':
    main()
