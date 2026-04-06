"""
Google Willow 105Q — Temporal Depth Analysis
Decompose detection events round-by-round to separate
spatial correlation (within a round) from temporal correlation (across rounds).

Key question: Is the super-Poissonian Fano driven by temporal correlations
(error bursts spanning multiple rounds) or spatial correlations (within a single round)?
"""
import zipfile, json, sys, numpy as np
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

ZIP_PATH = 'C:/Users/selin/Downloads/google_105Q_surface_code_d3_d5_d7.zip'
z = zipfile.ZipFile(ZIP_PATH)


def count_detectors(z, stim_path):
    """Count DETECTOR lines and determine detectors-per-round from stim circuit."""
    text = z.read(stim_path).decode()
    total = text.count('DETECTOR')
    return total


def read_detection_matrix(z, path, n_detectors, n_shots):
    """Read b8 detection events, return full binary matrix (shots x detectors)."""
    raw = z.read(path)
    bytes_per_shot = (n_detectors + 7) // 8
    data = np.frombuffer(raw, dtype=np.uint8).reshape(n_shots, bytes_per_shot)
    # Unpack to full bit matrix
    matrix = np.zeros((n_shots, n_detectors), dtype=np.uint8)
    for byte_idx in range(bytes_per_shot):
        for bit in range(min(8, n_detectors - byte_idx * 8)):
            col = byte_idx * 8 + bit
            matrix[:, col] = (data[:, byte_idx] >> bit) & 1
    return matrix


def get_metadata(z, meta_path):
    md = json.loads(z.read(meta_path))
    parts = meta_path.split('/')
    md['patch'] = parts[1]
    md['prefix'] = '/'.join(parts[:4])
    return md


print("=" * 110)
print("GOOGLE WILLOW 105Q — TEMPORAL DEPTH ANALYSIS")
print("Decomposing detection events round-by-round")
print("=" * 110)
print()

# We need to understand the detector layout.
# In a surface code with d data qubits and m measure qubits over r rounds:
#   - Round 1 has m "boundary" detectors (comparing first measurement to initialization)
#   - Rounds 2..r each have m "bulk" detectors (comparing consecutive measurements)
#   - Total detectors = m * r (approximately, first round may differ)
# Detectors are ordered: round 1 detectors, round 2 detectors, ..., round r detectors

# For d=3: 8 measure qubits => 8 detectors per round
# For d=5: 24 measure qubits => 24 detectors per round
# For d=7: 48 measure qubits => 48 detectors per round

# First, verify detector counts
print("DETECTOR COUNT VERIFICATION:")
for d_code, patch, n_meas_expected in [(3, 'd3_at_q4_5', 8), (5, 'd5_at_q4_7', 24), (7, 'd7_at_q6_7', 48)]:
    for rr in [1, 10, 13, 50, 250]:
        stim_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/circuit_ideal.stim'
        try:
            n_det = count_detectors(z, stim_path)
            det_per_round = n_det / rr
            print(f"  d={d_code}, r={rr:>3}: total_det={n_det:>5}, per_round={det_per_round:.1f} (expect ~{n_meas_expected})")
        except:
            pass
    print()


# ──────────────────────────────────────────────────────────────────────
# ANALYSIS 1: Per-round Fano factor
# Split the detector columns into rounds, compute syndrome count per round,
# then compute Fano across rounds within each shot, and across shots within each round.
# ──────────────────────────────────────────────────────────────────────

print("=" * 110)
print("ANALYSIS 1: SPATIAL FANO (within each round, across shots)")
print("  For each round separately, count detection events across shots.")
print("  Fano > 1 here means spatial over-dispersion within a single round.")
print("=" * 110)
print()

# Use a moderate number of rounds for good statistics
target_rounds = [13, 50, 110, 250]
target_configs = [
    (3, 'd3_at_q4_5', 8),
    (5, 'd5_at_q4_7', 24),
    (7, 'd7_at_q6_7', 48),
]

for d_code, patch, det_per_round in target_configs:
    print(f"  Distance {d_code} ({patch}):")
    for rr in target_rounds:
        stim_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/circuit_ideal.stim'
        det_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/detection_events.b8'
        meta_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/metadata.json'

        try:
            n_det = count_detectors(z, stim_path)
            md = json.loads(z.read(meta_path))
            n_shots = md['shots']

            matrix = read_detection_matrix(z, det_path, n_det, n_shots)

            # Split into rounds
            # Detectors are laid out sequentially: first det_per_round for round 1, etc.
            actual_dpr = n_det // rr
            if n_det % rr != 0:
                # Might have extra boundary detectors — use floor
                actual_dpr = n_det // rr

            # Compute per-round syndrome counts
            round_fanos = []
            round_means = []
            for r_idx in range(rr):
                start = r_idx * actual_dpr
                end = start + actual_dpr
                if end > n_det:
                    break
                round_counts = np.sum(matrix[:, start:end], axis=1)
                mu = np.mean(round_counts)
                var = np.var(round_counts, ddof=1)
                f = var / mu if mu > 0 else np.nan
                round_fanos.append(f)
                round_means.append(mu)

            rf = np.array(round_fanos)
            rm = np.array(round_means)

            # First round vs bulk rounds
            f_first = rf[0]
            f_bulk = np.mean(rf[1:]) if len(rf) > 1 else np.nan
            f_last = rf[-1] if len(rf) > 0 else np.nan

            print(f"    r={rr:>3}: dpr={actual_dpr}, "
                  f"F_round1={f_first:.4f}, F_bulk={f_bulk:.4f}, F_last={f_last:.4f}, "
                  f"F_all_rounds_mean={np.mean(rf):.4f} +/- {np.std(rf):.4f}, "
                  f"mean_det/round={np.mean(rm):.3f}")
        except Exception as e:
            print(f"    r={rr:>3}: ERROR - {e}")
    print()


# ──────────────────────────────────────────────────────────────────────
# ANALYSIS 2: Temporal Fano (across rounds, within each shot)
# For each shot, count events in each round => time series of length r.
# Compute Fano of this time series across rounds.
# ──────────────────────────────────────────────────────────────────────

print("=" * 110)
print("ANALYSIS 2: TEMPORAL FANO (across rounds within each shot)")
print("  For each shot, make a time series of per-round detection counts.")
print("  Compute Fano of this time series. Fano > 1 = temporal bunching.")
print("=" * 110)
print()

for d_code, patch, det_per_round in target_configs:
    print(f"  Distance {d_code} ({patch}):")
    for rr in [50, 110, 250]:  # Need enough rounds for meaningful temporal stats
        stim_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/circuit_ideal.stim'
        det_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/detection_events.b8'
        meta_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/metadata.json'

        try:
            n_det = count_detectors(z, stim_path)
            md = json.loads(z.read(meta_path))
            n_shots = md['shots']

            matrix = read_detection_matrix(z, det_path, n_det, n_shots)
            actual_dpr = n_det // rr

            # Build per-round counts for each shot: shape (n_shots, rr)
            round_counts = np.zeros((n_shots, rr), dtype=np.int32)
            for r_idx in range(rr):
                start = r_idx * actual_dpr
                end = min(start + actual_dpr, n_det)
                round_counts[:, r_idx] = np.sum(matrix[:, start:end], axis=1)

            # Temporal Fano per shot
            shot_means = np.mean(round_counts, axis=1)
            shot_vars = np.var(round_counts, axis=1, ddof=1)
            valid = shot_means > 0
            temporal_fanos = np.full(n_shots, np.nan)
            temporal_fanos[valid] = shot_vars[valid] / shot_means[valid]
            tf = temporal_fanos[valid]

            print(f"    r={rr:>3}: temporal Fano per shot: "
                  f"mean={np.mean(tf):.4f} +/- {np.std(tf):.4f}, "
                  f"median={np.median(tf):.4f}, "
                  f"fraction > 1: {np.mean(tf > 1):.3f}, "
                  f"fraction < 1: {np.mean(tf < 1):.3f}")

            # Adjacent round correlation (lag-1 autocorrelation of per-round counts)
            # Average across shots
            autocorrs = []
            for shot_idx in range(min(10000, n_shots)):
                ts = round_counts[shot_idx, :].astype(float)
                if np.std(ts) > 0:
                    ac = np.corrcoef(ts[:-1], ts[1:])[0, 1]
                    autocorrs.append(ac)
            autocorrs = np.array(autocorrs)
            print(f"           lag-1 autocorrelation: "
                  f"mean={np.mean(autocorrs):.4f} +/- {np.std(autocorrs):.4f}, "
                  f"fraction > 0: {np.mean(autocorrs > 0):.3f}")

        except Exception as e:
            print(f"    r={rr:>3}: ERROR - {e}")
    print()


# ──────────────────────────────────────────────────────────────────────
# ANALYSIS 3: Adjacent detector correlation (spatial, within round)
# ──────────────────────────────────────────────────────────────────────

print("=" * 110)
print("ANALYSIS 3: ADJACENT DETECTOR CORRELATION (spatial, within single round)")
print("  Correlation between neighboring detectors within the same round.")
print("  Positive = spatial bunching. Negative = spatial anti-bunching.")
print("=" * 110)
print()

for d_code, patch, det_per_round in target_configs:
    rr = 50  # Use 50 rounds
    stim_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/circuit_ideal.stim'
    det_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/detection_events.b8'
    meta_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/metadata.json'

    try:
        n_det = count_detectors(z, stim_path)
        md = json.loads(z.read(meta_path))
        n_shots = md['shots']

        matrix = read_detection_matrix(z, det_path, n_det, n_shots)
        actual_dpr = n_det // rr

        # Pick a middle round (round 25) to avoid boundary effects
        r_idx = rr // 2
        start = r_idx * actual_dpr
        end = start + actual_dpr
        round_data = matrix[:, start:end].astype(float)

        # Adjacent detector correlation
        adj_corrs = []
        for j in range(actual_dpr - 1):
            if np.std(round_data[:, j]) > 0 and np.std(round_data[:, j+1]) > 0:
                c = np.corrcoef(round_data[:, j], round_data[:, j+1])[0, 1]
                adj_corrs.append(c)

        adj_corrs = np.array(adj_corrs)
        print(f"  d={d_code} ({patch}), round {r_idx+1}/{rr}:")
        print(f"    {actual_dpr} detectors, {len(adj_corrs)} adjacent pairs")
        print(f"    Adjacent correlation: mean={np.mean(adj_corrs):.4f} +/- {np.std(adj_corrs):.4f}")
        print(f"    Fraction positive: {np.mean(adj_corrs > 0):.3f}")
        print(f"    Min={np.min(adj_corrs):.4f}, Max={np.max(adj_corrs):.4f}")
        print()

    except Exception as e:
        print(f"  d={d_code}: ERROR - {e}")
        print()


# ──────────────────────────────────────────────────────────────────────
# ANALYSIS 4: Decompose total Fano into spatial + temporal components
# Total Fano = F_spatial + F_temporal_contribution
# ──────────────────────────────────────────────────────────────────────

print("=" * 110)
print("ANALYSIS 4: FANO DECOMPOSITION")
print("  Total Var(N) = E[Var(N|round)] + Var(E[N|round])")
print("  = within-round variance (spatial) + between-round variance (temporal)")
print("=" * 110)
print()

for d_code, patch, det_per_round in target_configs:
    print(f"  Distance {d_code} ({patch}):")
    for rr in [13, 50, 250]:
        det_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/detection_events.b8'
        meta_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/metadata.json'
        stim_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/circuit_ideal.stim'

        try:
            n_det = count_detectors(z, stim_path)
            md = json.loads(z.read(meta_path))
            n_shots = md['shots']

            matrix = read_detection_matrix(z, det_path, n_det, n_shots)
            actual_dpr = n_det // rr

            # Total counts per shot
            total_counts = np.sum(matrix, axis=1)
            total_mean = np.mean(total_counts)
            total_var = np.var(total_counts, ddof=1)
            total_fano = total_var / total_mean

            # Per-round counts: shape (n_shots, rr)
            round_counts = np.zeros((n_shots, rr), dtype=np.int32)
            for r_idx in range(rr):
                start = r_idx * actual_dpr
                end = min(start + actual_dpr, n_det)
                round_counts[:, r_idx] = np.sum(matrix[:, start:end], axis=1)

            # Within-round variance (averaged across rounds)
            # For each round, compute variance across shots
            within_vars = []
            within_means = []
            for r_idx in range(rr):
                within_vars.append(np.var(round_counts[:, r_idx], ddof=1))
                within_means.append(np.mean(round_counts[:, r_idx]))

            # Between-round variance of means
            round_means_across_shots = np.mean(round_counts, axis=0)  # mean per round
            between_var = np.var(round_means_across_shots, ddof=1) * n_shots  # scaled

            avg_within_var = np.mean(within_vars)
            avg_within_mean = np.mean(within_means)
            spatial_fano = avg_within_var / avg_within_mean if avg_within_mean > 0 else np.nan

            # Between-round contribution per shot
            shot_round_means = np.mean(round_counts, axis=0)  # (rr,) mean count in each round
            between_round_var = np.var(shot_round_means)

            print(f"    r={rr:>3}: Total Fano = {total_fano:.4f}")
            print(f"           Spatial Fano (avg within-round) = {spatial_fano:.4f}")
            print(f"           Round-mean variation: {np.std(shot_round_means):.4f} "
                  f"(range {np.min(shot_round_means):.3f} - {np.max(shot_round_means):.3f})")
            print(f"           First 3 round means: {shot_round_means[:3]}")
            print(f"           Last 3 round means:  {shot_round_means[-3:]}")

        except Exception as e:
            print(f"    r={rr:>3}: ERROR - {e}")
    print()


# ──────────────────────────────────────────────────────────────────────
# ANALYSIS 5: IBM-style Fano on single-round slices
# If we look at ONE round at a time (like IBM's single-cycle data),
# what Fano do we get?
# ──────────────────────────────────────────────────────────────────────

print("=" * 110)
print("ANALYSIS 5: SINGLE-ROUND FANO (closest comparison to IBM)")
print("  IBM measures Fano on per-run syndrome counts.")
print("  Google data: compute Fano on per-shot counts within a single round.")
print("=" * 110)
print()

for d_code, patch, det_per_round in target_configs:
    rr = 50
    stim_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/circuit_ideal.stim'
    det_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/detection_events.b8'
    meta_path = f'google_105Q_surface_code_d3_d5_d7/{patch}/X/r{rr}/metadata.json'

    try:
        n_det = count_detectors(z, stim_path)
        md = json.loads(z.read(meta_path))
        n_shots = md['shots']
        matrix = read_detection_matrix(z, det_path, n_det, n_shots)
        actual_dpr = n_det // rr

        print(f"  d={d_code} ({patch}), r={rr}, {actual_dpr} detectors/round:")

        # Sample several rounds
        single_round_fanos = []
        for r_idx in [0, 1, 5, 10, 24, 25, 49]:
            if r_idx >= rr:
                continue
            start = r_idx * actual_dpr
            end = start + actual_dpr
            counts = np.sum(matrix[:, start:end], axis=1)
            mu = np.mean(counts)
            var = np.var(counts, ddof=1)
            f = var / mu if mu > 0 else np.nan
            single_round_fanos.append(f)
            label = "FIRST" if r_idx == 0 else ("LAST" if r_idx == rr - 1 else "")
            print(f"    Round {r_idx+1:>3}: mean={mu:.3f}, var={var:.3f}, "
                  f"Fano={f:.4f}  {label}")

        # All rounds
        all_single = []
        for r_idx in range(rr):
            start = r_idx * actual_dpr
            end = start + actual_dpr
            counts = np.sum(matrix[:, start:end], axis=1)
            mu = np.mean(counts)
            var = np.var(counts, ddof=1)
            f = var / mu if mu > 0 else np.nan
            all_single.append(f)

        all_single = np.array(all_single)
        print(f"    ALL {rr} rounds: Fano mean={np.mean(all_single):.4f} +/- {np.std(all_single):.4f}")
        print(f"    Excluding round 1: Fano mean={np.mean(all_single[1:]):.4f} +/- {np.std(all_single[1:]):.4f}")
        print()

    except Exception as e:
        print(f"  d={d_code}: ERROR - {e}")
        print()


print("=" * 110)
print("FINAL SUMMARY")
print("=" * 110)
print()
print("  IBM Eagle r3:   F = 0.856  (sub-Poissonian, anti-bunched)")
print("  Google Willow:   F ~ 2.4   (super-Poissonian, bunched)")
print()
print("  The question: is Willow's F>1 spatial or temporal?")
print("  If single-round Fano is near 1.0, the excess is purely temporal.")
print("  If single-round Fano is also >1, there is genuine spatial bunching.")
print()
