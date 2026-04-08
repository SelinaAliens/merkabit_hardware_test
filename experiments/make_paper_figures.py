#!/usr/bin/env python3
"""
Publication Figure Generator
=============================

Produces all figures for the merkabit hardware validation paper from the
three primary datasets collected on ibm_strasbourg 2026-04-07/08:

  1. P3 Z2 symmetry sweep (2-qubit, n=4,6,8,12)
     outputs/p3_z2/p3_z2_ibm_strasbourg_20260407_093513.json

  2. Rotation gap tau sweep (9-qubit triangle, tau=1,5,12)
     outputs/rotation_gap/rotation_gap_tau_sweep_ibm_strasbourg_20260407.json

  3. Pentachoric error injection (26-qubit 7-node Eisenstein)
     outputs/pentachoric/pentachoric_error_injection_ibm_strasbourg_20260407.json

Figures produced (saved to figures/):

  fig1_state_prep_validation.png  -- 2q distributions + Z2 error + ZZ breathing
  fig2_intra_vs_inter_round.png   -- Triangle per-round Fano vs aggregate Fano
  fig3_error_detection.png        -- Pentachoric baseline vs 28 injected
  fig4_lattice_coordination.png   -- Mean syndrome weight per node
  fig5_fano_by_chirality.png      -- Fano per (node, gate) grouped by chirality
  fig6_summary.png                -- 8-panel summary of all hardware results

Also produces figures_data.json with the computed values for each figure.

Usage: python experiments/make_paper_figures.py
"""

import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch
from matplotlib.colors import LinearSegmentedColormap

# --- Paths --------------------------------------------------------------------

ROOT       = Path(__file__).parent.parent
OUTPUTS    = ROOT / "outputs"
FIG_DIR    = ROOT / "figures"
FIG_DIR.mkdir(exist_ok=True)

Z2_JSON      = OUTPUTS / "p3_z2" / "p3_z2_ibm_strasbourg_20260407_093513.json"
ROTGAP_JSON  = OUTPUTS / "rotation_gap" / "rotation_gap_tau_sweep_ibm_strasbourg_20260407.json"
PENTA_JSON   = OUTPUTS / "pentachoric" / "pentachoric_error_injection_ibm_strasbourg_20260407.json"

# --- Styling ------------------------------------------------------------------

plt.rcParams.update({
    "font.family":      "DejaVu Sans",
    "font.size":        11,
    "axes.titlesize":   12,
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

COLOR_IDEAL   = "#888888"
COLOR_HW      = "#1a7fb8"
COLOR_PAIRED  = "#1a7fb8"
COLOR_CONTROL = "#d66b3a"
COLOR_CENTRE  = "#cc3333"
COLOR_FORWARD = "#2e8b57"
COLOR_INVERSE = "#6a3ea1"
COLOR_POISSON = "#cc3333"
GATE_LABELS   = ["S", "R", "T", "P", "F"]

# --- Figure 1: State preparation validation ----------------------------------

def fig1_state_prep_validation(z2_data):
    sweep = z2_data["sweep"]
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    states = ["00", "01", "10", "11"]

    # (a) Distribution tracking at n=4 (representative)
    ax = axes[0, 0]
    entry = sweep[0]  # n=4
    x = np.arange(len(states))
    w = 0.2
    ideal_f = [entry["ideal"]["fwd"][s] for s in states]
    hw_f    = [entry["fwd"]["probs"][s] for s in states]
    ideal_r = [entry["ideal"]["rev"][s] for s in states]
    hw_r    = [entry["rev"]["probs"][s] for s in states]
    ax.bar(x - 1.5*w, ideal_f, w, label="ideal (fwd)",
           color=COLOR_IDEAL, edgecolor="black", linewidth=0.5)
    ax.bar(x - 0.5*w, hw_f, w, label="hardware (fwd)",
           color=COLOR_HW, edgecolor="black", linewidth=0.5)
    ax.bar(x + 0.5*w, ideal_r, w, label="ideal (rev)",
           color=COLOR_IDEAL, alpha=0.5, edgecolor="black", linewidth=0.5)
    ax.bar(x + 1.5*w, hw_r, w, label="hardware (rev)",
           color=COLOR_HW, alpha=0.5, edgecolor="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels([f"|{s}>" for s in states])
    ax.set_ylabel("Probability")
    ax.set_title(f"(a) State distributions at n={entry['n_steps']}")
    ax.legend(loc="upper right", fontsize=9)
    ax.set_ylim(0, 0.95)

    # (b) Z2 error across all n
    ax = axes[0, 1]
    ns = [e["n_steps"] for e in sweep]
    z2_hw = [e["z2_error_hw"] for e in sweep]
    ax.bar(ns, z2_hw, color=COLOR_HW, edgecolor="black", width=1.2)
    ax.axhline(0.03, color=COLOR_POISSON, linestyle="--", linewidth=1.5,
               label="readout noise floor (~0.03)")
    ax.set_xlabel("Ouroboros steps n")
    ax.set_ylabel(r"$Z_2$ error (hardware)")
    ax.set_title(f"(b) $Z_2$ symmetry error: mean = {z2_data['mean_z2_error']:.4f}")
    ax.set_xticks(ns)
    ax.set_ylim(0, 0.035)
    ax.legend(loc="upper left", fontsize=9)
    for n, z in zip(ns, z2_hw):
        ax.text(n, z + 0.001, f"{z:.4f}", ha="center", fontsize=9)

    # (c) ZZ breathing
    ax = axes[1, 0]
    zz_fwd_ideal = []
    zz_fwd_hw    = []
    zz_rev_hw    = []
    for e in sweep:
        i = e["ideal"]["fwd"]
        zz_fwd_ideal.append(i["00"] - i["01"] - i["10"] + i["11"])
        zz_fwd_hw.append(e["zz_fwd"])
        zz_rev_hw.append(e["zz_rev"])
    ax.plot(ns, zz_fwd_ideal, "o--", color=COLOR_IDEAL, markersize=8,
            label="ideal", linewidth=2)
    ax.plot(ns, zz_fwd_hw, "s-", color=COLOR_HW, markersize=9,
            label=r"hardware $\langle ZZ\rangle_{\mathrm{fwd}}$", linewidth=2)
    ax.plot(ns, zz_rev_hw, "^-", color=COLOR_FORWARD, markersize=9,
            label=r"hardware $\langle ZZ\rangle_{\mathrm{rev}}$", linewidth=2)
    ax.set_xlabel("Ouroboros steps n")
    ax.set_ylabel(r"$\langle ZZ\rangle$")
    ax.set_title(r"(c) Ouroboros breathing in $\langle ZZ\rangle$")
    ax.set_xticks(ns)
    ax.legend(loc="upper right", fontsize=9)
    ax.set_ylim(0.35, 0.75)

    # (d) Maximum bin deviation across all n
    ax = axes[1, 1]
    max_devs = []
    for e in sweep:
        devs = []
        for s in states:
            devs.append(abs(e["ideal"]["fwd"][s] - e["fwd"]["probs"][s]))
            devs.append(abs(e["ideal"]["rev"][s] - e["rev"]["probs"][s]))
        max_devs.append(max(devs))
    ax.bar(ns, max_devs, color=COLOR_HW, edgecolor="black", width=1.2)
    ax.set_xlabel("Ouroboros steps n")
    ax.set_ylabel("Max |ideal - hardware| per bin")
    ax.set_title("(d) Distribution fidelity (max bin deviation)")
    ax.set_xticks(ns)
    for n, d in zip(ns, max_devs):
        ax.text(n, d + 0.001, f"{d:.3f}", ha="center", fontsize=9)
    ax.set_ylim(0, max(max_devs) * 1.3)

    fig.suptitle("Figure 1 -- State preparation validation (2 qubits, depth 6)",
                 fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    path = FIG_DIR / "fig1_state_prep_validation.png"
    plt.savefig(path)
    plt.close()
    print(f"  saved {path}")

    return {
        "n_steps":           ns,
        "z2_error_hw":       z2_hw,
        "zz_fwd_hw":         zz_fwd_hw,
        "zz_rev_hw":         zz_rev_hw,
        "zz_ideal":          zz_fwd_ideal,
        "max_bin_deviation": max_devs,
        "mean_z2_error":     z2_data["mean_z2_error"],
    }


# --- Figure 2: Intra-round vs inter-round Fano -------------------------------

def fig2_intra_vs_inter_round(rotgap_data):
    taus = [1, 5, 12]
    keys = [f"tau_{t}" for t in taus]

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))

    # (a) Per-round Fano as stripplot across tau
    ax = axes[0]
    colors = {1: "#7b9ec9", 5: COLOR_HW, 12: "#0f4b73"}
    for tau, k in zip(taus, keys):
        fano_values = rotgap_data[k]["per_round_fano"]
        x_jitter = tau + 0.1 * (np.arange(len(fano_values)) - len(fano_values)/2)
        ax.scatter(x_jitter, fano_values, s=100, color=colors[tau],
                   edgecolors="black", linewidth=0.8, zorder=3,
                   label=f"tau={tau} ({len(fano_values)} rounds)")
        mean = np.mean(fano_values)
        ax.plot([tau - 0.4, tau + 0.4], [mean, mean], "k-",
                linewidth=2, zorder=2)
    ax.axhline(1.0, color=COLOR_POISSON, linestyle="--", linewidth=1.5,
               label="Poisson (F=1)")
    ax.set_xlabel(r"$\tau$ (cycle length)")
    ax.set_ylabel("per-round Fano factor")
    ax.set_title("(a) Intra-round Fano: flat at ~0.52")
    ax.set_xticks(taus)
    ax.set_ylim(0.0, 1.15)
    ax.legend(loc="upper right", fontsize=9)

    # (b) Per-round vs aggregate Fano comparison
    ax = axes[1]
    x = np.arange(len(taus))
    w = 0.35
    intra = [np.mean(rotgap_data[k]["per_round_fano"]) for k in keys]
    aggr = [rotgap_data[k]["fano_factor"] for k in keys]
    ax.bar(x - w/2, intra, w, color=COLOR_HW, edgecolor="black",
           label="intra-round Fano (mean)")
    ax.bar(x + w/2, aggr, w, color=COLOR_CONTROL, edgecolor="black",
           label="aggregate Fano")
    ax.axhline(1.0, color=COLOR_POISSON, linestyle="--", linewidth=1.5,
               label="Poisson (F=1)")
    ax.set_xticks(x)
    ax.set_xticklabels([rf"$\tau={t}$" for t in taus])
    ax.set_ylabel("Fano factor")
    ax.set_title("(b) Scale separation: intra vs aggregate")
    ax.legend(loc="upper left", fontsize=9)
    ax.set_ylim(0, 6.2)
    for i, (v_i, v_a) in enumerate(zip(intra, aggr)):
        ax.text(i - w/2, v_i + 0.1, f"{v_i:.3f}", ha="center", fontsize=9)
        ax.text(i + w/2, v_a + 0.1, f"{v_a:.3f}", ha="center", fontsize=9)

    # (c) Inferred round-to-round correlation rho
    ax = axes[2]
    rho_values = []
    for k, tau in zip(keys, taus):
        if tau < 2:
            continue
        d = rotgap_data[k]
        mean_per_round = d["mean_syndrome_weight"] / tau
        intra_fano = np.mean(d["per_round_fano"])
        var_per_round = intra_fano * mean_per_round
        sum_indep = tau * var_per_round
        excess = d["var_syndrome_weight"] - sum_indep
        n_pairs = tau * (tau - 1) / 2
        mean_cov = excess / (2 * n_pairs) if n_pairs > 0 else np.nan
        rho = mean_cov / var_per_round if var_per_round > 0 else np.nan
        rho_values.append((tau, rho))

    taus_rho, rhos = zip(*rho_values)
    ax.bar(taus_rho, rhos, width=2.0, color=COLOR_FORWARD,
           edgecolor="black", alpha=0.85)
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.set_xlabel(r"$\tau$")
    ax.set_ylabel(r"mean round-to-round correlation $\rho$")
    ax.set_title(r"(c) Inter-round coherence: $\rho \approx 0.86$")
    ax.set_ylim(-0.1, 1.0)
    ax.set_xticks(taus_rho)
    for t, r in zip(taus_rho, rhos):
        ax.text(t, r + 0.02, f"{r:.3f}", ha="center", fontsize=10,
                fontweight="bold")

    fig.suptitle("Figure 2 -- Two-scale Fano structure on 3-merkabit triangle (9 qubits)",
                 fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    path = FIG_DIR / "fig2_intra_vs_inter_round.png"
    plt.savefig(path)
    plt.close()
    print(f"  saved {path}")

    return {
        "taus":       list(taus),
        "intra_fano": intra,
        "aggr_fano":  aggr,
        "rho_values": [(int(t), float(r)) for t, r in rho_values],
    }


# --- Figure 3: Error detection (pentachoric) ---------------------------------

def fig3_error_detection(penta_data):
    runs = penta_data["runs"]
    baseline = runs[0]
    injected = runs[1:]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # (a) Baseline vs injected detection rates
    ax = axes[0]
    labels = ["baseline\n(no error)"] + [r["label"].replace("node", "n")
                                         for r in injected]
    rates = [baseline["detection_rate"]] + [r["detection_rate"] for r in injected]
    colors = ["#888888"] + [
        (COLOR_CENTRE if r["chirality"] == 0
         else COLOR_FORWARD if r["chirality"] == 1
         else COLOR_INVERSE)
        for r in injected
    ]
    bars = ax.bar(range(len(rates)), rates, color=colors,
                  edgecolor="black", linewidth=0.5)
    ax.axhline(0.5, color="black", linestyle=":", linewidth=0.8, alpha=0.5)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=90, fontsize=7)
    ax.set_ylabel("Detection rate")
    ax.set_title("(a) Error detection: baseline vs 28 injections")
    ax.set_ylim(0, 1.05)
    ax.text(0, baseline["detection_rate"] + 0.02,
            f"{baseline['detection_rate']:.3f}",
            ha="center", fontsize=8, fontweight="bold")
    mean_inj = np.mean([r["detection_rate"] for r in injected])
    ax.axhline(mean_inj, color=COLOR_HW, linestyle="--", linewidth=1.5,
               label=f"mean injected = {mean_inj:.3f}")
    ax.legend(loc="center right", fontsize=9)

    # (b) Detection-rate jump with gap arrow
    ax = axes[1]
    categories = ["baseline", "injected\n(mean over 28)"]
    values = [baseline["detection_rate"], mean_inj]
    colors_b = ["#888888", COLOR_HW]
    ax.bar(categories, values, color=colors_b, edgecolor="black",
           width=0.5)
    ax.set_ylabel("Detection rate")
    ax.set_title(f"(b) {(mean_inj - baseline['detection_rate'])*100:.1f} pp detection jump")
    ax.set_ylim(0, 1.05)
    for i, v in enumerate(values):
        ax.text(i, v + 0.015, f"{v:.4f}", ha="center",
                fontsize=12, fontweight="bold")
    ax.annotate("", xy=(1, mean_inj), xytext=(0, baseline["detection_rate"]),
                arrowprops=dict(arrowstyle="->", color=COLOR_POISSON,
                                lw=2.5))
    ax.text(0.5, (baseline["detection_rate"] + mean_inj) / 2,
            f"+{(mean_inj - baseline['detection_rate'])*100:.0f} pp",
            ha="center", color=COLOR_POISSON, fontsize=13,
            fontweight="bold", rotation=0,
            bbox=dict(facecolor="white", edgecolor=COLOR_POISSON,
                      boxstyle="round,pad=0.3"))

    fig.suptitle(
        "Figure 3 -- Pentachoric error detection (26-qubit 7-node Eisenstein cell)",
        fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    path = FIG_DIR / "fig3_error_detection.png"
    plt.savefig(path)
    plt.close()
    print(f"  saved {path}")

    return {
        "baseline_detection": baseline["detection_rate"],
        "mean_injected_detection": float(mean_inj),
        "gap_pp": float((mean_inj - baseline["detection_rate"]) * 100),
        "n_injected": len(injected),
    }


# --- Figure 4: Lattice coordination signature --------------------------------

def fig4_lattice_coordination(penta_data):
    runs = penta_data["runs"]
    injected = [r for r in runs if r.get("inject_error") is not None]

    # Aggregate by node
    by_node = {}
    for r in injected:
        node = r["node"]
        if node not in by_node:
            by_node[node] = {
                "chirality": r["chirality"],
                "weights": [],
                "fanos": [],
            }
        by_node[node]["weights"].append(r["mean_syndrome_weight"])
        by_node[node]["fanos"].append(r["fano_factor"])

    nodes = sorted(by_node.keys())
    fig, ax = plt.subplots(figsize=(11, 5.5))

    means = [np.mean(by_node[n]["weights"]) for n in nodes]
    stds  = [np.std(by_node[n]["weights"])  for n in nodes]
    colors = [
        (COLOR_CENTRE if by_node[n]["chirality"] == 0
         else COLOR_FORWARD if by_node[n]["chirality"] == 1
         else COLOR_INVERSE)
        for n in nodes
    ]

    x = np.arange(len(nodes))
    ax.bar(x, means, yerr=stds, color=colors, edgecolor="black",
           linewidth=0.8, capsize=4)

    # Predicted coordination lines
    ax.axhline(3.0, color="gray", linestyle="--", linewidth=1.5,
               label="periphery coordination = 3")
    ax.axhline(6.0, color=COLOR_CENTRE, linestyle="--", linewidth=1.5,
               label="centre coordination = 6")

    ax.set_xticks(x)
    ax.set_xticklabels([
        f"n{n}\n(chi={by_node[n]['chirality']:+d})"
        for n in nodes
    ])
    ax.set_xlabel("Node")
    ax.set_ylabel("Mean syndrome weight (per injected error)")
    ax.set_title(
        "Figure 4 -- Lattice coordination signature: centre weight = 2x periphery",
        fontweight="bold")
    ax.legend(loc="upper right", fontsize=10)
    ax.set_ylim(0, 7)

    for xi, m, n in zip(x, means, nodes):
        ax.text(xi, m + 0.15, f"{m:.2f}", ha="center",
                fontsize=10, fontweight="bold")

    # Legend entries for chirality
    from matplotlib.patches import Patch
    chi_legend = [
        Patch(color=COLOR_CENTRE, label="centre (chi=0)"),
        Patch(color=COLOR_FORWARD, label="forward (chi=+1)"),
        Patch(color=COLOR_INVERSE, label="inverse (chi=-1)"),
    ]
    first_legend = ax.legend(loc="upper right", fontsize=9)
    ax.add_artist(first_legend)
    ax.legend(handles=chi_legend, loc="upper left", fontsize=9,
              title="Chirality class", title_fontsize=9)

    plt.tight_layout()
    path = FIG_DIR / "fig4_lattice_coordination.png"
    plt.savefig(path)
    plt.close()
    print(f"  saved {path}")

    return {
        "nodes": nodes,
        "mean_weights": [float(m) for m in means],
        "std_weights":  [float(s) for s in stds],
        "centre_to_periphery_ratio": float(
            means[nodes.index(3)] /
            np.mean([means[i] for i, n in enumerate(nodes) if n != 3])
        ),
    }


# --- Figure 5: Fano factor by chirality class --------------------------------

def fig5_fano_by_chirality(penta_data):
    runs = penta_data["runs"]
    injected = [r for r in runs if r.get("inject_error") is not None]

    chi_groups = {
        0:  {"label": "Centre (chi=0)",   "color": COLOR_CENTRE,  "fanos": []},
        1:  {"label": "Forward (chi=+1)", "color": COLOR_FORWARD, "fanos": []},
        -1: {"label": "Inverse (chi=-1)", "color": COLOR_INVERSE, "fanos": []},
    }
    for r in injected:
        chi_groups[r["chirality"]]["fanos"].append(r["fano_factor"])

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))

    # (a) All 28 Fano factors per injection
    ax = axes[0]
    x = 0
    positions = []
    colors = []
    fanos_flat = []
    labels_flat = []
    for chi in [0, 1, -1]:
        g = chi_groups[chi]
        for r in injected:
            if r["chirality"] != chi:
                continue
            positions.append(x)
            colors.append(g["color"])
            fanos_flat.append(r["fano_factor"])
            labels_flat.append(r["label"].replace("node", "n").replace("gate", "g"))
            x += 1
        x += 0.8

    ax.bar(positions, fanos_flat, color=colors, edgecolor="black",
           linewidth=0.5, width=0.8)
    ax.axhline(1.0, color=COLOR_POISSON, linestyle="--", linewidth=1.5,
               label="Poisson (F=1)")
    ax.set_xticks(positions)
    ax.set_xticklabels(labels_flat, rotation=90, fontsize=7)
    ax.set_ylabel("Fano factor")
    ax.set_title("(a) Fano per (node, gate) -- all 28 sub-Poissonian")
    ax.legend(loc="upper right", fontsize=9)
    ax.set_ylim(0, 1.1)

    # (b) Fano means per chirality class
    ax = axes[1]
    chis = [0, 1, -1]
    means = [np.mean(chi_groups[c]["fanos"]) for c in chis]
    stds = [np.std(chi_groups[c]["fanos"]) for c in chis]
    cols = [chi_groups[c]["color"] for c in chis]
    labels = [chi_groups[c]["label"] for c in chis]

    bars = ax.bar(labels, means, yerr=stds, color=cols,
                  edgecolor="black", linewidth=0.8, capsize=8)
    ax.axhline(1.0, color=COLOR_POISSON, linestyle="--", linewidth=1.5,
               label="Poisson (F=1)")
    ax.set_ylabel("Mean Fano factor (per chirality class)")
    ax.set_title("(b) Chirality-resolved Fano: centre ~4x tighter")
    ax.legend(loc="upper right", fontsize=9)
    ax.set_ylim(0, 0.35)
    for i, (m, s) in enumerate(zip(means, stds)):
        ax.text(i, m + s + 0.01, f"{m:.3f}\n+/-{s:.3f}",
                ha="center", fontsize=10, fontweight="bold")

    fig.suptitle(
        "Figure 5 -- Sub-Poissonian anti-bunching across all injections",
        fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    path = FIG_DIR / "fig5_fano_by_chirality.png"
    plt.savefig(path)
    plt.close()
    print(f"  saved {path}")

    return {
        "centre_fano_mean":   float(means[0]),
        "centre_fano_std":    float(stds[0]),
        "forward_fano_mean":  float(means[1]),
        "forward_fano_std":   float(stds[1]),
        "inverse_fano_mean":  float(means[2]),
        "inverse_fano_std":   float(stds[2]),
        "all_sub_poissonian": bool(all(f < 1.0 for f in fanos_flat)),
        "n_runs":             len(fanos_flat),
    }


# --- Figure 6: Summary panel --------------------------------------------------

def fig6_summary(z2_data, rotgap_data, penta_data, results_by_fig):
    fig = plt.figure(figsize=(14, 9))
    gs = fig.add_gridspec(3, 3, hspace=0.55, wspace=0.45)

    # Panel 1: Z2 error bar (top-left)
    ax = fig.add_subplot(gs[0, 0])
    sweep = z2_data["sweep"]
    ns = [e["n_steps"] for e in sweep]
    z2_hw = [e["z2_error_hw"] for e in sweep]
    ax.bar(ns, z2_hw, color=COLOR_HW, edgecolor="black", width=1.2)
    ax.axhline(0.03, color=COLOR_POISSON, linestyle="--", linewidth=1.0)
    ax.set_xticks(ns)
    ax.set_ylabel(r"$Z_2$ error")
    ax.set_title(r"(1) $Z_2$ symmetry (2q)", fontsize=11)
    ax.set_ylim(0, 0.035)

    # Panel 2: ZZ breathing (top-middle)
    ax = fig.add_subplot(gs[0, 1])
    zz_fwd_ideal = []
    zz_fwd_hw = []
    for e in sweep:
        i = e["ideal"]["fwd"]
        zz_fwd_ideal.append(i["00"] - i["01"] - i["10"] + i["11"])
        zz_fwd_hw.append(e["zz_fwd"])
    ax.plot(ns, zz_fwd_ideal, "o--", color=COLOR_IDEAL, label="ideal",
            markersize=7, linewidth=2)
    ax.plot(ns, zz_fwd_hw, "s-", color=COLOR_HW, label="hardware",
            markersize=8, linewidth=2)
    ax.set_xticks(ns)
    ax.set_ylabel(r"$\langle ZZ\rangle$")
    ax.set_title(r"(2) Ouroboros breathing", fontsize=11)
    ax.legend(fontsize=8, loc="upper right")

    # Panel 3: Per-round Fano stability (top-right)
    ax = fig.add_subplot(gs[0, 2])
    for tau in [5, 12]:
        k = f"tau_{tau}"
        rounds = np.arange(1, tau + 1)
        fano_rounds = rotgap_data[k]["per_round_fano"]
        ax.plot(rounds, fano_rounds, "o-",
                color=COLOR_HW if tau == 5 else "#0f4b73",
                label=rf"$\tau={tau}$", markersize=6, linewidth=1.8)
    ax.axhline(1.0, color=COLOR_POISSON, linestyle="--", linewidth=1.0)
    ax.set_xlabel("Round index")
    ax.set_ylabel("Per-round Fano")
    ax.set_title("(3) Intra-round stability (9q)", fontsize=11)
    ax.legend(fontsize=8, loc="center right")
    ax.set_ylim(0.4, 1.1)

    # Panel 4: Inter-round correlation rho (middle-left)
    ax = fig.add_subplot(gs[1, 0])
    rho_data = results_by_fig["fig2"]["rho_values"]
    taus_rho = [r[0] for r in rho_data]
    rhos = [r[1] for r in rho_data]
    ax.bar(taus_rho, rhos, width=2, color=COLOR_FORWARD,
           edgecolor="black")
    ax.set_xticks(taus_rho)
    ax.set_xlabel(r"$\tau$")
    ax.set_ylabel(r"$\rho$ (mean)")
    ax.set_title(r"(4) Inter-round coherence", fontsize=11)
    ax.set_ylim(0, 1.0)
    for t, r in zip(taus_rho, rhos):
        ax.text(t, r + 0.02, f"{r:.2f}", ha="center", fontsize=9,
                fontweight="bold")

    # Panel 5: Error detection jump (middle-middle)
    ax = fig.add_subplot(gs[1, 1])
    runs = penta_data["runs"]
    baseline = runs[0]
    injected = [r for r in runs[1:]]
    mean_inj = np.mean([r["detection_rate"] for r in injected])
    ax.bar(["baseline", "injected"],
           [baseline["detection_rate"], mean_inj],
           color=["#888888", COLOR_HW], edgecolor="black")
    ax.set_ylabel("Detection rate")
    ax.set_title("(5) Error detection (26q)", fontsize=11)
    ax.set_ylim(0, 1.1)
    for i, v in enumerate([baseline["detection_rate"], mean_inj]):
        ax.text(i, v + 0.02, f"{v:.3f}", ha="center",
                fontsize=9, fontweight="bold")

    # Panel 6: Per-node mean weight (middle-right)
    ax = fig.add_subplot(gs[1, 2])
    by_node = {}
    for r in injected:
        by_node.setdefault(r["node"], {
            "chi": r["chirality"], "w": []
        })["w"].append(r["mean_syndrome_weight"])
    nodes = sorted(by_node.keys())
    means_w = [np.mean(by_node[n]["w"]) for n in nodes]
    cols = [
        (COLOR_CENTRE if by_node[n]["chi"] == 0
         else COLOR_FORWARD if by_node[n]["chi"] == 1
         else COLOR_INVERSE)
        for n in nodes
    ]
    ax.bar(nodes, means_w, color=cols, edgecolor="black")
    ax.axhline(3.0, color="gray", linestyle="--", linewidth=1.0)
    ax.axhline(6.0, color=COLOR_CENTRE, linestyle="--", linewidth=1.0)
    ax.set_xticks(nodes)
    ax.set_xlabel("Node")
    ax.set_ylabel("Mean weight")
    ax.set_title("(6) Coord. signature", fontsize=11)
    ax.set_ylim(0, 7)

    # Panel 7: Fano by chirality (bottom-left)
    ax = fig.add_subplot(gs[2, 0])
    f5 = results_by_fig["fig5"]
    chis = ["Centre", "Forward", "Inverse"]
    means = [f5["centre_fano_mean"], f5["forward_fano_mean"],
             f5["inverse_fano_mean"]]
    stds = [f5["centre_fano_std"], f5["forward_fano_std"],
            f5["inverse_fano_std"]]
    cols = [COLOR_CENTRE, COLOR_FORWARD, COLOR_INVERSE]
    ax.bar(chis, means, yerr=stds, color=cols, edgecolor="black",
           capsize=5)
    ax.axhline(1.0, color=COLOR_POISSON, linestyle="--", linewidth=1.0)
    ax.set_ylabel("Fano")
    ax.set_title("(7) Fano by chirality", fontsize=11)
    ax.set_ylim(0, 0.32)
    for i, (m, s) in enumerate(zip(means, stds)):
        ax.text(i, m + s + 0.008, f"{m:.3f}", ha="center",
                fontsize=9, fontweight="bold")

    # Panel 8 & 9: Summary text (bottom span)
    ax = fig.add_subplot(gs[2, 1:])
    ax.axis("off")
    summary_text = (
        "FIRST HARDWARE VALIDATION -- ibm_strasbourg -- 2026-04-07/08\n\n"
        r"$\bullet$ 2-qubit (depth 6): state distribution matches ideal to 1--2% per bin" + "\n"
        r"$\bullet$ $Z_2$ symmetry: mean error 0.0163 (below readout floor 0.03)" + "\n"
        r"$\bullet$ Ouroboros breathing: non-monotonic $\langle ZZ\rangle$ preserved" + "\n"
        r"$\bullet$ 9-qubit triangle: intra-round Fano locked at ~0.52 across 12 rounds" + "\n"
        r"$\bullet$ Inter-round correlation $\rho \approx 0.86$ (coherent standing wave)" + "\n"
        r"$\bullet$ 26-qubit pentachoric: error detection $0.089 \to 0.99$ (all 28 injections)" + "\n"
        r"$\bullet$ Centre coordination signature: $6.04 / 3.14 \approx 1.92$" + "\n"
        r"$\bullet$ Sub-Poissonian Fano on every single hardware run" + "\n"
        r"$\bullet$ Centre $F = 0.053 \pm 0.008$, periphery $F \approx 0.20 \pm 0.02$"
    )
    ax.text(0.02, 0.98, summary_text, transform=ax.transAxes,
            fontsize=10, verticalalignment="top", family="monospace",
            bbox=dict(facecolor="#f5f5f5", edgecolor="black",
                      boxstyle="round,pad=0.5"))

    fig.suptitle("Figure 6 -- Merkabit hardware validation summary",
                 fontweight="bold", fontsize=14)

    path = FIG_DIR / "fig6_summary.png"
    plt.savefig(path, bbox_inches="tight")
    plt.close()
    print(f"  saved {path}")


# --- Main ---------------------------------------------------------------------

def main():
    print(f"\n== Merkabit Paper Figure Generator ==")
    print(f"Output directory: {FIG_DIR}\n")

    # Load
    print("Loading datasets:")
    for p in [Z2_JSON, ROTGAP_JSON, PENTA_JSON]:
        print(f"  {p.name}: {'OK' if p.exists() else 'MISSING'}")

    z2_data = json.loads(Z2_JSON.read_text())
    rotgap_data = json.loads(ROTGAP_JSON.read_text())
    penta_data = json.loads(PENTA_JSON.read_text())

    print("\nGenerating figures:")
    results = {}
    results["fig1"] = fig1_state_prep_validation(z2_data)
    results["fig2"] = fig2_intra_vs_inter_round(rotgap_data)
    results["fig3"] = fig3_error_detection(penta_data)
    results["fig4"] = fig4_lattice_coordination(penta_data)
    results["fig5"] = fig5_fano_by_chirality(penta_data)
    fig6_summary(z2_data, rotgap_data, penta_data, results)

    # Save computed values
    data_out = FIG_DIR / "figures_data.json"
    with open(data_out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFigure data -> {data_out}")

    print("\n== Summary ==")
    print(f"  Z2 mean error:          {results['fig1']['mean_z2_error']:.4f}")
    print(f"  Triangle intra-Fano:    "
          f"tau=1 {results['fig2']['intra_fano'][0]:.4f}, "
          f"tau=5 {results['fig2']['intra_fano'][1]:.4f}, "
          f"tau=12 {results['fig2']['intra_fano'][2]:.4f}")
    print(f"  Inter-round rho:        "
          f"tau=5 {results['fig2']['rho_values'][0][1]:.4f}, "
          f"tau=12 {results['fig2']['rho_values'][1][1]:.4f}")
    print(f"  Detection jump:         "
          f"{results['fig3']['baseline_detection']:.4f} -> "
          f"{results['fig3']['mean_injected_detection']:.4f}  "
          f"(+{results['fig3']['gap_pp']:.1f} pp)")
    print(f"  Centre/periphery ratio: "
          f"{results['fig4']['centre_to_periphery_ratio']:.4f}")
    print(f"  Centre Fano:            "
          f"{results['fig5']['centre_fano_mean']:.4f} "
          f"+/- {results['fig5']['centre_fano_std']:.4f}")
    print(f"  Forward Fano:           "
          f"{results['fig5']['forward_fano_mean']:.4f} "
          f"+/- {results['fig5']['forward_fano_std']:.4f}")
    print(f"  Inverse Fano:           "
          f"{results['fig5']['inverse_fano_mean']:.4f} "
          f"+/- {results['fig5']['inverse_fano_std']:.4f}")
    print(f"  All sub-Poissonian:     {results['fig5']['all_sub_poissonian']}")


if __name__ == "__main__":
    main()
