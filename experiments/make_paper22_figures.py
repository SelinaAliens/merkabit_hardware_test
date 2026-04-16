#!/usr/bin/env python3
"""
Paper 22 Figure Generator — The Cosmological Constant
=====================================================

Produces five figures for Paper 22 from the stated results:

  fig_p22_1_structural_identity.png  — How |B₃₁|=31 produces both α⁻¹ and γ_Berry
  fig_p22_2_monopole_decay.png       — Three monopole types: lifetime, force, decay
  fig_p22_3_lambda_convergence.png   — QFT vs framework vs observed (120 orders of magnitude)
  fig_p22_4_coxeter_expansion.png    — Parallel Coxeter expansions for α⁻¹ and γ_Berry
  fig_p22_5_constants_deviation.png  — All 9 derived constants: deviation from measurement
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
from pathlib import Path

FIG_DIR = Path("C:/Users/selin/OneDrive/Desktop/New Paper 20-23")

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "figure.titlesize": 14,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.axisbelow": True,
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
})

C_E6 = "#1a7fb8"
C_PSL = "#2e8b57"
C_MATTER = "#cc3333"
C_FRAMEWORK = "#1a7fb8"
C_QFT = "#cc3333"
C_OBSERVED = "#2e8b57"
C_GOLD = "#d4a017"


# ── Figure 1: Structural Identity ────────────────────────────────────────

def fig1_structural_identity():
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 8)
    ax.axis("off")

    # Title
    ax.text(6, 7.5, "The Shared Root: |B\u2083\u2081| = 31",
            ha="center", fontsize=16, fontweight="bold")
    ax.text(6, 7.0, "Both constants measure the non-matter content of the geometry",
            ha="center", fontsize=11, style="italic", color="#555555")

    # Left branch: PSL(2,7) → α⁻¹
    box_psl = FancyBboxPatch((0.5, 5.2), 4.5, 1.2, boxstyle="round,pad=0.15",
                              facecolor="#e8f5e9", edgecolor=C_PSL, linewidth=2)
    ax.add_patch(box_psl)
    ax.text(2.75, 5.95, "PSL(2,7)", ha="center", fontsize=14, fontweight="bold", color=C_PSL)
    ax.text(2.75, 5.45, "168 group elements", ha="center", fontsize=11)

    # Right branch: E₆ → γ_Berry
    box_e6 = FancyBboxPatch((7, 5.2), 4.5, 1.2, boxstyle="round,pad=0.15",
                             facecolor="#e3f2fd", edgecolor=C_E6, linewidth=2)
    ax.add_patch(box_e6)
    ax.text(9.25, 5.95, "E\u2086", ha="center", fontsize=14, fontweight="bold", color=C_E6)
    ax.text(9.25, 5.45, "78 Lie algebra dimensions", ha="center", fontsize=11)

    # Centre: B₃₁ = 31 (matter sector)
    box_matter = FancyBboxPatch((4, 3.5), 4, 1.0, boxstyle="round,pad=0.15",
                                 facecolor="#ffebee", edgecolor=C_MATTER, linewidth=2.5)
    ax.add_patch(box_matter)
    ax.text(6, 4.15, "|B\u2083\u2081| = 31", ha="center", fontsize=15, fontweight="bold", color=C_MATTER)
    ax.text(6, 3.7, "matter sector (subtracted from both)", ha="center", fontsize=10)

    # Arrows from B₃₁ to both
    ax.annotate("", xy=(2.75, 5.2), xytext=(5, 4.5),
                arrowprops=dict(arrowstyle="-|>", color=C_MATTER, lw=2))
    ax.annotate("", xy=(9.25, 5.2), xytext=(7, 4.5),
                arrowprops=dict(arrowstyle="-|>", color=C_MATTER, lw=2))

    # Left result: 168 - 31 = 137
    ax.text(2.75, 4.7, "\u2212 31", ha="center", fontsize=12, fontweight="bold", color=C_MATTER)

    box_alpha = FancyBboxPatch((0.8, 1.5), 3.9, 1.5, boxstyle="round,pad=0.15",
                                facecolor="#c8e6c9", edgecolor=C_PSL, linewidth=2)
    ax.add_patch(box_alpha)
    ax.text(2.75, 2.55, "168 \u2212 31 = 137", ha="center", fontsize=13, fontweight="bold")
    ax.text(2.75, 2.05, "\u03B1\u207B\u00B9 = 137.036...", ha="center", fontsize=12, color=C_PSL)
    ax.text(2.75, 1.65, "strength of light", ha="center", fontsize=10, style="italic")

    ax.annotate("", xy=(2.75, 3.0), xytext=(2.75, 3.5),
                arrowprops=dict(arrowstyle="-|>", color=C_PSL, lw=2.5))

    # Right result: (78-31)/(78-28) = 47/50
    ax.text(9.25, 4.7, "\u2212 31", ha="center", fontsize=12, fontweight="bold", color=C_MATTER)

    box_gamma = FancyBboxPatch((7.3, 1.5), 3.9, 1.5, boxstyle="round,pad=0.15",
                                facecolor="#bbdefb", edgecolor=C_E6, linewidth=2)
    ax.add_patch(box_gamma)
    ax.text(9.25, 2.55, "(78\u221231) / (78\u221228) = 47/50", ha="center", fontsize=13, fontweight="bold")
    ax.text(9.25, 2.05, "\u03B3_Berry = 0.940", ha="center", fontsize=12, color=C_E6)
    ax.text(9.25, 1.65, "rate of expansion", ha="center", fontsize=10, style="italic")

    ax.annotate("", xy=(9.25, 3.0), xytext=(9.25, 3.5),
                arrowprops=dict(arrowstyle="-|>", color=C_E6, lw=2.5))

    # Additional note: D₄ = 28
    ax.text(10.8, 4.3, "D\u2084 = 28\n(triality)", ha="center", fontsize=9,
            color="#666666", style="italic")

    # Bottom: the unifying statement
    box_bottom = FancyBboxPatch((1.5, 0.2), 9, 0.9, boxstyle="round,pad=0.15",
                                 facecolor="#fff9c4", edgecolor=C_GOLD, linewidth=2)
    ax.add_patch(box_bottom)
    ax.text(6, 0.65, "Both constants subtract the same 31 from different totals: "
            "the part of the geometry that is not matter",
            ha="center", fontsize=11, fontweight="bold", color="#555555")

    path = FIG_DIR / "fig_p22_1_structural_identity.png"
    plt.savefig(path)
    plt.close()
    print(f"  saved {path}")


# ── Figure 2: Monopole Decay ─────────────────────────────────────────────

def fig2_monopole_decay():
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))

    types = ["Type A\n(v = 0)", "Type B\n(v = u)", "Type C\n(h' = 7)"]
    lifetimes = [1, 3, 4]
    forces = [0.10, 0.12, 0.04]
    radiation = ["Isotropic\n(l = 0)", "Isotropic\n(l = 0)", "Beat-\nfrequency"]
    colors = [C_QFT, "#e67e22", C_GOLD]
    descriptions = ["Single spinor\nonly", "Locked spinors\n(no counter-rot.)", "Wrong Coxeter\nperiod (h'=7)"]

    # (a) Lifetime
    ax = axes[0]
    bars = ax.bar(types, lifetimes, color=colors, edgecolor="black", width=0.6)
    ax.set_ylabel("Lifetime (Coxeter cycles)")
    ax.set_title("(a) Monopole lifetime")
    ax.set_ylim(0, 5.5)
    for i, (t, l) in enumerate(zip(types, lifetimes)):
        ax.text(i, l + 0.15, f"{l} cycle{'s' if l > 1 else ''}", ha="center",
                fontsize=11, fontweight="bold")
        ax.text(i, -0.7, descriptions[i], ha="center", fontsize=8,
                color="#555555", style="italic")

    # (b) Force on bipartite matter
    ax = axes[1]
    bars = ax.bar(types, forces, color=colors, edgecolor="black", width=0.6)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("Probe drift (repulsive)")
    ax.set_title("(b) Force on bipartite matter")
    ax.set_ylim(-0.02, 0.16)
    for i, f in enumerate(forces):
        ax.text(i, f + 0.005, f"+{f:.2f}", ha="center", fontsize=11, fontweight="bold")
    ax.text(2.5, 0.14, "All repulsive\n= dark energy", ha="center", fontsize=10,
            color=C_QFT, fontweight="bold",
            bbox=dict(facecolor="#ffebee", edgecolor=C_QFT, boxstyle="round,pad=0.3"))

    # (c) Radiation pattern
    ax = axes[2]
    # Draw simple radiation diagrams
    for i, (t, r) in enumerate(zip(types, radiation)):
        y_center = 2 - i * 0.8
        ax.text(0.3, y_center, t.replace("\n", " "), fontsize=10, va="center",
                fontweight="bold", color=colors[i])
        ax.text(2.5, y_center, r.replace("\n", " "), fontsize=10, va="center",
                ha="center")
        # Draw circles for isotropic
        if "Isotropic" in r:
            circle = plt.Circle((4.2, y_center), 0.25, fill=False,
                                edgecolor=colors[i], linewidth=2)
            ax.add_patch(circle)
            ax.plot(4.2, y_center, "o", color=colors[i], markersize=5)
        else:
            # Wavy line for beat frequency
            x_wave = np.linspace(3.7, 4.7, 50)
            y_wave = y_center + 0.15 * np.sin(x_wave * 15)
            ax.plot(x_wave, y_wave, color=colors[i], linewidth=2)

    ax.set_xlim(-0.2, 5)
    ax.set_ylim(-0.2, 2.8)
    ax.set_title("(c) Decay radiation")
    ax.axis("off")

    fig.suptitle("Figure 2 \u2014 Torsion monopoles: all unstable, all repulsive, all dark energy",
                 fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.93])
    path = FIG_DIR / "fig_p22_2_monopole_decay.png"
    plt.savefig(path)
    plt.close()
    print(f"  saved {path}")


# ── Figure 3: Λ Convergence ──────────────────────────────────────────────

def fig3_lambda_convergence():
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # (a) The 10^120 gap
    ax = axes[0]
    categories = ["QFT\nprediction", "Leading\n(47/50)", "Two-term\n(+2\u03C0/936\u00B2)", "Observed\n(Planck 2018)"]
    log_values = [np.log10(1e-2), np.log10(2.876e-122), np.log10(2.870e-122), np.log10(2.87e-122)]
    colors_bar = [C_QFT, C_FRAMEWORK, C_FRAMEWORK, C_OBSERVED]
    alphas = [0.7, 0.5, 0.9, 0.9]

    for i, (lv, cb) in enumerate(zip(log_values, colors_bar)):
        al = [0.7, 0.5, 0.9, 0.9][i]
        ax.barh(i, lv, color=cb, edgecolor="black", height=0.5, alpha=al)
    ax.set_yticks(range(len(categories)))
    ax.set_yticklabels(categories, fontsize=11)
    ax.set_xlabel("log\u2081\u2080(\u039B) in Planck units")
    ax.set_title("(a) The cosmological constant problem \u2014 and its resolution")
    ax.set_xlim(-135, 5)

    # Labels
    ax.text(log_values[0] + 1, 0, "~10\u207B\u00B2", va="center", fontsize=10,
            fontweight="bold", color=C_QFT)
    ax.text(-60, 1, "2.876 \u00D7 10\u207B\u00B9\u00B2\u00B2", va="center", fontsize=9,
            fontweight="bold", color=C_FRAMEWORK)
    ax.text(-60, 2, "2.870 \u00D7 10\u207B\u00B9\u00B2\u00B2", va="center", fontsize=9,
            fontweight="bold", color=C_FRAMEWORK)
    ax.text(-60, 3, "2.87 \u00D7 10\u207B\u00B9\u00B2\u00B2", va="center", fontsize=9,
            fontweight="bold", color=C_OBSERVED)

    # Gap annotation
    ax.annotate("", xy=(-2, 0.3), xytext=(-122, 0.3),
                arrowprops=dict(arrowstyle="<->", color=C_QFT, lw=2))
    ax.text(-62, 0.5, "120 orders of magnitude", ha="center", fontsize=11,
            fontweight="bold", color=C_QFT)

    # (b) Zoom on the framework values
    ax = axes[1]
    terms = ["Leading\n(47/50 only)", "Two-term\n(+2\u03C0/936\u00B2)", "Observed"]
    values = [2.876e-122, 2.870e-122, 2.87e-122]
    ratios = [v / 2.87e-122 for v in values]
    colors_zoom = [C_FRAMEWORK, C_FRAMEWORK, C_OBSERVED]

    for i, (t, r, cz) in enumerate(zip(terms, ratios, colors_zoom)):
        al = [0.5, 0.9, 0.9][i]
        ax.bar(t, r, color=cz, edgecolor="black", width=0.5, alpha=al)
    ax.axhline(1.0, color="black", linewidth=1.5, linestyle="--", label="Observed = 1.000")
    ax.set_ylabel("Derived / Observed")
    ax.set_title("(b) Convergence to 0.01% accuracy")
    ax.set_ylim(0.995, 1.005)

    for i, (r, v) in enumerate(zip(ratios, values)):
        pct = (r - 1) * 100
        ax.text(i, r + 0.0005, f"{r:.4f}\n({pct:+.2f}%)", ha="center",
                fontsize=10, fontweight="bold")

    ax.legend(fontsize=10, loc="upper right")

    fig.suptitle("Figure 3 \u2014 The cosmological constant: from 10\u00B9\u00B2\u2070 discrepancy to 0.01% agreement",
                 fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.93])
    path = FIG_DIR / "fig_p22_3_lambda_convergence.png"
    plt.savefig(path)
    plt.close()
    print(f"  saved {path}")


# ── Figure 4: Parallel Coxeter Expansions ─────────────────────────────────

def fig4_coxeter_expansion():
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 8)
    ax.axis("off")

    ax.text(6, 7.5, "Parallel Coxeter Expansions from |B\u2083\u2081| = 31",
            ha="center", fontsize=15, fontweight="bold")

    # Left column: α⁻¹
    col_l = 3.0
    ax.text(col_l, 6.7, "\u03B1\u207B\u00B9 (fine structure)", ha="center",
            fontsize=13, fontweight="bold", color=C_PSL)

    rows_l = [
        ("Leading term:", "137 = 168 \u2212 31", 6.0),
        ("Source:", "PSL(2,7) \u2212 |B\u2083\u2081|", 5.5),
        ("Expansion param:", "V = 10", 4.8),
        ("Sub-leading:", "+36/10\u00B3 = +0.036", 4.3),
        ("Sub-sub-leading:", "\u2212(11/12)/10\u2076", 3.8),
        ("Result:", "137.035999", 3.1),
        ("Measured:", "137.035999", 2.6),
        ("Accuracy:", "< 0.0001%", 2.1),
    ]
    for label, value, y in rows_l:
        ax.text(col_l - 1.8, y, label, fontsize=10, ha="right", color="#555555")
        ax.text(col_l - 1.6, y, value, fontsize=10, ha="left",
                fontweight="bold" if "Result" in label or "Accuracy" in label else "normal",
                color=C_PSL if "Result" in label else "black")

    # Right column: γ_Berry
    col_r = 9.0
    ax.text(col_r, 6.7, "\u03B3_Berry (Berry coupling)", ha="center",
            fontsize=13, fontweight="bold", color=C_E6)

    rows_r = [
        ("Leading term:", "47/50 = 0.940", 6.0),
        ("Source:", "(dim(E\u2086)\u2212|B\u2083\u2081|)/(dim(E\u2086)\u2212dim(D\u2084))", 5.5),
        ("Expansion param:", "V = 936 = 12\u00D76\u00D713", 4.8),
        ("Sub-leading:", "+2\u03C0/936\u00B2 = +7.2\u00D710\u207B\u2076", 4.3),
        ("Sub-sub-leading:", "...", 3.8),
        ("Result:", "0.940007", 3.1),
        ("Simulation:", "0.940007", 2.6),
        ("Accuracy:", "3.7 \u00D7 10\u207B\u2077", 2.1),
    ]
    for label, value, y in rows_r:
        ax.text(col_r - 1.8, y, label, fontsize=10, ha="right", color="#555555")
        ax.text(col_r - 1.6, y, value, fontsize=10, ha="left",
                fontweight="bold" if "Result" in label or "Accuracy" in label else "normal",
                color=C_E6 if "Result" in label else "black")

    # Centre dividing line
    ax.plot([6, 6], [1.8, 6.5], color="#cccccc", linewidth=1.5, linestyle="--")

    # Shared root at bottom
    box = FancyBboxPatch((2, 0.5), 8, 1.0, boxstyle="round,pad=0.15",
                          facecolor="#ffebee", edgecolor=C_MATTER, linewidth=2)
    ax.add_patch(box)
    ax.text(6, 1.0, "Shared root: |B\u2083\u2081| = 31 (matter sector cardinality)",
            ha="center", fontsize=12, fontweight="bold", color=C_MATTER)

    # Arrows from shared root up
    ax.annotate("", xy=(col_l, 2.0), xytext=(5, 1.5),
                arrowprops=dict(arrowstyle="-|>", color=C_MATTER, lw=1.5))
    ax.annotate("", xy=(col_r, 2.0), xytext=(7, 1.5),
                arrowprops=dict(arrowstyle="-|>", color=C_MATTER, lw=1.5))

    path = FIG_DIR / "fig_p22_4_coxeter_expansion.png"
    plt.savefig(path)
    plt.close()
    print(f"  saved {path}")


# ── Figure 5: All Constants Deviation Plot ────────────────────────────────

def fig5_constants_deviation():
    # a_g has 33% deviation — completely different scale from the rest.
    # Show 8 constants on the main plot; note a_g separately.
    constants = [
        ("alpha^-1", 137.035999, 137.035999, "<0.0001%"),
        ("alpha_s", 0.11798, 0.11800, "0.02 sigma"),
        ("sin^2 theta_W", 0.23077, 0.23122, "0.19%"),
        ("m_W", 80.40, 80.377, "0.03%"),
        ("v (Higgs)", 246.3, 246.22, "0.05%"),
        ("G_eff", 0.2500, 0.2542, "1.7%"),
        ("k (bending)", 4.000, 4.000, "exact"),
        ("Lambda", 2.876e-122, 2.87e-122, "0.2%"),
    ]

    names = [c[0] for c in constants]
    deviations_pct = [(c[1] / c[2] - 1) * 100 for c in constants]
    accuracies = [c[3] for c in constants]

    colors = []
    for a in accuracies:
        if "exact" in a or "<0.0001" in a:
            colors.append(C_OBSERVED)
        elif "0.02" in a or "0.03" in a or "0.05" in a or "0.19" in a or "0.2%" in a:
            colors.append(C_FRAMEWORK)
        else:
            colors.append(C_GOLD)

    fig = plt.figure(figsize=(7, 6))
    ax = fig.add_axes([0.22, 0.10, 0.72, 0.78])

    y_pos = np.arange(len(constants))
    for i, (d, col) in enumerate(zip(deviations_pct, colors)):
        ax.barh(i, d, color=col, edgecolor="black", height=0.6, alpha=0.85)

    ax.axvline(0, color="black", linewidth=2)
    ax.axvspan(-0.1, 0.1, alpha=0.08, color=C_OBSERVED)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=11)
    ax.set_xlabel("Deviation from measured value (%)", fontsize=11)
    ax.set_title("Eight constants, zero free parameters:\nderived vs measured",
                 fontweight="bold", fontsize=13, pad=10)
    ax.set_xlim(-2.2, 2.2)

    for i, (d, a) in enumerate(zip(deviations_pct, accuracies)):
        x_pos = d + 0.08 * np.sign(d) if abs(d) > 0.05 else 0.12
        ax.text(x_pos, i, f"  {a}", va="center", fontsize=9, fontweight="bold")

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=C_OBSERVED, edgecolor="black", label="< 0.1%"),
        Patch(facecolor=C_FRAMEWORK, edgecolor="black", label="0.02-0.2%"),
        Patch(facecolor=C_GOLD, edgecolor="black", label="1-2%"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=9)

    # Note about a_g below the plot
    ax.text(0.0, -1.2,
            "Also: a_g (antimatter) = 1.000g derived vs 0.75\u00b10.29g measured (within 1\u03c3, ALPHA-g 2023)",
            ha="center", fontsize=9, style="italic", color="#555555")

    path = FIG_DIR / "fig_p22_5_constants_deviation.png"
    fig.savefig(path, dpi=150)
    plt.close()
    print(f"  saved {path}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print(f"\n== Paper 22 Figure Generator ==")
    print(f"Output: {FIG_DIR}\n")
    print("Generating figures:")
    fig1_structural_identity()
    fig2_monopole_decay()
    fig3_lambda_convergence()
    fig4_coxeter_expansion()
    fig5_constants_deviation()
    print("\nDone. Five figures saved.")


if __name__ == "__main__":
    main()
