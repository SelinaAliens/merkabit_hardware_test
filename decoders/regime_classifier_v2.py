#!/usr/bin/env python3
"""
REGIME CLASSIFIER v2 -- Mixed Binary/Ternary Error Model
=========================================================

Paper 3: The Rotation Gap Is Not An Error

KEY FIX from v1: The previous simulation was purely binary — every
syndrome activation was a real error. There were no ternary transitions
to correctly abstain from, so the classifier had 0% correct abstain rate.

This version introduces the MIXED MODEL:

  Each syndrome activation has two possible causes:
    1. BINARY ERROR (probability 1 - f_ternary):
       Real error. Should be corrected. Correcting it fixes the state.
    2. TERNARY TRANSITION (probability f_ternary):
       Structured transition. Should NOT be corrected.
       If a decoder "corrects" a ternary transition, it INTRODUCES an error.

  f_ternary = 1 - Fano = 0.144 (from IBM hardware)

This models what the hardware data tells us: 14.4% of syndrome events
are not random noise but structured cooperative transitions. A standard
decoder that corrects everything will miscorrect those 14.4%, introducing
errors that wouldn't exist if it had left them alone.

The paradigm test:
  - Standard decoder corrects everything → miscorrects ternary transitions
  - Regime classifier identifies ternary transitions → leaves them alone
  - If classifier wins, standard QEC is destroying information

Selina Stenberg with Claude Anthropic
"""

import sys
import numpy as np
from time import perf_counter
from scipy.stats import chi2 as chi2_dist

sys.path.insert(0, r"C:\Users\selin\OneDrive\Desktop\Code")
from lattice_scaling_simulation import EisensteinCell, DynamicPentachoricCode, NUM_GATES

# ============================================================================
# HARDWARE-MEASURED CONSTANTS
# ============================================================================

TARGET_FANO = 0.856
TARGET_ADJ_CORR = 0.074
F_TERNARY = 1.0 - TARGET_FANO   # 0.144: fraction of events that are ternary
TAU_B31 = 1
TAU_T75 = 5


# ============================================================================
# MIXED ERROR MODEL
# ============================================================================

class MixedErrorModel:
    """
    Generates TWO types of syndrome events:

    1. Binary errors: Real gate errors. Random, Poisson-distributed.
       When corrected → error is fixed (good).
       When not corrected → error persists (bad).

    2. Ternary transitions: Structured, anti-bunched, boundary-favoring.
       When corrected → correction INTRODUCES an error (bad).
       When not corrected → state is fine (good).

    The mix produces sub-Poissonian statistics because ternary transitions
    are anti-bunched (structured, not random), reducing the overall count
    variance below Poisson.
    """

    def __init__(self, f_ternary=F_TERNARY):
        self.f_ternary = f_ternary
        # Edge-mediated parameters (for anti-bunching of ternary events)
        self.edge_prob = 0.3
        self.coupling = 0.5
        self.antibunch = 0.15

    def generate_events(self, cell, p_phys, rng):
        """
        Returns:
          binary_errors: dict {node: gate} — real errors, should be corrected
          ternary_transitions: dict {node: gate} — structured events,
                               should NOT be corrected
          all_syndrome: dict {node: gate} — union (what the decoder sees)

        The decoder sees all_syndrome but doesn't know which are binary
        and which are ternary. The classifier's job is to figure this out.
        """
        n = cell.num_nodes

        # --- Generate binary errors (standard Poisson) ---
        p_binary = p_phys * (1.0 - self.f_ternary)
        binary_errors = {}
        for i in range(n):
            if rng.random() < p_binary:
                binary_errors[i] = int(rng.integers(0, NUM_GATES))

        # --- Generate ternary transitions (structured, anti-bunched) ---
        # Ternary transitions favor boundary nodes (reduced coordination)
        # and are anti-bunched (isolated, not clustered)
        p_ternary_base = p_phys * self.f_ternary

        # Boundary nodes get HIGHER ternary probability
        # Interior nodes get LOWER ternary probability
        # This models: reduced coordination → more freedom → ternary expression
        ternary_transitions = {}
        for i in range(n):
            coord = cell.coordination[i]
            # Boundary enhancement: nodes with < 6 neighbors are 2x more
            # likely to undergo ternary transition
            if coord < 6:
                p_t = p_ternary_base * (1.0 + (6 - coord) / 6.0)
            else:
                p_t = p_ternary_base * 0.5  # Interior: suppressed

            # Anti-bunching: if a neighbor already has a ternary transition,
            # this node is LESS likely to also transition
            # (the Z3 structure spaces events apart)
            for nbr in cell.neighbours[i]:
                if nbr in ternary_transitions:
                    p_t *= (1.0 - self.antibunch)

            if i not in binary_errors and rng.random() < p_t:
                ternary_transitions[i] = int(rng.integers(0, NUM_GATES))

        # Union: what the decoder sees (can't tell which is which)
        all_syndrome = {}
        all_syndrome.update(binary_errors)
        all_syndrome.update(ternary_transitions)
        # Note: if same node has both (extremely rare), binary takes priority

        return binary_errors, ternary_transitions, all_syndrome

    def measure_stats(self, cell, p_phys, rng, n_samples=3000):
        """Measure Fano factor and adjacent correlation of the mixed model."""
        counts = []
        adj_same = 0
        adj_total = 0

        for _ in range(n_samples):
            _, _, all_syn = self.generate_events(cell, p_phys, rng)
            counts.append(len(all_syn))
            synset = set(all_syn.keys())
            for i, j in cell.edges:
                ei = 1 if i in synset else 0
                ej = 1 if j in synset else 0
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


# ============================================================================
# SYNDROME COLLECTION
# ============================================================================

def collect_syndrome(cell, code, assignment, events, tau):
    """Collect syndrome from whatever events the decoder can see."""
    syndrome = {}
    for t in range(tau):
        for node in range(cell.num_nodes):
            absent = code.absent_gate(assignment[node], cell.chirality[node], t)
            if node in events and events[node] == absent:
                syndrome[(node, t)] = None
            elif node in events:
                syndrome[(node, t)] = 'inconsistent'
            else:
                syndrome[(node, t)] = absent
    return syndrome


# ============================================================================
# DECODER 1: STANDARD BINARY (corrects everything)
# ============================================================================

class StandardDecoder:
    """Majority vote. Corrects every flagged node. Doesn't know about ternary."""

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
# DECODER 2: REGIME CLASSIFIER (classifies then corrects)
# ============================================================================

class RegimeClassifier:
    """
    Classifies each flagged node as binary (correct it) or ternary
    (leave it alone). Uses structural features visible in the syndrome.
    """

    def __init__(self, ternary_threshold=0.5):
        self.threshold = ternary_threshold

    def classify(self, node, cell, syndrome, tau):
        """
        Compute ternary probability based on syndrome features.

        Key signals that a node is undergoing ternary transition:
        1. ISOLATION: Syndrome activity at this node, neighbors quiet
        2. BOUNDARY: Reduced coordination (more degrees of freedom)
        3. TEMPORAL COHERENCE: Consistent syndrome across time steps
           (ternary transitions are persistent; random errors are sporadic)
        """
        # Self evidence
        incon = sum(1 for t in range(tau)
                    if syndrome.get((node, t)) == 'inconsistent')
        if incon == 0:
            return 0.0

        density = incon / max(tau, 1)

        # Neighbor evidence
        nbr_incon = []
        for nbr in cell.neighbours[node]:
            ni = sum(1 for t in range(tau)
                     if syndrome.get((nbr, t)) == 'inconsistent')
            nbr_incon.append(ni)

        mean_nbr = np.mean(nbr_incon) if nbr_incon else 0.0
        max_nbr = max(nbr_incon) if nbr_incon else 0.0

        score = 0.0

        # Feature 1: ISOLATION (strongest)
        # Anti-bunched events are isolated. If this node is active
        # but ALL neighbors are quiet, this looks ternary.
        if max_nbr == 0 and density > 0:
            score += 0.35

        # Feature 2: BOUNDARY
        coordination = cell.coordination[node]
        if coordination < 6:
            boundary_weight = (6 - coordination) / 6.0
            score += 0.25 * boundary_weight

        # Feature 3: DENSITY vs NEIGHBORS
        # Ternary: strong self-signal, weak neighbor signal
        # Binary: signal spreads to neighbors too
        if density > 0.5 and mean_nbr < density * 0.3:
            score += 0.2

        # Feature 4: CHIRALITY
        # Non-zero chirality nodes have the ternary degree of freedom
        chirality = cell.chirality[node]
        if chirality != 0:
            score += 0.1

        # Feature 5: TEMPORAL CONSISTENCY
        # Ternary transitions persist across time steps (structured)
        # Random errors are sporadic
        if tau > 1:
            # Check if the syndrome pattern is consistent across time
            pattern = [syndrome.get((node, t)) for t in range(tau)]
            n_incon = sum(1 for p in pattern if p == 'inconsistent')
            # High consistency = same pattern repeats = structured
            if n_incon == tau:  # Active at every time step
                score += 0.1
            elif n_incon >= tau * 0.8:
                score += 0.05

        return min(score, 1.0)

    def decode(self, cell, code, assignment, syndrome, tau):
        """
        Classify-then-correct:
        1. Flag nodes by majority vote (same detection as standard)
        2. For each flagged node, classify as binary or ternary
        3. Only correct binary-classified nodes
        """
        predictions = {}
        classifications = {}

        for node in range(cell.num_nodes):
            incon = sum(1 for t in range(tau)
                        if syndrome.get((node, t)) == 'inconsistent')

            if incon <= tau / 2:
                continue  # Not flagged, skip

            # This node IS flagged. Now classify.
            ternary_prob = self.classify(node, cell, syndrome, tau)

            if ternary_prob >= self.threshold:
                classifications[node] = ('T75', ternary_prob)
                # DON'T correct — leave it alone
            else:
                classifications[node] = ('B31', ternary_prob)
                predictions[node] = code.absent_gate(
                    assignment[node], cell.chirality[node], 0)

        return predictions, classifications


# ============================================================================
# EVALUATION
# ============================================================================

def evaluate(cell, code, model, p_values, n_trials, n_assignments,
             seed, tau, thresholds=[0.3, 0.5, 0.7]):
    """
    The real test. For each trial:
    1. Generate mixed events (binary errors + ternary transitions)
    2. Run standard decoder (corrects everything)
    3. Run regime classifier (classifies, then selectively corrects)
    4. Score: a trial is "failed" if the final state has any uncorrected
       binary errors OR any miscorrected ternary transitions.

    Standard decoder failure modes:
      - Misses a binary error (same as any decoder)
      - "Corrects" a ternary transition → introduces error

    Regime classifier failure modes:
      - Misses a binary error (if classified as T75)
      - Correctly abstains from ternary transition (success!)
      - Fails to identify ternary → corrects it → introduces error
    """
    rng = np.random.default_rng(seed)
    standard = StandardDecoder()

    assignments, _ = code.find_valid_assignments(rng, n_assignments)
    if not assignments:
        return {}

    trials_per = max(1, n_trials // len(assignments))
    results = {}

    for p in p_values:
        std_fail = 0
        regime_fails = {t: 0 for t in thresholds}

        # Detailed stats
        std_miscorrect_ternary = 0    # Standard corrects a ternary event
        std_miss_binary = 0            # Standard misses a binary error

        regime_stats = {t: {
            'correct_abstain': 0,      # Correctly left ternary alone
            'missed_binary': 0,        # Classified binary error as T75
            'correct_correct': 0,      # Correctly corrected binary error
            'miscorrect_ternary': 0,   # Failed to identify ternary, corrected it
            'n_ternary_seen': 0,       # Total ternary events in syndrome
            'n_binary_seen': 0,        # Total binary errors in syndrome
        } for t in thresholds}

        # Pairwise comparison
        std_only = {t: 0 for t in thresholds}
        reg_only = {t: 0 for t in thresholds}

        total = 0

        for assign in assignments:
            for _ in range(trials_per):
                binary_errors, ternary_trans, all_events = \
                    model.generate_events(cell, p, rng)

                syndrome = collect_syndrome(cell, code, assign, all_events, tau)

                # === STANDARD DECODER ===
                std_pred = standard.decode(cell, code, assign, syndrome, tau)

                # Standard decoder fails if:
                # 1. It missed a binary error (binary error not in predictions)
                # 2. It "corrected" a ternary transition (ternary node in predictions)
                #    This INTRODUCES an error on a node that was fine

                std_residual_errors = set()

                # Binary errors not corrected
                for node, gate in binary_errors.items():
                    if node not in std_pred or std_pred[node] != gate:
                        std_residual_errors.add(node)
                    # If correctly predicted, error is fixed

                # Ternary transitions that were "corrected" — introduces error
                for node, gate in ternary_trans.items():
                    if node in std_pred:
                        std_residual_errors.add(node)
                        std_miscorrect_ternary += 1

                std_wrong = len(std_residual_errors) > 0
                if std_wrong:
                    std_fail += 1

                # Count what standard missed
                for node in binary_errors:
                    if node not in std_pred:
                        std_miss_binary += 1

                # === REGIME CLASSIFIER ===
                for thresh in thresholds:
                    classifier = RegimeClassifier(ternary_threshold=thresh)
                    reg_pred, classifications = classifier.decode(
                        cell, code, assign, syndrome, tau)

                    reg_residual = set()

                    # Binary errors: check if corrected
                    for node, gate in binary_errors.items():
                        if node not in reg_pred or reg_pred[node] != gate:
                            reg_residual.add(node)
                            # Was it classified as T75? (missed binary)
                            if node in classifications and \
                               classifications[node][0] == 'T75':
                                regime_stats[thresh]['missed_binary'] += 1
                        else:
                            regime_stats[thresh]['correct_correct'] += 1

                    # Ternary transitions: check if left alone
                    for node, gate in ternary_trans.items():
                        regime_stats[thresh]['n_ternary_seen'] += 1
                        if node in reg_pred:
                            # Classifier failed to identify, corrected it
                            reg_residual.add(node)
                            regime_stats[thresh]['miscorrect_ternary'] += 1
                        else:
                            # Correctly abstained!
                            if node in classifications and \
                               classifications[node][0] == 'T75':
                                regime_stats[thresh]['correct_abstain'] += 1
                            # Note: could also be that the node wasn't flagged
                            # at all (incon <= tau/2), which is also correct

                    regime_stats[thresh]['n_binary_seen'] += len(binary_errors)

                    reg_wrong = len(reg_residual) > 0
                    if reg_wrong:
                        regime_fails[thresh] += 1

                    if std_wrong and not reg_wrong:
                        std_only[thresh] += 1
                    if reg_wrong and not std_wrong:
                        reg_only[thresh] += 1

                total += 1

        # Compute metrics
        thresh_results = {}
        for thresh in thresholds:
            imp = (std_fail - regime_fails[thresh]) / max(1, std_fail) * 100

            disc = std_only[thresh] + reg_only[thresh]
            if disc > 0:
                chi2_val = (std_only[thresh] - reg_only[thresh])**2 / disc
                pval = 1.0 - chi2_dist.cdf(chi2_val, df=1)
            else:
                pval = 1.0

            rs = regime_stats[thresh]
            n_tern = max(rs['n_ternary_seen'], 1)
            n_bin = max(rs['n_binary_seen'], 1)

            thresh_results[thresh] = {
                'LER': regime_fails[thresh] / total,
                'improvement': imp,
                'p_value': pval,
                'std_only': std_only[thresh],
                'reg_only': reg_only[thresh],
                # Classification accuracy
                'correct_abstain': rs['correct_abstain'],
                'missed_binary': rs['missed_binary'],
                'correct_correct': rs['correct_correct'],
                'miscorrect_ternary': rs['miscorrect_ternary'],
                'abstain_rate': rs['correct_abstain'] / n_tern,
                'binary_miss_rate': rs['missed_binary'] / n_bin,
            }

        results[p] = {
            'standard_LER': std_fail / total,
            'std_miscorrect_ternary': std_miscorrect_ternary,
            'std_miss_binary': std_miss_binary,
            'regime': thresh_results,
            'total': total,
        }

    return results


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 72)
    print("REGIME CLASSIFIER v2 -- Mixed Binary/Ternary Model")
    print("'Stop Correcting What Isn't Broken'")
    print("=" * 72)
    print(f"\n  Fano = {TARGET_FANO} → ternary fraction = {F_TERNARY:.1%}")
    print(f"  Model: {100*(1-F_TERNARY):.1f}% of syndrome events are binary errors")
    print(f"         {100*F_TERNARY:.1f}% are ternary transitions (correcting = BAD)")
    print()

    P_VALUES = [1e-3, 1e-2, 1e-1]
    THRESHOLDS = [0.3, 0.4, 0.5, 0.6, 0.7]

    # Verify mixed model produces reasonable statistics
    print("--- MIXED MODEL VALIDATION ---")
    for radius in [1, 2, 3]:
        cell = EisensteinCell(radius)
        model = MixedErrorModel(f_ternary=F_TERNARY)
        rng = np.random.default_rng(42)
        fano, adj, mc = model.measure_stats(cell, 0.01, rng, 5000)
        n_boundary = sum(1 for i in range(cell.num_nodes) if cell.coordination[i] < 6)
        print(f"  {cell.num_nodes:3d} nodes (boundary={n_boundary}): "
              f"Fano={fano:.3f}, adj_corr={adj:.4f}, mean_events={mc:.2f}")

    # Run evaluation
    configs = {
        1: (5000, 50),
        2: (4000, 40),
        3: (3000, 30),
        4: (2000, 25),
    }

    all_results = {}
    model = MixedErrorModel(f_ternary=F_TERNARY)

    for radius, (n_trials, n_assign) in configs.items():
        cell = EisensteinCell(radius)
        code = DynamicPentachoricCode(cell)
        n_boundary = sum(1 for i in range(cell.num_nodes)
                         if cell.coordination[i] < 6)

        print(f"\n{'='*72}")
        print(f"{cell.num_nodes}-NODE CELL (radius {radius})")
        print(f"  Interior: {cell.num_nodes - n_boundary}  |  "
              f"Boundary: {n_boundary}  |  "
              f"Boundary %: {n_boundary/cell.num_nodes:.1%}")
        print(f"{'='*72}")

        for tau, label in [(TAU_B31, "tau=1 REAL QUBITS"),
                           (TAU_T75, "tau=5 MERKABIT")]:
            print(f"\n  --- {label} ---")
            t0 = perf_counter()
            results = evaluate(cell, code, model, P_VALUES,
                             n_trials, n_assign,
                             seed=42+radius+tau, tau=tau,
                             thresholds=THRESHOLDS)
            dt = perf_counter() - t0
            print(f"  ({dt:.1f}s)")

            for p in P_VALUES:
                r = results[p]
                print(f"\n  p={p:.0e}  N={r['total']}")
                print(f"    Standard LER: {r['standard_LER']:.4f}")
                print(f"      ├─ Miscorrected ternary: {r['std_miscorrect_ternary']}")
                print(f"      └─ Missed binary: {r['std_miss_binary']}")

                best_thresh = min(THRESHOLDS,
                                  key=lambda t: r['regime'][t]['LER'])
                best = r['regime'][best_thresh]
                sig = '*' if best['p_value'] < 0.05 else ''

                print(f"    Best Regime LER: {best['LER']:.4f} "
                      f"(threshold={best_thresh})")
                print(f"      ├─ vs Standard: {best['improvement']:+.1f}% "
                      f"p={best['p_value']:.4f}{sig}")
                print(f"      ├─ Correct abstain (ternary left alone): "
                      f"{best['correct_abstain']}")
                print(f"      ├─ Missed binary (classified as T75): "
                      f"{best['missed_binary']}")
                print(f"      ├─ Miscorrected ternary: "
                      f"{best['miscorrect_ternary']}")
                print(f"      └─ Abstain rate (of ternary events): "
                      f"{best['abstain_rate']:.1%}")

                print(f"\n    {'Thresh':>6s}  {'LER':>7s}  {'Impr':>7s}  "
                      f"{'p-val':>8s}  {'Abst':>5s}  {'MissB':>5s}  "
                      f"{'MiscT':>5s}  {'AbstR':>6s}")
                for t in THRESHOLDS:
                    tr = r['regime'][t]
                    s = '*' if tr['p_value'] < 0.05 else ' '
                    print(f"    {t:6.1f}  {tr['LER']:7.4f}  "
                          f"{tr['improvement']:+6.1f}%  "
                          f"{tr['p_value']:8.4f}{s} "
                          f"{tr['correct_abstain']:5d}  "
                          f"{tr['missed_binary']:5d}  "
                          f"{tr['miscorrect_ternary']:5d}  "
                          f"{tr['abstain_rate']:5.1%}")

            all_results[(radius, tau)] = results

    # ====================================================================
    # SUMMARY
    # ====================================================================
    print(f"\n{'='*72}")
    print("SUMMARY at p=1e-2")
    print(f"{'='*72}")
    print(f"\n{'N':>5s} {'tau':>3s} | {'Std':>7s} {'Best':>7s} | "
          f"{'Impr':>7s} {'p-val':>8s} | "
          f"{'Abst':>5s} {'MissB':>5s} {'MiscT':>5s} | "
          f"{'AbstR':>6s}")
    print("-" * 80)

    for (radius, tau), results in sorted(all_results.items()):
        if 1e-2 not in results:
            continue
        r = results[1e-2]
        best_t = min(THRESHOLDS, key=lambda t: r['regime'][t]['LER'])
        best = r['regime'][best_t]
        cell = EisensteinCell(radius)
        sig = '*' if best['p_value'] < 0.05 else ' '
        print(f"{cell.num_nodes:5d} {tau:3d} | "
              f"{r['standard_LER']:7.4f} {best['LER']:7.4f} | "
              f"{best['improvement']:+6.1f}% {best['p_value']:8.4f}{sig}| "
              f"{best['correct_abstain']:5d} {best['missed_binary']:5d} "
              f"{best['miscorrect_ternary']:5d} | "
              f"{best['abstain_rate']:5.1%}")

    # ====================================================================
    # THE PARADIGM QUESTION
    # ====================================================================
    print(f"\n{'='*72}")
    print("THE PARADIGM QUESTION")
    print(f"{'='*72}")
    print(f"""
    Standard decoder miscorrects ternary transitions → introduces errors.
    Regime classifier identifies ternary transitions → leaves them alone.

    Key metric: CORRECT ABSTAIN count.
    Every correct abstain is a case where standard QEC would have
    INTRODUCED an error by correcting a valid ternary state.

    If improvement > 0 AND correct_abstain > 0:
      → Standard QEC IS destroying information
      → Less correction = better performance
      → The hardware has ternary structure that binary decoders damage
    """)

    # F_TERNARY sweep: how sensitive is the result?
    print(f"\n{'='*72}")
    print("SENSITIVITY: varying f_ternary")
    print(f"{'='*72}")
    cell = EisensteinCell(2)
    code = DynamicPentachoricCode(cell)
    print(f"\n  19-node cell, p=1e-2, tau=1, threshold=0.5")
    print(f"  {'f_ternary':>10s}  {'Std LER':>8s}  {'Reg LER':>8s}  "
          f"{'Impr':>7s}  {'Abstain':>7s}")

    for ft in [0.0, 0.05, 0.10, 0.144, 0.20, 0.30]:
        m = MixedErrorModel(f_ternary=ft)
        r = evaluate(cell, code, m, [1e-2], 3000, 30,
                     seed=999, tau=TAU_B31, thresholds=[0.5])
        res = r[1e-2]
        reg = res['regime'][0.5]
        print(f"  {ft:10.3f}  {res['standard_LER']:8.4f}  {reg['LER']:8.4f}  "
              f"{reg['improvement']:+6.1f}%  {reg['correct_abstain']:7d}")

    print("\nDone.")


if __name__ == '__main__':
    main()
