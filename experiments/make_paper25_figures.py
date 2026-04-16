#!/usr/bin/env python3
"""
Paper 25 Figure Generator — Four of Five
==========================================

Produces figures for Paper 25 from the 9 April 2026 hardware data:

  fig_p25_1_ramsey_berry.png     — P1b Ramsey: forward-reversed difference + Z2 antisymmetry
  fig_p25_2_stroboscopic.png     — P2: P(|00>) oscillation with quasi-period peak at 3.25T
  fig_p25_3_fano_gap.png         — Tau=5 Fano gap + per-round stability
  fig_p25_4_scorecard.png        — Appendix N scorecard: 4 of 5 confirmed

Data sources:
  outputs/p1_ramsey/p1_ramsey_ibm_strasbourg_20260409_121917.json
  outputs/p2_stroboscopic/p2_strobo_ibm_strasbourg_20260409_133950.json
  outputs/rotation_gap/rotation_gap_ibm_strasbourg_20260409_112127.json
"""

import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).parent.parent
OUTPUTS = ROOT / "outputs"
FIG_DIR = Path("C:/Users/selin/OneDrive/Desktop/24+25")

plt.rcParams.update({
    "font.family":      "DejaVu Sans",
    "font.size":        11,
    "axes.titlesize":   13,
    "axes.labelsize":   11,
    "xtick.labelsize":  10,
    "ytick.labelsize":  10,
    "legend.fontsize":  10,
    "figure.titlesize": 14,
    "axes.grid":        True,
    "grid.alpha":       0.3,
    "axes.axisbelow":   True,
    "savefig.dpi":      150,
    "savefig.bbox":     "tight",
})

C_HW      = "#1a7fb8"
C_IDEAL   = "#888888"
C_PAIRED  = "#1a7fb8"
C_CTRL    = "#d66b3a"
C_GOOD    = "#2e8b57"
C_PENDING = "#cc3333"
C_PEAK    = "#cc3333"


# ── Figure 1: P1b Ramsey Berry Phase ─────────────────────────────────────

def fig1_ramsey(p1_data):
    sweep = p1_data["sweep"]
    ns = [e["n_steps"] for e in sweep]
    z_fwd_diff = [e["z_fwd_diff"] for e in sweep]
    z_inv_diff = [e["z_inv_diff"] for e in sweep]
    asym_sum = [e["z_fwd_diff"] + e["z_inv_diff"] for e in sweep]

    # Compute ideal differences from the fwd/rev Z values
    # We need ideal — extract from the simulation data if available
    # For now use the known ideal values from Paper 3
    ideal_diff = {1: -0.0537, 2: -0.2937, 3: -0.4558, 4: -0.5557,
                  6: -0.2087, 8: +1.1375, 10: +1.4861, 12: +0.1564}

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # (a) Forward spinor difference: hw vs ideal
    ax = axes[0]
    ideal_ns = sorted(ideal_diff.keys())
    ideal_vals = [ideal_diff[n] for n in ideal_ns]
    ax.plot(ideal_ns, ideal_vals, "o--", color=C_IDEAL, markersize=8,
            linewidth=2, label="ideal", zorder=2)
    ax.plot(ns, z_fwd_diff, "s-", color=C_HW, markersize=10,
            linewidth=2.5, label="hardware", zorder=3)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="-")
    ax.axvspan(6, 8, alpha=0.15, color=C_PEAK, label="sign flip region")
    ax.set_xlabel("Ouroboros steps n")
    ax.set_ylabel(r"$\Delta\langle Z_+\rangle$ (fwd $-$ rev)")
    ax.set_title(r"(a) Berry phase: $\Delta\langle Z_+\rangle$")
    ax.legend(loc="upper left", fontsize=9)
    ax.set_xticks(ns)
    ax.set_ylim(-0.8, 1.7)
    # Annotate sign flip
    ax.annotate("sign flip", xy=(7, 0.4), fontsize=10, color=C_PEAK,
                fontweight="bold", ha="center")

    # (b) Z2 antisymmetry: fwd_diff vs -inv_diff
    ax = axes[1]
    ax.plot(ns, z_fwd_diff, "s-", color=C_HW, markersize=9,
            linewidth=2, label=r"$\Delta\langle Z_+\rangle$")
    ax.plot(ns, [-x for x in z_inv_diff], "^--", color=C_GOOD, markersize=9,
            linewidth=2, label=r"$-\Delta\langle Z_-\rangle$")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Ouroboros steps n")
    ax.set_ylabel("Value")
    ax.set_title(r"(b) $Z_2$ antisymmetry")
    ax.legend(loc="upper left", fontsize=9)
    ax.set_xticks(ns)

    # (c) Antisymmetry residual (sum should be ~0)
    ax = axes[2]
    ax.bar(ns, asym_sum, color=C_HW, edgecolor="black", width=0.6)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.axhspan(-0.05, 0.05, alpha=0.1, color=C_GOOD, label="shot noise band")
    ax.set_xlabel("Ouroboros steps n")
    ax.set_ylabel(r"$\Delta\langle Z_+\rangle + \Delta\langle Z_-\rangle$")
    ax.set_title(r"(c) Antisymmetry residual ($\approx 0$)")
    ax.set_xticks(ns)
    ax.set_ylim(-0.08, 0.08)
    ax.legend(fontsize=9)
    for n, v in zip(ns, asym_sum):
        ax.text(n, v + 0.005 * np.sign(v) + 0.003, f"{v:+.003f}",
                ha="center", fontsize=8, rotation=45)

    fig.suptitle("Figure 1 \u2014 P1 Ramsey Berry Phase (zero CX, depth 6, ibm_strasbourg 9 April 2026)",
                 fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    path = FIG_DIR / "fig_p25_1_ramsey_berry.png"
    plt.savefig(path)
    plt.close()
    print(f"  saved {path}")


# ── Figure 2: P2 Stroboscopic Quasi-Period ────────────────────────────────

def fig2_stroboscopic(p2_data):
    sweep = p2_data["sweep"]
    ns = [e["n_steps"] for e in sweep]
    p_hw = [e["p_return_hw"] for e in sweep]
    p_ideal = [e["p_return_ideal"] for e in sweep]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    # (a) P(|00>) vs n: hardware and ideal
    ax = axes[0]
    ax.plot(ns, p_ideal, "o-", color=C_IDEAL, markersize=5, linewidth=1.5,
            label="ideal", alpha=0.7, zorder=2)
    ax.plot(ns, p_hw, "s-", color=C_HW, markersize=7, linewidth=2,
            label="hardware", zorder=3)
    # Mark quasi-period peaks
    peaks_n = [39, 57]
    for pn in peaks_n:
        idx = ns.index(pn)
        ax.plot(pn, p_hw[idx], "D", color=C_PEAK, markersize=14,
                markeredgecolor="black", markeredgewidth=1.5, zorder=4)
    ax.annotate("3.25T", xy=(39, 0.890), xytext=(42, 0.82),
                fontsize=12, fontweight="bold", color=C_PEAK,
                arrowprops=dict(arrowstyle="->", color=C_PEAK, lw=2))
    ax.annotate("4.75T", xy=(57, 0.901), xytext=(53, 0.82),
                fontsize=11, fontweight="bold", color=C_PEAK,
                arrowprops=dict(arrowstyle="->", color=C_PEAK, lw=2))
    # Predicted quasi-period line
    ax.axvline(39.6, color=C_PEAK, linestyle=":", linewidth=1.5,
               label="predicted 3.3T = 39.6", alpha=0.7)
    ax.axhline(0.25, color="gray", linestyle="--", linewidth=1,
               label="dephasing limit (0.25)")
    ax.set_xlabel("Ouroboros steps n")
    ax.set_ylabel(r"$P(|00\rangle)$")
    ax.set_title(r"(a) Stroboscopic return probability $P(|00\rangle)$")
    ax.legend(loc="lower left", fontsize=9)
    ax.set_xlim(0, 61)
    ax.set_ylim(0.55, 0.96)

    # (b) Fidelity (hw/ideal) vs n
    ax = axes[1]
    fidelity = [h / i * 100 if i > 0 else 0 for h, i in zip(p_hw, p_ideal)]
    ax.plot(ns, fidelity, "s-", color=C_GOOD, markersize=6, linewidth=2)
    ax.axhline(100, color="black", linewidth=0.8, linestyle="-")
    ax.axhspan(96, 100, alpha=0.1, color=C_GOOD)
    ax.set_xlabel("Ouroboros steps n")
    ax.set_ylabel("Fidelity (%)")
    ax.set_title("(b) Hardware / ideal fidelity")
    ax.set_xlim(0, 61)
    ax.set_ylim(94, 101)
    mean_fid = np.mean(fidelity)
    ax.axhline(mean_fid, color=C_HW, linestyle="--", linewidth=1.5,
               label=f"mean = {mean_fid:.1f}%")
    ax.legend(fontsize=10, loc="lower left")

    fig.suptitle("Figure 2 \u2014 P2 Stroboscopic Quasi-Period (zero CX, depth 6, ibm_strasbourg 9 April 2026)",
                 fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    path = FIG_DIR / "fig_p25_2_stroboscopic.png"
    plt.savefig(path)
    plt.close()
    print(f"  saved {path}")


# ── Figure 3: Tau=5 Fano Gap ─────────────────────────────────────────────

def fig3_fano_gap(t5_data):
    paired = t5_data["results"]["paired_tau5"]
    control = t5_data["results"]["unpaired_tau5"]

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # (a) Fano comparison across tau (include Paper 24 values)
    ax = axes[0]
    taus = [1, 3, 5]
    paired_fanos = [0.654, 0.871, paired["fano_factor"]]
    ctrl_fanos = [0.613, 0.600, control["fano_factor"]]
    x = np.arange(len(taus))
    w = 0.35
    ax.bar(x - w/2, paired_fanos, w, color=C_PAIRED, edgecolor="black",
           label="Paired (merkabit)")
    ax.bar(x + w/2, ctrl_fanos, w, color=C_CTRL, edgecolor="black",
           label="Control (unpaired)")
    ax.axhline(1.0, color=C_PENDING, linestyle="--", linewidth=1.5,
               label="Poisson (F=1)")
    ax.set_xticks(x)
    ax.set_xticklabels([f"\u03c4={t}" for t in taus])
    ax.set_ylabel("Fano factor")
    ax.set_title("(a) Fano: paired vs control across \u03c4")
    ax.legend(fontsize=9, loc="upper left")
    ax.set_ylim(0, 1.1)
    for i, (p, c) in enumerate(zip(paired_fanos, ctrl_fanos)):
        ax.text(i - w/2, p + 0.02, f"{p:.3f}", ha="center", fontsize=9)
        ax.text(i + w/2, c + 0.02, f"{c:.3f}", ha="center", fontsize=9)
    # Arrow showing crossover at tau=5
    ax.annotate("paired < control", xy=(2, 0.506), xytext=(1.5, 0.3),
                fontsize=10, fontweight="bold", color=C_PAIRED,
                arrowprops=dict(arrowstyle="->", color=C_PAIRED, lw=2))

    # (b) Per-round Fano at tau=5
    ax = axes[1]
    pr = paired["per_round_fano"]
    rounds = np.arange(1, len(pr) + 1)
    ax.plot(rounds, pr, "o-", color=C_PAIRED, markersize=12,
            linewidth=2.5, markeredgecolor="black", markeredgewidth=1)
    ax.axhline(1.0, color=C_PENDING, linestyle="--", linewidth=1.5,
               label="Poisson (F=1)")
    ax.axhline(np.mean(pr), color=C_GOOD, linestyle="-", linewidth=2,
               label=f"mean = {np.mean(pr):.3f}")
    ax.fill_between(rounds, np.mean(pr) - np.std(pr),
                     np.mean(pr) + np.std(pr), alpha=0.2, color=C_GOOD)
    ax.set_xlabel("Syndrome round")
    ax.set_ylabel("Per-round Fano")
    ax.set_title("(b) Per-round Fano at \u03c4=5 (paired)")
    ax.set_xticks(rounds)
    ax.set_ylim(0.40, 1.05)
    ax.legend(fontsize=9)
    for r, f in zip(rounds, pr):
        ax.text(r, f + 0.015, f"{f:.3f}", ha="center", fontsize=9)

    # (c) Edge fire rates at tau=5
    ax = axes[2]
    edges = paired["edge_fire_rates"]
    labels = ["(0,1)\nmixed", "(0,2)\nmixed", "(1,2)\ncounter-rot."]
    colors = [C_HW, C_HW, C_PEAK]
    bars = ax.bar(labels, edges, color=colors, edgecolor="black", width=0.5)
    ax.axhline(0.5, color="gray", linestyle="--", linewidth=1, alpha=0.5)
    ax.set_ylabel("Edge fire rate")
    ax.set_title("(c) Edge fire rates at \u03c4=5")
    ax.set_ylim(0.45, 0.53)
    for i, v in enumerate(edges):
        ax.text(i, v + 0.002, f"{v:.3f}", ha="center", fontsize=10,
                fontweight="bold")

    fig.suptitle("Figure 3 \u2014 Tau=5 Rotation Gap (9 qubits, depth 279, 108 CX, ibm_strasbourg 9 April 2026)",
                 fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    path = FIG_DIR / "fig_p25_3_fano_gap.png"
    plt.savefig(path)
    plt.close()
    print(f"  saved {path}")


# ── Figure 4: Appendix N Scorecard ───────────────────────────────────────

def fig4_scorecard():
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.axis("off")

    preds = [
        ("P1", "Berry phase\nsign flip + peak + closure", "Confirmed", "Paper 25 \u00a72",
         "sign flip n=6\u21928 \u2713\npeak n=10 (96%) \u2713\nreturn n=12 \u2713", True),
        ("P2", "Quasi-period\n3.3T \u00b1 0.3T", "Confirmed", "Paper 25 \u00a73",
         "peak at n=39 = 3.25T\n97.9% fidelity", True),
        ("P3", "Z\u2082 symmetry\n< 5% deviation", "Confirmed", "Paper 24 \u00a74",
         "mean error 0.016", True),
        ("P4", "Centre detection\n91% \u00b1 5%", "Exceeded", "Paper 24 \u00a76",
         "99.3% (+8.3 pp\nabove central)", True),
        ("P5", "DTC robustness\namplitude > 0.3", "Pending", "\u2014",
         "\u2014", False),
    ]

    col_x = [0.03, 0.12, 0.35, 0.55, 0.72, 0.92]
    headers = ["ID", "Prediction", "Result", "Source", "Measured", ""]

    # Header
    for x, h in zip(col_x, headers):
        ax.text(x, 0.95, h, transform=ax.transAxes, fontsize=11,
                fontweight="bold", va="top", ha="left")
    ax.plot([0.02, 0.98], [0.91, 0.91], color="black", linewidth=1.5,
            transform=ax.transAxes, clip_on=False)

    for i, (pid, pred, result, source, measured, confirmed) in enumerate(preds):
        y = 0.85 - i * 0.17
        bg_color = "#e8f5e9" if confirmed else "#fff3e0"
        rect = plt.Rectangle((0.02, y - 0.06), 0.96, 0.15,
                              transform=ax.transAxes, facecolor=bg_color,
                              edgecolor="#cccccc", linewidth=0.5, zorder=0)
        ax.add_patch(rect)

        result_color = C_GOOD if confirmed else C_PENDING
        check = "\u2713" if confirmed else "\u2717"

        ax.text(col_x[0], y, pid, transform=ax.transAxes, fontsize=12,
                fontweight="bold", va="center")
        ax.text(col_x[1], y, pred, transform=ax.transAxes, fontsize=9,
                va="center")
        ax.text(col_x[2], y, f"{check} {result}", transform=ax.transAxes,
                fontsize=11, fontweight="bold", va="center", color=result_color)
        ax.text(col_x[3], y, source, transform=ax.transAxes, fontsize=9,
                va="center")
        ax.text(col_x[4], y, measured, transform=ax.transAxes, fontsize=9,
                va="center")

    ax.text(0.5, 0.02, "Four of five Appendix N predictions retired on IBM hardware within one week (6\u20139 April 2026)",
            transform=ax.transAxes, fontsize=12, fontweight="bold",
            ha="center", va="bottom",
            bbox=dict(facecolor="#e8f5e9", edgecolor=C_GOOD,
                      boxstyle="round,pad=0.4"))

    fig.suptitle("Figure 4 \u2014 Paper 3 Appendix N Scorecard", fontweight="bold", fontsize=14)
    path = FIG_DIR / "fig_p25_4_scorecard.png"
    plt.savefig(path)
    plt.close()
    print(f"  saved {path}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print(f"\n== Paper 25 Figure Generator ==")
    print(f"Output: {FIG_DIR}\n")

    p1 = json.loads((OUTPUTS / "p1_ramsey/p1_ramsey_ibm_strasbourg_20260409_121917.json").read_text())
    p2 = json.loads((OUTPUTS / "p2_stroboscopic/p2_strobo_ibm_strasbourg_20260409_133950.json").read_text())
    t5 = json.loads((OUTPUTS / "rotation_gap/rotation_gap_ibm_strasbourg_20260409_112127.json").read_text())

    print("Generating figures:")
    fig1_ramsey(p1)
    fig2_stroboscopic(p2)
    fig3_fano_gap(t5)
    fig4_scorecard()

    print("\nDone. Four figures saved.")


if __name__ == "__main__":
    main()
