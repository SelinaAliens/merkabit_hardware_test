"""
IBM Heron DAQEC Data — Paper 15 Consistency Tests
==================================================
Tests the "rotation gap is flat" claims against 756 QEC runs
on ibm_brisbane, ibm_kyoto, ibm_osaka (127-qubit Eagle r3).

Test 1: Suppression ratio constancy across hardware drift
Test 2: Fano factor structure across code distances
Test 3: Syndrome burst scaling (linear vs quadratic)
Test 4: Adjacent correlation vs T2 (threshold approach)
Test 5: LER vs T1/T2 regression (ratio invariance)
"""

import pandas as pd
import numpy as np
from scipy import stats
from pathlib import Path

DATA_DIR = Path(r"C:\Users\selin\OneDrive\Desktop\IBM Heron")
RESULTS_DIR = Path(r"C:\Users\selin\merkabit_results")

# Load data
print("=" * 70)
print("LOADING IBM HERON DAQEC DATA")
print("=" * 70)
master = pd.read_parquet(DATA_DIR / "master.parquet")
drift = pd.read_csv(DATA_DIR / "drift_characterization.csv")
syndrome = pd.read_csv(DATA_DIR / "syndrome_statistics.csv")

print(f"Master: {len(master)} runs, {master['backend'].nunique()} backends")
print(f"Drift: {len(drift)} measurements over {drift['day'].nunique()} days")
print(f"Syndrome: {len(syndrome)} aggregated rows")
print(f"Backends: {sorted(master['backend'].unique())}")
print(f"Distances: {sorted(master['distance'].unique())}")
print(f"Strategies: {sorted(master['strategy'].unique())}")
print()

# =====================================================================
# TEST 1: FLAT SUPPRESSION RATIO ACROSS HARDWARE DRIFT
# =====================================================================
print("=" * 70)
print("TEST 1: SUPPRESSION RATIO CONSTANCY")
print("Paper claim: CV < 0.15 across operating conditions")
print("=" * 70)

# For each backend × distance × day, compute LER ratio (baseline / drift_aware)
ratios_all = []
for backend in master['backend'].unique():
    for dist in master['distance'].unique():
        for day in master['day'].unique():
            mask_base = (
                (master['backend'] == backend) &
                (master['distance'] == dist) &
                (master['day'] == day) &
                (master['strategy'] == 'baseline_static')
            )
            mask_drift = (
                (master['backend'] == backend) &
                (master['distance'] == dist) &
                (master['day'] == day) &
                (master['strategy'] == 'drift_aware_full_stack')
            )
            ler_base = master.loc[mask_base, 'logical_error_rate']
            ler_drift = master.loc[mask_drift, 'logical_error_rate']

            if len(ler_base) > 0 and len(ler_drift) > 0:
                mean_base = ler_base.mean()
                mean_drift = ler_drift.mean()
                if mean_drift > 0:
                    ratio = mean_base / mean_drift
                    ratios_all.append({
                        'backend': backend, 'distance': dist, 'day': day,
                        'ler_baseline': mean_base, 'ler_drift_aware': mean_drift,
                        'suppression_ratio': ratio
                    })

ratios_df = pd.DataFrame(ratios_all)

if len(ratios_df) > 0:
    print(f"\nTotal ratio measurements: {len(ratios_df)}")
    print(f"\nSuppression ratio (baseline / drift_aware) summary:")
    print(f"  Mean:   {ratios_df['suppression_ratio'].mean():.4f}")
    print(f"  Median: {ratios_df['suppression_ratio'].median():.4f}")
    print(f"  Std:    {ratios_df['suppression_ratio'].std():.4f}")
    cv = ratios_df['suppression_ratio'].std() / ratios_df['suppression_ratio'].mean()
    print(f"  CV:     {cv:.4f}")
    print(f"  CV < 0.15? {'YES — CONSISTENT' if cv < 0.15 else 'NO — INCONSISTENT'}")

    # Per-backend breakdown
    print(f"\nPer-backend CV:")
    for backend in ratios_df['backend'].unique():
        sub = ratios_df[ratios_df['backend'] == backend]['suppression_ratio']
        cv_b = sub.std() / sub.mean()
        print(f"  {backend}: mean={sub.mean():.4f}, CV={cv_b:.4f} "
              f"{'PASS' if cv_b < 0.15 else 'FAIL'}")

    # Per-distance breakdown
    print(f"\nPer-distance CV:")
    for dist in sorted(ratios_df['distance'].unique()):
        sub = ratios_df[ratios_df['distance'] == dist]['suppression_ratio']
        cv_d = sub.std() / sub.mean()
        print(f"  d={dist}: mean={sub.mean():.4f}, CV={cv_d:.4f} "
              f"{'PASS' if cv_d < 0.15 else 'FAIL'}")

    # Test: is ratio constant across days? (Kruskal-Wallis)
    groups_by_day = [g['suppression_ratio'].values
                     for _, g in ratios_df.groupby('day') if len(g) > 1]
    if len(groups_by_day) > 2:
        kw_stat, kw_p = stats.kruskal(*groups_by_day)
        print(f"\nKruskal-Wallis across days: H={kw_stat:.3f}, p={kw_p:.4f}")
        print(f"  Ratio constant across days? "
              f"{'YES (p>{:.2f})'.format(kw_p) if kw_p > 0.05 else 'NO — ratio varies with day'}")
else:
    print("WARNING: Could not compute suppression ratios")

# =====================================================================
# TEST 2: FANO FACTOR STRUCTURE ACROSS CODE DISTANCES
# =====================================================================
print("\n" + "=" * 70)
print("TEST 2: FANO FACTOR STRUCTURE")
print("Paper claim: sub-Poissonian (< 1), constant across distance")
print("=" * 70)

fano = master[['backend', 'distance', 'strategy', 'fano_factor']].dropna()
print(f"\nOverall Fano factor: {fano['fano_factor'].mean():.4f} ± {fano['fano_factor'].std():.4f}")
print(f"Sub-Poissonian (< 1)? {'YES' if fano['fano_factor'].mean() < 1 else 'NO'}")

# One-sample t-test vs 1.0 (Poisson)
t_fano, p_fano = stats.ttest_1samp(fano['fano_factor'], 1.0)
print(f"t-test vs Poisson (F=1): t={t_fano:.3f}, p={p_fano:.2e}")
print(f"  Significantly sub-Poissonian? {'YES' if p_fano < 0.05 and t_fano < 0 else 'NO'}")

# Per-distance
print(f"\nFano factor by distance:")
for dist in sorted(fano['distance'].unique()):
    sub = fano[fano['distance'] == dist]['fano_factor']
    print(f"  d={dist}: {sub.mean():.4f} ± {sub.std():.4f} (n={len(sub)})")

# ANOVA across distances
groups_fano = [g['fano_factor'].values for _, g in fano.groupby('distance')]
f_stat, f_p = stats.f_oneway(*groups_fano)
print(f"\nANOVA across distances: F={f_stat:.3f}, p={f_p:.4f}")
print(f"  Fano constant across distance? "
      f"{'YES — architectural' if f_p > 0.05 else 'NO — distance-dependent'}")

# Per-backend × strategy
print(f"\nFano factor by backend × strategy:")
for backend in sorted(fano['backend'].unique()):
    for strat in sorted(fano['strategy'].unique()):
        sub = fano[(fano['backend'] == backend) & (fano['strategy'] == strat)]['fano_factor']
        print(f"  {backend} / {strat}: {sub.mean():.4f} ± {sub.std():.4f}")

# =====================================================================
# TEST 3: SYNDROME BURST SCALING (LINEAR VS QUADRATIC)
# =====================================================================
print("\n" + "=" * 70)
print("TEST 3: SYNDROME BURST SCALING")
print("Paper claim: linear burst scaling (correlated/GUE-like)")
print("Poisson prediction: quadratic scaling with distance")
print("=" * 70)

burst = master[['backend', 'distance', 'strategy', 'syndrome_burst_count']].dropna()

# Mean burst count by distance
print(f"\nMean burst count by distance:")
burst_by_d = {}
for dist in sorted(burst['distance'].unique()):
    sub = burst[burst['distance'] == dist]['syndrome_burst_count']
    burst_by_d[dist] = sub.mean()
    print(f"  d={dist}: {sub.mean():.1f} ± {sub.std():.1f}")

# Fit linear vs quadratic
distances = np.array(sorted(burst_by_d.keys()))
bursts = np.array([burst_by_d[d] for d in distances])

# Linear fit: B = a*d + b
slope_lin, intercept_lin, r_lin, p_lin, se_lin = stats.linregress(distances, bursts)
resid_lin = bursts - (slope_lin * distances + intercept_lin)
ss_res_lin = np.sum(resid_lin**2)

# Quadratic fit: B = a*d^2 + b*d + c
coeffs_quad = np.polyfit(distances, bursts, 2)
pred_quad = np.polyval(coeffs_quad, distances)
resid_quad = bursts - pred_quad
ss_res_quad = np.sum(resid_quad**2)

print(f"\nLinear fit: B = {slope_lin:.2f}·d + {intercept_lin:.2f}")
print(f"  R² = {r_lin**2:.6f}, residual SS = {ss_res_lin:.2f}")
print(f"Quadratic fit: B = {coeffs_quad[0]:.2f}·d² + {coeffs_quad[1]:.2f}·d + {coeffs_quad[2]:.2f}")
print(f"  Residual SS = {ss_res_quad:.2f}")

# Check if quadratic term is needed
# With only 3 points, we can check the ratio
ratio_3_to_5 = burst_by_d.get(5, 0) / burst_by_d.get(3, 1) if burst_by_d.get(3, 0) > 0 else float('nan')
ratio_5_to_7 = burst_by_d.get(7, 0) / burst_by_d.get(5, 1) if burst_by_d.get(5, 0) > 0 else float('nan')
print(f"\nScaling ratios:")
print(f"  B(d=5)/B(d=3) = {ratio_3_to_5:.3f} (linear predicts {5/3:.3f}, quadratic predicts {25/9:.3f})")
print(f"  B(d=7)/B(d=5) = {ratio_5_to_7:.3f} (linear predicts {7/5:.3f}, quadratic predicts {49/25:.3f})")

closer_to_linear_1 = abs(ratio_3_to_5 - 5/3) < abs(ratio_3_to_5 - 25/9)
closer_to_linear_2 = abs(ratio_5_to_7 - 7/5) < abs(ratio_5_to_7 - 49/25)
print(f"  d=5/d=3: closer to {'LINEAR' if closer_to_linear_1 else 'QUADRATIC'}")
print(f"  d=7/d=5: closer to {'LINEAR' if closer_to_linear_2 else 'QUADRATIC'}")

# =====================================================================
# TEST 4: ADJACENT CORRELATION VS T2 (THRESHOLD APPROACH)
# =====================================================================
print("\n" + "=" * 70)
print("TEST 4: ADJACENT CORRELATION VS T2")
print("Paper claim: T2 is threshold channel; lower T2 → higher correlation")
print("=" * 70)

ac_data = master[['backend', 'avg_t2_us', 'adjacent_correlation', 'avg_t1_us']].dropna()

# Correlation: adjacent_correlation vs T2
r_t2, p_t2 = stats.pearsonr(ac_data['avg_t2_us'], ac_data['adjacent_correlation'])
r_t1, p_t1 = stats.pearsonr(ac_data['avg_t1_us'], ac_data['adjacent_correlation'])

print(f"\nPearson correlation:")
print(f"  Adjacent corr vs T2: r={r_t2:.4f}, p={p_t2:.4e}")
print(f"  Adjacent corr vs T1: r={r_t1:.4f}, p={p_t1:.4e}")

# Paper predicts NEGATIVE correlation with T2 (lower T2 → higher adj_corr)
print(f"\n  T2 prediction (negative r): {'CONFIRMED' if r_t2 < 0 and p_t2 < 0.05 else 'NOT CONFIRMED'}")
print(f"  T1 for comparison: r={r_t1:.4f}")

# Spearman (rank) as robustness check
rs_t2, ps_t2 = stats.spearmanr(ac_data['avg_t2_us'], ac_data['adjacent_correlation'])
rs_t1, ps_t1 = stats.spearmanr(ac_data['avg_t1_us'], ac_data['adjacent_correlation'])
print(f"\nSpearman rank correlation:")
print(f"  Adjacent corr vs T2: ρ={rs_t2:.4f}, p={ps_t2:.4e}")
print(f"  Adjacent corr vs T1: ρ={rs_t1:.4f}, p={ps_t1:.4e}")

# T2 quartile analysis
ac_data['t2_quartile'] = pd.qcut(ac_data['avg_t2_us'], 4, labels=['Q1(low)', 'Q2', 'Q3', 'Q4(high)'])
print(f"\nAdjacent correlation by T2 quartile:")
for q in ['Q1(low)', 'Q2', 'Q3', 'Q4(high)']:
    sub = ac_data[ac_data['t2_quartile'] == q]['adjacent_correlation']
    print(f"  {q}: {sub.mean():.4f} ± {sub.std():.4f}")

# =====================================================================
# TEST 5: LER VS T1/T2 REGRESSION — RATIO INVARIANCE
# =====================================================================
print("\n" + "=" * 70)
print("TEST 5: LER VS T1/T2 — SUPPRESSION RATIO INVARIANCE")
print("Paper claim: absolute LER varies with drift, but ratio stays constant")
print("=" * 70)

# Merge ratio data with T1/T2 from drift characterization
if len(ratios_df) > 0:
    # Get average T1, T2 per backend per day from drift data
    drift_daily = drift.groupby(['backend', 'day']).agg(
        avg_t1=('avg_t1_us', 'mean'),
        avg_t2=('avg_t2_us', 'mean')
    ).reset_index()

    ratios_merged = ratios_df.merge(drift_daily, on=['backend', 'day'], how='left')

    # Does absolute LER correlate with T1/T2?
    r_ler_t1, p_ler_t1 = stats.pearsonr(
        ratios_merged['avg_t1'].dropna(),
        ratios_merged.loc[ratios_merged['avg_t1'].notna(), 'ler_baseline']
    )
    r_ler_t2, p_ler_t2 = stats.pearsonr(
        ratios_merged['avg_t2'].dropna(),
        ratios_merged.loc[ratios_merged['avg_t2'].notna(), 'ler_baseline']
    )
    print(f"\nAbsolute LER (baseline) vs hardware:")
    print(f"  LER vs T1: r={r_ler_t1:.4f}, p={p_ler_t1:.4e}")
    print(f"  LER vs T2: r={r_ler_t2:.4f}, p={p_ler_t2:.4e}")
    print(f"  (Expect: LER varies with T1/T2 → significant correlation)")

    # Does suppression RATIO correlate with T1/T2?
    valid = ratios_merged.dropna(subset=['avg_t1', 'avg_t2', 'suppression_ratio'])
    r_ratio_t1, p_ratio_t1 = stats.pearsonr(valid['avg_t1'], valid['suppression_ratio'])
    r_ratio_t2, p_ratio_t2 = stats.pearsonr(valid['avg_t2'], valid['suppression_ratio'])
    print(f"\nSuppression RATIO vs hardware (should be ~0 if architectural):")
    print(f"  Ratio vs T1: r={r_ratio_t1:.4f}, p={p_ratio_t1:.4e}")
    print(f"  Ratio vs T2: r={r_ratio_t2:.4f}, p={p_ratio_t2:.4e}")
    ratio_invariant_t1 = p_ratio_t1 > 0.05
    ratio_invariant_t2 = p_ratio_t2 > 0.05
    print(f"  Ratio invariant to T1? {'YES' if ratio_invariant_t1 else 'NO'}")
    print(f"  Ratio invariant to T2? {'YES' if ratio_invariant_t2 else 'NO'}")

    # Residual analysis: does ratio drift with time?
    r_ratio_day, p_ratio_day = stats.pearsonr(valid['day'], valid['suppression_ratio'])
    print(f"\n  Ratio vs day (temporal drift): r={r_ratio_day:.4f}, p={p_ratio_day:.4e}")
    print(f"  No temporal drift? {'YES' if p_ratio_day > 0.05 else 'NO -- ratio drifts'}")

# =====================================================================
# SUMMARY
# =====================================================================
print("\n" + "=" * 70)
print("SUMMARY — PAPER 15 CONSISTENCY WITH IBM HERON DATA")
print("=" * 70)

print("""
Test 1: Suppression ratio constancy
  → CV of baseline/drift_aware ratio across all conditions
  → Paper prediction: CV < 0.15

Test 2: Fano factor
  → Sub-Poissonian (< 1): confirms cooperative error structure
  → Distance-independent: confirms architectural origin

Test 3: Burst scaling
  → Linear: GUE-like (correlated errors, level repulsion)
  → Quadratic: Poisson (independent errors)

Test 4: Adjacent correlation vs T2
  → Negative correlation: T2 is threshold channel
  → Paper: T2 less controllable by recalibration

Test 5: LER ratio invariance
  → Absolute LER varies with T1/T2 drift (expected)
  → Ratio stays constant (architectural suppression)
""")

print("Script complete.")
