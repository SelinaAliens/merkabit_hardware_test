"""
DAQEC-Benchmark: REFINED KWW Analysis — Autocorrelation & PSD Approach
Merkabit Research Program — March 2026

Key insight from first pass: IBM hardware T1/T2 is a STOCHASTIC fluctuation
(TLS fluctuators switching), not a smooth monotonic decay. KWW on the raw
time series gives R2 ~ 0. The correct approach:

1. Autocorrelation function (ACF) → KWW fit to temporal correlation decay
2. Power spectral density (PSD) → 1/f^beta noise exponent
3. Fluctuation magnitude distribution → stretched exponential?
4. Session-pair analysis: consecutive session T1/T2 differences
"""

import pandas as pd
import numpy as np
from scipy.optimize import curve_fit
from scipy import stats, signal
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = Path(r"C:\Users\selin\OneDrive\Desktop\IBM Heron")
OUT_DIR = Path(r"C:\Users\selin\merkabit_results\daqec")

master = pd.read_parquet(DATA_DIR / "master.parquet")
drift = pd.read_csv(DATA_DIR / "drift_characterization.csv")
drift['timestamp_utc'] = pd.to_datetime(drift['timestamp_utc'])
master['timestamp_utc'] = pd.to_datetime(master['timestamp_utc'])
master['calibration_timestamp'] = pd.to_datetime(master['calibration_timestamp'])

# ── KWW functions ──────────────────────────────────────────────────────
def kww(t, A, tau, alpha, offset):
    return A * np.exp(-(t / tau) ** alpha) + offset

def fit_kww(t, y, p0=None, bounds=None):
    if len(t) < 5:
        return None
    if bounds is None:
        bounds = ([0, 0.01, 0.1, -0.5], [2.0, 200, 3.0, 0.5])
    if p0 is None:
        p0 = [1.0, 5.0, 1.33, 0.0]
    try:
        popt, pcov = curve_fit(kww, t, y, p0=p0, bounds=bounds, maxfev=20000)
        y_pred = kww(t, *popt)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 1e-15 else 0.0
        perr = np.sqrt(np.diag(pcov))
        return {
            'A': popt[0], 'tau': popt[1], 'alpha': popt[2], 'offset': popt[3],
            'alpha_err': perr[2], 'r2': r2,
            'delta_alpha': abs(popt[2] - 4/3)
        }
    except Exception:
        return None

def fit_exp(t, y):
    if len(t) < 4:
        return None
    try:
        def exp1(t, A, tau, offset):
            return A * np.exp(-t / tau) + offset
        popt, _ = curve_fit(exp1, t, y, p0=[1, 5, 0],
                            bounds=([0, 0.01, -1], [2, 200, 1]), maxfev=10000)
        y_pred = exp1(t, *popt)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        return 1 - ss_res / ss_tot if ss_tot > 1e-15 else 0.0
    except Exception:
        return None

# ═══════════════════════════════════════════════════════════════════════
# PREPARE CLEAN TIME SERIES (average across sessions per timestamp)
# ═══════════════════════════════════════════════════════════════════════
print("Preparing clean time series (session-averaged per timestamp)...")

ts_data = {}
for backend in ['ibm_brisbane', 'ibm_kyoto', 'ibm_osaka']:
    bdata = drift[drift['backend'] == backend].copy()
    # Average across multiple sessions at same timestamp
    grouped = bdata.groupby('timestamp_utc').agg({
        'avg_t1_us': 'mean',
        'avg_t2_us': 'mean',
        'probe_t1_us': 'mean',
        'probe_t2_us': 'mean'
    }).sort_index().reset_index()

    t0 = grouped['timestamp_utc'].min()
    grouped['hours'] = (grouped['timestamp_utc'] - t0).dt.total_seconds() / 3600.0
    ts_data[backend] = grouped
    print(f"  {backend}: {len(grouped)} unique timestamps over {grouped['hours'].max():.0f} hours")


# ═══════════════════════════════════════════════════════════════════════
# ANALYSIS 1: AUTOCORRELATION FUNCTION → KWW FIT
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("ANALYSIS 1: AUTOCORRELATION FUNCTION — KWW decay of C(lag)")
print("=" * 70)

acf_results = []

fig_acf, axes_acf = plt.subplots(3, 2, figsize=(14, 12))
fig_acf.suptitle('T1/T2 Autocorrelation Decay — KWW Fits\nIBM Eagle r3 Hardware, 14-day monitoring', fontsize=13)

for i, backend in enumerate(['ibm_brisbane', 'ibm_kyoto', 'ibm_osaka']):
    gdata = ts_data[backend]

    for j, (col, label) in enumerate([('avg_t1_us', 'T1'), ('avg_t2_us', 'T2')]):
        ax = axes_acf[i, j]
        vals = gdata[col].values
        n = len(vals)

        # Compute autocorrelation
        vals_c = vals - np.mean(vals)
        var = np.var(vals)
        if var < 1e-10 or n < 10:
            continue

        max_lag = min(n // 2, 20)
        acf = np.zeros(max_lag)
        for lag in range(max_lag):
            if lag == 0:
                acf[lag] = 1.0
            else:
                acf[lag] = np.mean(vals_c[:n-lag] * vals_c[lag:]) / var

        lags = np.arange(max_lag).astype(float)

        # Plot raw ACF
        ax.bar(lags, acf, color='steelblue', alpha=0.6, width=0.8, label='ACF')

        # Fit KWW to positive ACF values (lag >= 1)
        pos_mask = (lags >= 1) & (acf > 0.01)
        if pos_mask.sum() >= 4:
            lags_fit = lags[pos_mask]
            acf_fit = acf[pos_mask]

            result = fit_kww(lags_fit, acf_fit,
                           p0=[1.0, 5.0, 1.33, 0.0],
                           bounds=([0, 0.1, 0.1, -0.5], [2, 50, 3.0, 0.5]))
            r2_exp = fit_exp(lags_fit, acf_fit)

            if result:
                result['backend'] = backend
                result['signal'] = f'ACF_{label}'
                result['r2_exp'] = r2_exp or 0.0
                result['n_lags'] = len(acf_fit)
                acf_results.append(result)

                # Plot fit
                lag_fine = np.linspace(lags_fit.min(), lags_fit.max(), 100)
                acf_pred = kww(lag_fine, result['A'], result['tau'], result['alpha'], result['offset'])
                ax.plot(lag_fine, acf_pred, 'r-', lw=2,
                       label=f"KWW: $\\alpha$={result['alpha']:.3f}, R$^2$={result['r2']:.3f}")

                status = "IN WINDOW" if result['delta_alpha'] < 0.15 else \
                         "NEAR" if result['delta_alpha'] < 0.25 else "outside"
                print(f"  {backend:15s} ACF_{label}: alpha={result['alpha']:.3f} +/- {result['alpha_err']:.3f}, "
                      f"tau={result['tau']:.1f} lags, R2_kww={result['r2']:.4f}, R2_exp={result['r2_exp']:.4f}, "
                      f"|a-4/3|={result['delta_alpha']:.3f} {status}")

        ax.axhline(0, color='gray', ls=':', lw=0.5)
        ax.axhline(1.96/np.sqrt(n), color='gray', ls='--', lw=0.5, alpha=0.5)
        ax.axhline(-1.96/np.sqrt(n), color='gray', ls='--', lw=0.5, alpha=0.5)
        ax.set_xlabel('Lag (sessions)')
        ax.set_ylabel('Autocorrelation')
        ax.set_title(f'{backend} — {label}')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(OUT_DIR / 'daqec_acf_kww.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"\nSaved: {OUT_DIR / 'daqec_acf_kww.png'}")


# ═══════════════════════════════════════════════════════════════════════
# ANALYSIS 2: POWER SPECTRAL DENSITY — 1/f^beta noise
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("ANALYSIS 2: POWER SPECTRAL DENSITY — 1/f^beta noise exponent")
print("=" * 70)

psd_results = []

fig_psd, axes_psd = plt.subplots(3, 2, figsize=(14, 12))
fig_psd.suptitle('T1/T2 Power Spectral Density — 1/f^beta Noise\nIBM Eagle r3 Hardware', fontsize=13)

for i, backend in enumerate(['ibm_brisbane', 'ibm_kyoto', 'ibm_osaka']):
    gdata = ts_data[backend]

    for j, (col, label) in enumerate([('avg_t1_us', 'T1'), ('avg_t2_us', 'T2')]):
        ax = axes_psd[i, j]
        vals = gdata[col].values
        n = len(vals)

        if n < 10:
            continue

        # Compute PSD via periodogram
        freqs, psd = signal.periodogram(vals - np.mean(vals), fs=1.0)  # fs=1 session

        # Remove DC
        mask = freqs > 0
        freqs_pos = freqs[mask]
        psd_pos = psd[mask]

        if len(freqs_pos) < 3 or np.any(psd_pos <= 0):
            continue

        # Log-log fit for 1/f^beta
        log_f = np.log10(freqs_pos)
        log_p = np.log10(psd_pos)

        slope, intercept, r, p_val, se = stats.linregress(log_f, log_p)
        beta = -slope  # PSD ~ 1/f^beta means log(PSD) = -beta * log(f) + const

        psd_results.append({
            'backend': backend, 'signal': label,
            'beta': beta, 'beta_err': se, 'r2_psd': r**2,
            'n_freqs': len(freqs_pos)
        })

        print(f"  {backend:15s} {label}: beta={beta:.3f} +/- {se:.3f}, R2={r**2:.4f}")

        # Plot
        ax.loglog(freqs_pos, psd_pos, 'o', ms=4, alpha=0.6, color='C0')
        f_fit = np.logspace(np.log10(freqs_pos.min()), np.log10(freqs_pos.max()), 50)
        ax.loglog(f_fit, 10**intercept * f_fit**slope, 'r-', lw=2,
                 label=f'1/f$^{{\\beta}}$: $\\beta$={beta:.3f}, R$^2$={r**2:.3f}')
        ax.set_xlabel('Frequency (1/session)')
        ax.set_ylabel('PSD')
        ax.set_title(f'{backend} — {label}')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3, which='both')

plt.tight_layout()
plt.savefig(OUT_DIR / 'daqec_psd.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"\nSaved: {OUT_DIR / 'daqec_psd.png'}")


# ═══════════════════════════════════════════════════════════════════════
# ANALYSIS 3: FLUCTUATION DISTRIBUTION — KWW on |delta_T1| CDF
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("ANALYSIS 3: FLUCTUATION DISTRIBUTION — consecutive session changes")
print("=" * 70)

fluct_results = []

fig_fluct, axes_fluct = plt.subplots(3, 2, figsize=(14, 12))
fig_fluct.suptitle('T1/T2 Fluctuation Magnitude Distribution — KWW Fit\n|T1(t+1) - T1(t)| survival function', fontsize=13)

for i, backend in enumerate(['ibm_brisbane', 'ibm_kyoto', 'ibm_osaka']):
    gdata = ts_data[backend]

    for j, (col, label) in enumerate([('avg_t1_us', 'T1'), ('avg_t2_us', 'T2')]):
        ax = axes_fluct[i, j]
        vals = gdata[col].values

        # Consecutive differences
        diffs = np.abs(np.diff(vals))

        if len(diffs) < 10:
            continue

        # Sort for survival function S(x) = P(|delta| > x)
        diffs_sorted = np.sort(diffs)
        survival = 1.0 - np.arange(1, len(diffs_sorted) + 1) / (len(diffs_sorted) + 1)

        # Normalize diffs to [0, max]
        d_norm = diffs_sorted / diffs_sorted.max()

        # Fit KWW to survival function: S(x) = exp(-(x/tau)^alpha)
        pos_mask = survival > 0.01
        if pos_mask.sum() >= 5:
            result = fit_kww(d_norm[pos_mask], survival[pos_mask],
                           p0=[1.0, 0.5, 1.33, 0.0],
                           bounds=([0.5, 0.01, 0.1, -0.1], [1.5, 5.0, 3.0, 0.1]))
            r2_exp = fit_exp(d_norm[pos_mask], survival[pos_mask])

            if result:
                result['backend'] = backend
                result['signal'] = f'Fluct_{label}'
                result['r2_exp'] = r2_exp or 0.0
                result['n_points'] = pos_mask.sum()
                result['mean_fluct_us'] = np.mean(diffs)
                result['median_fluct_us'] = np.median(diffs)
                fluct_results.append(result)

                status = "IN WINDOW" if result['delta_alpha'] < 0.15 else \
                         "NEAR" if result['delta_alpha'] < 0.25 else "outside"
                print(f"  {backend:15s} {label}: alpha={result['alpha']:.3f} +/- {result['alpha_err']:.3f}, "
                      f"R2_kww={result['r2']:.4f}, R2_exp={result['r2_exp']:.4f}, "
                      f"|a-4/3|={result['delta_alpha']:.3f} {status}, "
                      f"mean_fluct={result['mean_fluct_us']:.1f} us")

        # Plot
        ax.semilogy(diffs_sorted, survival, 'o', ms=4, alpha=0.6, color='C0', label='Data')

        if fluct_results and fluct_results[-1]['signal'] == f'Fluct_{label}' and \
           fluct_results[-1]['backend'] == backend:
            r = fluct_results[-1]
            x_fit = np.linspace(d_norm[pos_mask].min(), d_norm[pos_mask].max(), 100)
            y_fit = kww(x_fit, r['A'], r['tau'], r['alpha'], r['offset'])
            ax.semilogy(x_fit * diffs_sorted.max(), y_fit, 'r-', lw=2,
                       label=f"KWW $\\alpha$={r['alpha']:.3f}")

        ax.set_xlabel(f'|$\\Delta${label}| ($\\mu$s)')
        ax.set_ylabel('Survival probability')
        ax.set_title(f'{backend} — {label} fluctuations')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(OUT_DIR / 'daqec_fluctuation_dist.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"\nSaved: {OUT_DIR / 'daqec_fluctuation_dist.png'}")


# ═══════════════════════════════════════════════════════════════════════
# ANALYSIS 4: FANO FACTOR TEMPORAL EVOLUTION — KWW fit
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("ANALYSIS 4: FANO FACTOR & ADJACENT CORRELATION vs TIME")
print("=" * 70)

# Fano factor measures deviation from Poisson — its temporal evolution
# may show KWW relaxation

fano_results = []

for backend in ['ibm_brisbane', 'ibm_kyoto', 'ibm_osaka']:
    bdata = master[master['backend'] == backend].sort_values('timestamp_utc').copy()
    t0 = bdata['timestamp_utc'].min()
    bdata['hours'] = (bdata['timestamp_utc'] - t0).dt.total_seconds() / 3600.0

    # Group by timestamp, average Fano factor
    grouped = bdata.groupby('timestamp_utc').agg({
        'fano_factor': 'mean',
        'adjacent_correlation': 'mean',
        'hours': 'first'
    }).sort_index().reset_index()

    for signal_name, col in [('Fano', 'fano_factor'), ('AdjCorr', 'adjacent_correlation')]:
        vals = grouped[col].values
        t_hrs = grouped['hours'].values
        n = len(vals)

        if n < 10:
            continue

        # Compute ACF of the Fano factor time series
        vals_c = vals - np.mean(vals)
        var = np.var(vals)
        if var < 1e-12:
            continue

        max_lag = min(n // 2, 15)
        acf = np.zeros(max_lag)
        for lag in range(max_lag):
            if lag == 0:
                acf[lag] = 1.0
            else:
                acf[lag] = np.mean(vals_c[:n-lag] * vals_c[lag:]) / var

        lags = np.arange(max_lag).astype(float)
        pos_mask = (lags >= 1) & (acf > 0.01)

        if pos_mask.sum() >= 4:
            result = fit_kww(lags[pos_mask], acf[pos_mask],
                           p0=[1.0, 5.0, 1.33, 0.0],
                           bounds=([0, 0.1, 0.1, -0.5], [2, 50, 3.0, 0.5]))
            if result and result['r2'] > 0.3:
                result['backend'] = backend
                result['signal'] = f'ACF_{signal_name}'
                fano_results.append(result)

                status = "IN WINDOW" if result['delta_alpha'] < 0.15 else \
                         "NEAR" if result['delta_alpha'] < 0.25 else "outside"
                print(f"  {backend:15s} ACF_{signal_name}: alpha={result['alpha']:.3f} +/- {result['alpha_err']:.3f}, "
                      f"R2={result['r2']:.4f}, |a-4/3|={result['delta_alpha']:.3f} {status}")

if not fano_results:
    print("  No significant ACF fits for Fano/AdjCorr time series.")


# ═══════════════════════════════════════════════════════════════════════
# ANALYSIS 5: DETRENDED FLUCTUATION ANALYSIS (DFA)
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("ANALYSIS 5: DETRENDED FLUCTUATION ANALYSIS (DFA)")
print("=" * 70)

dfa_results = []

def compute_dfa(series, scales=None):
    """Compute DFA exponent for a time series."""
    n = len(series)
    if scales is None:
        scales = np.unique(np.logspace(0.5, np.log10(n//4), 15).astype(int))
        scales = scales[scales >= 4]

    # Cumulative sum (profile)
    profile = np.cumsum(series - np.mean(series))

    fluctuations = []
    valid_scales = []

    for s in scales:
        n_segments = n // s
        if n_segments < 2:
            continue

        rms_vals = []
        for seg in range(n_segments):
            start = seg * s
            end = start + s
            segment = profile[start:end]
            x = np.arange(s)
            # Linear detrend
            coeffs = np.polyfit(x, segment, 1)
            trend = np.polyval(coeffs, x)
            rms_vals.append(np.sqrt(np.mean((segment - trend)**2)))

        if rms_vals:
            fluctuations.append(np.mean(rms_vals))
            valid_scales.append(s)

    if len(valid_scales) < 3:
        return None

    log_s = np.log(np.array(valid_scales))
    log_f = np.log(np.array(fluctuations))
    slope, intercept, r, p, se = stats.linregress(log_s, log_f)

    return {'dfa_exponent': slope, 'dfa_err': se, 'r2': r**2,
            'scales': np.array(valid_scales), 'fluct': np.array(fluctuations)}

for backend in ['ibm_brisbane', 'ibm_kyoto', 'ibm_osaka']:
    gdata = ts_data[backend]

    for col, label in [('avg_t1_us', 'T1'), ('avg_t2_us', 'T2')]:
        vals = gdata[col].values
        if len(vals) < 16:
            continue

        result = compute_dfa(vals)
        if result:
            # DFA exponent H: H=0.5 white noise, H>0.5 persistent (correlated),
            # H<0.5 anti-persistent. H=1 means 1/f noise.
            # Connection to beta: beta = 2*H - 1 for fractional Gaussian noise
            H = result['dfa_exponent']
            beta_from_H = 2 * H - 1

            dfa_results.append({
                'backend': backend, 'signal': label,
                'H': H, 'H_err': result['dfa_err'], 'r2': result['r2'],
                'beta_from_H': beta_from_H
            })

            classification = "persistent (correlated)" if H > 0.5 else \
                           "anti-persistent" if H < 0.5 else "random walk"
            print(f"  {backend:15s} {label}: H={H:.3f} +/- {result['dfa_err']:.3f}, "
                  f"R2={result['r2']:.4f}, beta_equiv={beta_from_H:.3f} → {classification}")

# ═══════════════════════════════════════════════════════════════════════
# ANALYSIS 6: WITHIN-DAY COHERENCE DECAY SEGMENTS
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("ANALYSIS 6: WITHIN-DAY T1/T2 DECAY SEGMENTS")
print("=" * 70)

# For each day/backend, look at the T1 trajectory within that day
# If T1 decays within a day, fit KWW to each day's decay

day_results = []

for backend in ['ibm_brisbane', 'ibm_kyoto', 'ibm_osaka']:
    bdata = drift[drift['backend'] == backend].copy()
    bdata['timestamp_utc'] = pd.to_datetime(bdata['timestamp_utc'])

    for day in sorted(bdata['day'].unique()):
        ddata = bdata[bdata['day'] == day].sort_values('timestamp_utc')
        if len(ddata) < 5:
            continue

        t0 = ddata['timestamp_utc'].min()
        t_hrs = (ddata['timestamp_utc'] - t0).dt.total_seconds().values / 3600.0

        for col, label in [('avg_t1_us', 'T1'), ('avg_t2_us', 'T2')]:
            vals = ddata[col].values

            if np.std(vals) < 1e-6:
                continue

            # Check if there's a decay trend (negative slope)
            slope_raw, _, r_raw, _, _ = stats.linregress(t_hrs, vals)

            # Normalize
            v_min, v_max = vals.min(), vals.max()
            y_norm = (vals - v_min) / (v_max - v_min + 1e-10)

            result = fit_kww(t_hrs, y_norm)
            if result and result['r2'] > 0.3:
                result['backend'] = backend
                result['signal'] = label
                result['day'] = day
                result['n_points'] = len(vals)
                result['r2_exp'] = fit_exp(t_hrs, y_norm) or 0.0
                result['trend_slope'] = slope_raw
                day_results.append(result)

if day_results:
    day_df = pd.DataFrame(day_results)
    print(f"  Total within-day fits (R2 > 0.3): {len(day_df)}")

    for backend in ['ibm_brisbane', 'ibm_kyoto', 'ibm_osaka']:
        for sig in ['T1', 'T2']:
            sub = day_df[(day_df['backend'] == backend) & (day_df['signal'] == sig)]
            if len(sub) > 0:
                mean_a = sub['alpha'].mean()
                std_a = sub['alpha'].std()
                frac = (sub['delta_alpha'] < 0.15).mean() * 100
                mean_r2k = sub['r2'].mean()
                mean_r2e = sub['r2_exp'].mean()

                status = "IN WINDOW" if abs(mean_a - 4/3) < 0.15 else \
                         "NEAR" if abs(mean_a - 4/3) < 0.25 else ""
                print(f"  {backend:15s} {sig:5s}: N={len(sub):3d}, alpha={mean_a:.3f}+/-{std_a:.3f}, "
                      f"frac_in_window={frac:.0f}%, R2_kww={mean_r2k:.4f}, R2_exp={mean_r2e:.4f} {status}")
else:
    print("  No within-day segments with R2 > 0.3.")


# ═══════════════════════════════════════════════════════════════════════
# ANALYSIS 7: LOGICAL ERROR RATE FLUCTUATION ACF
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("ANALYSIS 7: LOGICAL ERROR RATE FLUCTUATION ACF")
print("=" * 70)

ler_acf_results = []

for backend in ['ibm_brisbane', 'ibm_kyoto', 'ibm_osaka']:
    bdata = master[master['backend'] == backend].sort_values('timestamp_utc')

    for dist in [3, 5, 7]:
        ddata = bdata[bdata['distance'] == dist]

        # Group by timestamp
        grouped = ddata.groupby('timestamp_utc')['logical_error_rate'].mean().sort_index()
        vals = grouped.values
        n = len(vals)

        if n < 15:
            continue

        vals_c = vals - np.mean(vals)
        var = np.var(vals)
        if var < 1e-15:
            continue

        max_lag = min(n // 2, 15)
        acf = np.zeros(max_lag)
        for lag in range(max_lag):
            if lag == 0:
                acf[lag] = 1.0
            else:
                acf[lag] = np.mean(vals_c[:n-lag] * vals_c[lag:]) / var

        lags = np.arange(max_lag).astype(float)
        pos_mask = (lags >= 1) & (acf > 0.01)

        if pos_mask.sum() >= 4:
            result = fit_kww(lags[pos_mask], acf[pos_mask],
                           p0=[1.0, 5.0, 1.33, 0.0],
                           bounds=([0, 0.1, 0.1, -0.5], [2, 50, 3.0, 0.5]))
            if result and result['r2'] > 0.3:
                result['backend'] = backend
                result['signal'] = f'LER_d{dist}_ACF'
                ler_acf_results.append(result)

                status = "IN WINDOW" if result['delta_alpha'] < 0.15 else \
                         "NEAR" if result['delta_alpha'] < 0.25 else ""
                print(f"  {backend:15s} d={dist}: alpha={result['alpha']:.3f} +/- {result['alpha_err']:.3f}, "
                      f"R2={result['r2']:.4f}, |a-4/3|={result['delta_alpha']:.3f} {status}")

if not ler_acf_results:
    print("  No significant LER ACF fits.")


# ═══════════════════════════════════════════════════════════════════════
# AGGREGATE ALL RESULTS
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("AGGREGATE RESULTS — REFINED ANALYSIS")
print("=" * 70)

all_kww = []
for label, rlist in [('ACF_coherence', acf_results),
                      ('Fluctuation_dist', fluct_results),
                      ('Fano_ACF', fano_results),
                      ('Within_day', day_results),
                      ('LER_ACF', ler_acf_results)]:
    for r in rlist:
        r['analysis'] = label
        all_kww.append(r)

if all_kww:
    kww_df = pd.DataFrame(all_kww)

    print(f"\nTotal valid KWW fits (R2 > 0.3): {len(kww_df)}")
    print(f"Mean alpha: {kww_df['alpha'].mean():.4f} +/- {kww_df['alpha'].std():.4f}")
    print(f"Median alpha: {kww_df['alpha'].median():.4f}")
    in_window = (kww_df['delta_alpha'] < 0.15).sum()
    near = (kww_df['delta_alpha'] < 0.25).sum()
    print(f"|alpha - 4/3| < 0.15: {in_window}/{len(kww_df)} ({in_window/len(kww_df)*100:.1f}%)")
    print(f"|alpha - 4/3| < 0.25: {near}/{len(kww_df)} ({near/len(kww_df)*100:.1f}%)")

    if len(kww_df) > 2:
        alphas = kww_df['alpha'].values
        t_43, p_43 = stats.ttest_1samp(alphas, 4/3)
        t_10, p_10 = stats.ttest_1samp(alphas, 1.0)
        print(f"\nt-test vs alpha=4/3: t={t_43:.3f}, p={p_43:.4f}")
        print(f"t-test vs alpha=1.0: t={t_10:.3f}, p={p_10:.4f}")

    # Per-analysis summary
    print(f"\n{'Analysis':20s} {'N':>4s} {'mean_alpha':>11s} {'std':>8s} {'in_window':>10s} {'mean_R2':>8s}")
    for analysis in kww_df['analysis'].unique():
        sub = kww_df[kww_df['analysis'] == analysis]
        if len(sub) > 0:
            print(f"{analysis:20s} {len(sub):4d} {sub['alpha'].mean():11.4f} {sub['alpha'].std():8.4f} "
                  f"{(sub['delta_alpha']<0.15).mean()*100:9.1f}% {sub['r2'].mean():8.4f}")

    kww_df.to_csv(OUT_DIR / 'daqec_refined_kww_results.csv', index=False)
    print(f"\nSaved: {OUT_DIR / 'daqec_refined_kww_results.csv'}")

# PSD results
if psd_results:
    psd_df = pd.DataFrame(psd_results)
    print(f"\nPSD 1/f^beta results:")
    print(f"  Mean beta: {psd_df['beta'].mean():.4f} +/- {psd_df['beta'].std():.4f}")
    for _, row in psd_df.iterrows():
        print(f"  {row['backend']:15s} {row['signal']}: beta={row['beta']:.3f} +/- {row['beta_err']:.3f}, R2={row['r2_psd']:.4f}")

# DFA results
if dfa_results:
    dfa_df = pd.DataFrame(dfa_results)
    print(f"\nDFA Hurst exponent results:")
    print(f"  Mean H: {dfa_df['H'].mean():.4f} +/- {dfa_df['H'].std():.4f}")
    for _, row in dfa_df.iterrows():
        classification = "persistent" if row['H'] > 0.5 else "anti-persistent"
        print(f"  {row['backend']:15s} {row['signal']}: H={row['H']:.3f}, beta_equiv={row['beta_from_H']:.3f} ({classification})")


# ═══════════════════════════════════════════════════════════════════════
# COMPOSITE SUMMARY FIGURE
# ═══════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(2, 3, figsize=(16, 10))
fig.suptitle('DAQEC-Benchmark: IBM Hardware Coherence Analysis Summary\n'
             'Merkabit Research Program — March 2026', fontsize=14)

# Top row: T1/T2 time series for each backend
for i, backend in enumerate(['ibm_brisbane', 'ibm_kyoto', 'ibm_osaka']):
    ax = axes[0, i]
    gdata = ts_data[backend]
    ax.plot(gdata['hours'], gdata['avg_t1_us'], 'o-', ms=3, lw=0.5, color='C0', label='T1')
    ax.plot(gdata['hours'], gdata['avg_t2_us'], 's-', ms=3, lw=0.5, color='C1', label='T2')
    ax.set_xlabel('Hours since start')
    ax.set_ylabel(r'Coherence time ($\mu$s)')
    ax.set_title(backend)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

# Bottom left: Alpha distribution from all valid fits
ax = axes[1, 0]
if all_kww:
    alphas = kww_df['alpha'].values
    ax.hist(alphas, bins=15, color='steelblue', edgecolor='black', alpha=0.7)
    ax.axvline(4/3, color='red', lw=2, ls='--', label=f'$\\alpha = 4/3$')
    ax.axvline(1.0, color='gray', lw=1.5, ls=':', label='$\\alpha = 1$')
    if len(alphas) > 0:
        ax.axvline(np.mean(alphas), color='orange', lw=2, label=f'Mean = {np.mean(alphas):.3f}')
    ax.set_xlabel('KWW exponent $\\alpha$')
    ax.set_ylabel('Count')
    ax.set_title('$\\alpha$ distribution (R$^2$ > 0.3 fits)')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

# Bottom middle: Fano factor vs distance
ax = axes[1, 1]
syn = pd.read_csv(DATA_DIR / "syndrome_statistics.csv")
for k, backend in enumerate(['ibm_brisbane', 'ibm_kyoto', 'ibm_osaka']):
    bsyn = syn[(syn['backend'] == backend) & (syn['strategy'] == 'baseline_static')]
    ax.errorbar(bsyn['distance'], bsyn['fano_factor_mean'], yerr=bsyn['fano_factor_std'],
                marker='o', capsize=3, label=backend, color=f'C{k}')
ax.axhline(1.0, color='gray', ls=':', label='Poisson')
ax.set_xlabel('Code distance d')
ax.set_ylabel('Fano factor')
ax.set_title('Sub-Poissonian syndrome statistics')
ax.legend(fontsize=7)
ax.grid(True, alpha=0.3)

# Bottom right: PSD summary
ax = axes[1, 2]
if psd_results:
    backends_psd = [r['backend'] for r in psd_results]
    signals_psd = [r['signal'] for r in psd_results]
    betas = [r['beta'] for r in psd_results]
    labels_psd = [f"{b.replace('ibm_','')}\n{s}" for b, s in zip(backends_psd, signals_psd)]
    colors = ['C0' if 'T1' in s else 'C1' for s in signals_psd]
    ax.barh(range(len(betas)), betas, color=colors, alpha=0.7, edgecolor='black')
    ax.set_yticks(range(len(labels_psd)))
    ax.set_yticklabels(labels_psd, fontsize=8)
    ax.axvline(0, color='gray', ls=':')
    ax.set_xlabel('PSD exponent $\\beta$ (1/f$^\\beta$)')
    ax.set_title('Noise color: $\\beta$ > 0 = pink/red noise')
    ax.grid(True, alpha=0.3, axis='x')

plt.tight_layout()
plt.savefig(OUT_DIR / 'daqec_summary_figure.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"\nSaved: {OUT_DIR / 'daqec_summary_figure.png'}")


# ═══════════════════════════════════════════════════════════════════════
# FINAL SUMMARY FILE
# ═══════════════════════════════════════════════════════════════════════
lines = []
lines.append("DAQEC-Benchmark: Refined KWW Analysis — IBM Hardware Coherence Drift")
lines.append("=" * 65)
lines.append("Merkabit Research Program — March 2026")
lines.append(f"Data: Zenodo DOI 10.5281/zenodo.17881116")
lines.append(f"Hardware: ibm_brisbane, ibm_kyoto, ibm_osaka (Eagle r3)")
lines.append(f"756 QEC runs, 14 days (2025-01-15 to 2025-01-28)")
lines.append("")
lines.append("KEY FINDINGS:")
lines.append("-" * 40)
lines.append("")
lines.append("1. RAW T1/T2 TIME SERIES: Not monotonic decay — stochastic fluctuation")
lines.append("   (TLS fluctuators). KWW on raw series gives R2 ~ 0. Not appropriate.")
lines.append("")

if acf_results:
    lines.append("2. AUTOCORRELATION DECAY (ACF):")
    for r in acf_results:
        status = "IN WINDOW" if r['delta_alpha'] < 0.15 else "NEAR" if r['delta_alpha'] < 0.25 else ""
        lines.append(f"   {r['backend']} {r['signal']}: alpha={r['alpha']:.3f}+/-{r['alpha_err']:.3f}, "
                     f"R2={r['r2']:.4f}, |a-4/3|={r['delta_alpha']:.3f} {status}")
    lines.append("")

if fluct_results:
    lines.append("3. FLUCTUATION MAGNITUDE DISTRIBUTION:")
    for r in fluct_results:
        status = "IN WINDOW" if r['delta_alpha'] < 0.15 else "NEAR" if r['delta_alpha'] < 0.25 else ""
        lines.append(f"   {r['backend']} {r['signal']}: alpha={r['alpha']:.3f}+/-{r['alpha_err']:.3f}, "
                     f"R2={r['r2']:.4f}, |a-4/3|={r['delta_alpha']:.3f} {status}")
    lines.append("")

if day_results:
    lines.append("4. WITHIN-DAY COHERENCE DECAY SEGMENTS:")
    day_df = pd.DataFrame(day_results)
    for backend in ['ibm_brisbane', 'ibm_kyoto', 'ibm_osaka']:
        for sig in ['T1', 'T2']:
            sub = day_df[(day_df['backend'] == backend) & (day_df['signal'] == sig)]
            if len(sub) > 0:
                lines.append(f"   {backend} {sig}: N={len(sub)}, mean_alpha={sub['alpha'].mean():.3f}+/-{sub['alpha'].std():.3f}, "
                           f"frac_in_window={(sub['delta_alpha']<0.15).mean()*100:.0f}%")
    lines.append("")

if psd_results:
    lines.append("5. POWER SPECTRAL DENSITY (1/f^beta):")
    for r in psd_results:
        lines.append(f"   {r['backend']} {r['signal']}: beta={r['beta']:.3f}+/-{r['beta_err']:.3f}, R2={r['r2_psd']:.4f}")
    lines.append("")

if dfa_results:
    lines.append("6. DFA HURST EXPONENT:")
    for r in dfa_results:
        classification = "persistent" if r['H'] > 0.5 else "anti-persistent"
        lines.append(f"   {r['backend']} {r['signal']}: H={r['H']:.3f}, ({classification})")
    lines.append("")

lines.append("7. SYNDROME STATISTICS:")
lines.append("   Fano factor: 0.83-0.88 across all backends (sub-Poissonian)")
lines.append("   Adjacent correlation: +0.06 to +0.09 (positive spatial correlation)")
lines.append("   Burst count ~ d^1.0 (linear scaling with code distance)")
lines.append("   → Correlated suppression of syndrome events, not independent Poisson")
lines.append("")

summary_final = "\n".join(lines)
with open(OUT_DIR / 'daqec_refined_summary.txt', 'w') as f:
    f.write(summary_final)
print(f"\nSaved: {OUT_DIR / 'daqec_refined_summary.txt'}")
print("\n" + summary_final)
print("\nRefined analysis complete.")
