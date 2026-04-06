"""
Google Willow — Regime Classifier Falsification Test
=====================================================
Paper 3 predicts: the regime classifier should have ZERO effect on
super-Poissonian hardware (no ternary transitions to preserve).

Test: Apply the classifier's logic to Willow detection events.
If it still "helps," the ternary interpretation is wrong.
If it has zero/negative effect, the prediction is confirmed.

Method:
  For each Willow experiment (50,000 shots):
  1. Standard decoder: correct every detection event
  2. Regime classifier: score each detection event on isolation,
     boundary-likeness, temporal consistency. Abstain from those
     classified as "ternary."
  3. Compare: does abstention help or hurt?

  Since we don't have Willow logical error rates, we use a proxy:
  count the fraction of detection events that LOOK ternary
  (isolated, boundary-like). If the structure isn't there,
  the classifier will find nothing to abstain from.

Selina Stenberg with Claude Anthropic, April 2026
"""

import zipfile, json, sys, numpy as np
from collections import defaultdict
from scipy import stats

sys.stdout.reconfigure(encoding='utf-8')

ZIP_PATH = 'C:/Users/selin/Downloads/google_105Q_surface_code_d3_d5_d7.zip'
z = zipfile.ZipFile(ZIP_PATH)


def count_detectors(z, stim_path):
    text = z.read(stim_path).decode()
    return text.count('DETECTOR')


def read_detection_matrix(z, path, n_detectors, n_shots):
    raw = z.read(path)
    bytes_per_shot = (n_detectors + 7) // 8
    data = np.frombuffer(raw, dtype=np.uint8).reshape(n_shots, bytes_per_shot)
    matrix = np.zeros((n_shots, n_detectors), dtype=np.uint8)
    for byte_idx in range(bytes_per_shot):
        for bit in range(min(8, n_detectors - byte_idx * 8)):
            col = byte_idx * 8 + bit
            matrix[:, col] = (data[:, byte_idx] >> bit) & 1
    return matrix


def build_detector_adjacency(n_det_per_round, rounds):
    """
    Build spatial adjacency for detectors within a round.
    Surface code detectors on a grid: adjacent if index differs by 1
    or by row_width. We approximate with sequential adjacency
    (detectors i and i+1 are neighbors within the same round).
    """
    adj = defaultdict(set)
    for r in range(rounds):
        base = r * n_det_per_round
        for i in range(n_det_per_round - 1):
            adj[base + i].add(base + i + 1)
            adj[base + i + 1].add(base + i)
    return adj


def classify_detection_event(det_idx, shot_data, adj, n_det_per_round, rounds):
    """
    Score a single detection event using the regime classifier features.
    Returns a ternary score in [0, 1].

    Features (matching Paper 3 Section 5.2):
      1. Isolation (0.35): active detector with all neighbors quiet
      2. Boundary (0.25): detector at edge of the patch
      3. Density contrast (0.20): strong self, weak neighbors
      4. Temporal consistency (0.10): same detector fires across rounds
    """
    score = 0.0

    # Feature 1: ISOLATION
    neighbors = adj.get(det_idx, set())
    if neighbors:
        nbr_active = sum(shot_data[n] for n in neighbors if n < len(shot_data))
        if nbr_active == 0:
            score += 0.35
    else:
        # No neighbors = boundary-like
        score += 0.35

    # Feature 2: BOUNDARY
    # Detectors at round boundaries (first/last in each round) or
    # at spatial edges of the patch
    local_idx = det_idx % n_det_per_round
    if local_idx == 0 or local_idx == n_det_per_round - 1:
        score += 0.25

    # Feature 3: DENSITY CONTRAST
    if neighbors:
        nbr_active = sum(shot_data[n] for n in neighbors if n < len(shot_data))
        total_nbr = len([n for n in neighbors if n < len(shot_data)])
        nbr_density = nbr_active / max(total_nbr, 1)
        if nbr_density < 0.15:  # Self active, neighbors mostly quiet
            score += 0.20

    # Feature 4: TEMPORAL CONSISTENCY
    # Check if the same spatial detector fires in adjacent rounds
    round_idx = det_idx // n_det_per_round
    spatial_idx = det_idx % n_det_per_round
    temporal_hits = 0
    for r in range(max(0, round_idx - 1), min(rounds, round_idx + 2)):
        other = r * n_det_per_round + spatial_idx
        if other < len(shot_data) and shot_data[other] == 1:
            temporal_hits += 1
    if temporal_hits >= 2:  # Fires in this round AND at least one neighbor round
        score += 0.10

    return min(score, 1.0)


print("=" * 100)
print("GOOGLE WILLOW — REGIME CLASSIFIER FALSIFICATION TEST")
print("Paper 3 prediction: classifier has ZERO effect on super-Poissonian hardware")
print("=" * 100)
print()

# ══════════════════════════════════════════════════════════════
# PART 1: Classification statistics on Willow detection events
# What fraction of events LOOK ternary?
# ══════════════════════════════════════════════════════════════

print("PART 1: TERNARY CLASSIFICATION ON WILLOW DETECTION EVENTS")
print("  Threshold θ = 0.3 (same as Paper 3 Table 1)")
print()

THETA = 0.3  # Same threshold as Paper 3

target_configs = [
    (3, 'd3_at_q4_5', 8),
    (3, 'd3_at_q6_7', 8),
    (5, 'd5_at_q4_7', 24),
    (5, 'd5_at_q6_5', 24),
    (7, 'd7_at_q6_7', 48),
]

all_results = []

for d_code, patch, dpr in target_configs:
    for rr in [13, 50]:
        stim_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/circuit_ideal.stim'
        det_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/detection_events.b8'
        meta_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/metadata.json'

        try:
            n_det = count_detectors(z, stim_path)
            md = json.loads(z.read(meta_path))
            n_shots = md['shots']

            matrix = read_detection_matrix(z, det_path, n_det, n_shots)
            adj = build_detector_adjacency(dpr, rr)

            # Sample shots for speed (classifier on 50K shots × 400 detectors is slow)
            n_sample = min(5000, n_shots)
            sample_idx = np.random.default_rng(42).choice(n_shots, n_sample, replace=False)
            sample = matrix[sample_idx]

            total_events = 0
            classified_ternary = 0
            classified_binary = 0
            isolation_scores = []

            # Per-shot analysis
            shot_total_events = []
            shot_ternary_frac = []
            shot_abstain_count = []

            for s in range(n_sample):
                shot = sample[s]
                active = np.where(shot == 1)[0]
                n_ev = len(active)
                total_events += n_ev
                shot_total_events.append(n_ev)

                n_tern = 0
                for det_idx in active:
                    score = classify_detection_event(det_idx, shot, adj, dpr, rr)
                    isolation_scores.append(score)
                    if score >= THETA:
                        classified_ternary += 1
                        n_tern += 1
                    else:
                        classified_binary += 1

                shot_ternary_frac.append(n_tern / max(n_ev, 1))
                shot_abstain_count.append(n_tern)

            frac_ternary = classified_ternary / max(total_events, 1)
            mean_score = np.mean(isolation_scores) if isolation_scores else 0
            mean_shot_frac = np.mean(shot_ternary_frac)

            result = {
                'd': d_code, 'patch': patch, 'rounds': rr,
                'n_sample': n_sample,
                'total_events': total_events,
                'frac_ternary': frac_ternary,
                'mean_score': mean_score,
                'mean_shot_frac': mean_shot_frac,
                'mean_abstain': np.mean(shot_abstain_count),
            }
            all_results.append(result)

            print(f"  d={d_code}, {patch}, r={rr}: "
                  f"events={total_events}, "
                  f"classified ternary={frac_ternary:.1%}, "
                  f"mean score={mean_score:.3f}, "
                  f"per-shot abstain={np.mean(shot_abstain_count):.1f}")

        except Exception as e:
            print(f"  d={d_code}, {patch}, r={rr}: ERROR - {e}")

print()

# ══════════════════════════════════════════════════════════════
# PART 2: Compare with IBM classifier fractions
# ══════════════════════════════════════════════════════════════

print("=" * 100)
print("PART 2: COMPARISON WITH IBM CLASSIFICATION RATES")
print("=" * 100)
print()

# From Paper 3 Table 1: abstain rates on IBM-calibrated model
ibm_abstain_rates = {
    (7, 1): 0.805,
    (19, 1): 0.762,
    (37, 1): 0.766,
    (61, 1): 0.758,
}

print(f"  IBM (mixed model, f=0.144):")
for (n, tau), rate in ibm_abstain_rates.items():
    print(f"    {n}-node, tau={tau}: {rate:.1%} of flagged events classified as ternary")

print()
print(f"  Google Willow (real hardware data):")
for r in all_results:
    print(f"    d={r['d']}, {r['patch']}, r={r['rounds']}: "
          f"{r['frac_ternary']:.1%} of events classified as ternary")

print()

# ══════════════════════════════════════════════════════════════
# PART 3: Isolation analysis — are Willow events isolated?
# ══════════════════════════════════════════════════════════════

print("=" * 100)
print("PART 3: ISOLATION ANALYSIS")
print("  Key question: are detection events on Willow isolated (anti-bunched)")
print("  or clustered (bunched)? Ternary transitions should be isolated.")
print("=" * 100)
print()

for d_code, patch, dpr in [(3, 'd3_at_q4_5', 8), (5, 'd5_at_q4_7', 24), (7, 'd7_at_q6_7', 48)]:
    rr = 50
    det_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/detection_events.b8'
    meta_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/metadata.json'
    stim_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/circuit_ideal.stim'

    n_det = count_detectors(z, stim_path)
    md = json.loads(z.read(meta_path))
    n_shots = md['shots']
    matrix = read_detection_matrix(z, det_path, n_det, n_shots)
    adj = build_detector_adjacency(dpr, rr)

    n_sample = 5000
    sample = matrix[np.random.default_rng(42).choice(n_shots, n_sample, replace=False)]

    isolated_count = 0
    clustered_count = 0
    total_active = 0

    for s in range(n_sample):
        shot = sample[s]
        active = np.where(shot == 1)[0]
        for det_idx in active:
            total_active += 1
            neighbors = adj.get(det_idx, set())
            nbr_active = sum(shot[n] for n in neighbors if n < len(shot))
            if nbr_active == 0:
                isolated_count += 1
            else:
                clustered_count += 1

    frac_isolated = isolated_count / max(total_active, 1)
    frac_clustered = clustered_count / max(total_active, 1)

    print(f"  d={d_code} ({patch}), r={rr}:")
    print(f"    Total active detectors: {total_active}")
    print(f"    Isolated (no active neighbors): {frac_isolated:.1%}")
    print(f"    Clustered (1+ active neighbors): {frac_clustered:.1%}")
    print()


# ══════════════════════════════════════════════════════════════
# PART 4: Simulated LER impact
# If we abstain from correcting "ternary-classified" events on Willow,
# does it help or hurt?
# Proxy: for each shot, count events that would be "left uncorrected."
# On sub-Poissonian data (IBM), these are genuine ternary → abstaining helps.
# On super-Poissonian data (Willow), these are real errors → abstaining hurts.
# ══════════════════════════════════════════════════════════════

print("=" * 100)
print("PART 4: IMPACT OF ABSTENTION ON WILLOW")
print("  Standard decoder: correct all N events → N corrections applied")
print("  Regime classifier: correct (N - A) events → A events left uncorrected")
print("  On IBM: abstained events are ternary → fewer miscorrections → HELPS")
print("  On Willow: abstained events are real errors → more uncorrected → HURTS")
print("=" * 100)
print()

# Use obs_flips_actual to check actual logical errors
for d_code, patch, dpr in [(3, 'd3_at_q4_5', 8), (5, 'd5_at_q4_7', 24), (7, 'd7_at_q6_7', 48)]:
    rr = 50
    stim_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/circuit_ideal.stim'
    det_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/detection_events.b8'
    meta_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/metadata.json'
    obs_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/obs_flips_actual.b8'

    n_det = count_detectors(z, stim_path)
    md = json.loads(z.read(meta_path))
    n_shots = md['shots']
    matrix = read_detection_matrix(z, det_path, n_det, n_shots)

    # Read actual observable flips (logical errors)
    obs_raw = z.read(obs_path)
    obs_bytes_per_shot = 1  # 1 observable → 1 bit → 1 byte (padded)
    obs_data = np.frombuffer(obs_raw, dtype=np.uint8)[:n_shots]
    logical_errors = obs_data & 1  # bit 0

    adj = build_detector_adjacency(dpr, rr)

    # For each shot, classify events and compute abstention rate
    # Then correlate abstention with logical error
    n_sample = min(10000, n_shots)
    rng = np.random.default_rng(42)
    idx = rng.choice(n_shots, n_sample, replace=False)

    abstain_counts = []
    event_counts = []
    log_errs = logical_errors[idx]

    for s_idx in range(n_sample):
        shot = matrix[idx[s_idx]]
        active = np.where(shot == 1)[0]
        n_abstain = 0
        for det_idx in active:
            score = classify_detection_event(det_idx, shot, adj, dpr, rr)
            if score >= THETA:
                n_abstain += 1
        abstain_counts.append(n_abstain)
        event_counts.append(len(active))

    abstain_counts = np.array(abstain_counts)
    event_counts = np.array(event_counts)
    abstain_frac = abstain_counts / np.maximum(event_counts, 1)

    # Correlation: does abstaining more correlate with MORE or FEWER logical errors?
    mask = event_counts > 0
    if np.std(abstain_frac[mask]) > 0:
        r_corr, p_corr = stats.pearsonr(abstain_frac[mask], log_errs[mask].astype(float))
    else:
        r_corr, p_corr = 0.0, 1.0

    # Compare logical error rates: high-abstention shots vs low-abstention shots
    med_abstain = np.median(abstain_frac[mask])
    high_abstain = log_errs[mask & (abstain_frac >= med_abstain)]
    low_abstain = log_errs[mask & (abstain_frac < med_abstain)]
    ler_high = np.mean(high_abstain) if len(high_abstain) > 0 else 0
    ler_low = np.mean(low_abstain) if len(low_abstain) > 0 else 0

    print(f"  d={d_code} ({patch}), r={rr}:")
    print(f"    Mean events/shot: {np.mean(event_counts):.1f}")
    print(f"    Mean abstentions/shot: {np.mean(abstain_counts):.1f} ({np.mean(abstain_frac):.1%})")
    print(f"    Logical error rate (overall): {np.mean(log_errs):.4f}")
    print(f"    Correlation (abstain_frac vs logical_error): r = {r_corr:+.4f}, p = {p_corr:.4f}")
    print(f"    LER (high abstention): {ler_high:.4f}")
    print(f"    LER (low abstention):  {ler_low:.4f}")
    if ler_high > ler_low:
        print(f"    >>> ABSTAINING HURTS (+{(ler_high-ler_low)/max(ler_low,1e-6):.1%} worse)")
    elif ler_high < ler_low:
        print(f"    >>> ABSTAINING HELPS ({(ler_low-ler_high)/max(ler_low,1e-6):.1%} better)")
    else:
        print(f"    >>> ZERO EFFECT")
    print()


# ══════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════

print("=" * 100)
print("SUMMARY: REGIME CLASSIFIER FALSIFICATION TEST")
print("=" * 100)
print()
print("  Paper 3 prediction:")
print("    On sub-Poissonian hardware (IBM): classifier HELPS (7-19%)")
print("    On super-Poissonian hardware (Willow): classifier has ZERO/NEGATIVE effect")
print()
print("  IBM (from Paper 3 Table 1):")
print("    Abstain rate: 75-80% of flagged events")
print("    LER improvement: +7 to +19%")
print("    Mechanism: abstaining from ternary transitions avoids miscorrection")
print()
print("  Google Willow (this analysis):")
willow_fracs = [r['frac_ternary'] for r in all_results]
print(f"    Classified as 'ternary': {np.mean(willow_fracs):.1%} of events")
print(f"    Prediction: abstaining from these hurts (they are real errors, not transitions)")
print()
