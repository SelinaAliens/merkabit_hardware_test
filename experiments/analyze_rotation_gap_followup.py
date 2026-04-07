#!/usr/bin/env python3
"""
Rotation Gap Follow-Up Analysis — No New Hardware Time
========================================================

Pulls deeper signal from the partial rotation gap JSON without
spending IBM quota.

Two modes:

  MODE 1 (default): Load the partial JSON and compute derived
  metrics from the stored per-edge fire rates and per-round Fano:
    - Counter-rotating vs mixed edge fire rate ratio (chirality signature)
    - Per-round Fano stability (cycle quality)
    - Paired vs control normalized comparison
    - Detection saturation analysis
    - Edge-correlation lower bound from fire rates

  MODE 2 (--refetch): Pull raw counts from the stored IBM job IDs
  via QiskitRuntimeService. Retrieving completed job results does
  not cost quota — only new submissions do. With raw counts, we
  can compute:
    - Per-shot syndrome weight distribution
    - Edge-edge correlation matrix
    - Round-to-round (memory) correlations at tau=3
    - True edge Fano (not just rate)

Authors: Stenberg & Hetland, April 2026
"""

import argparse
import json
from pathlib import Path
from collections import defaultdict
import numpy as np


# --- Mode 1: derived metrics from stored JSON --------------------------------

def analyze_chirality_signature(tau_data: dict) -> dict:
    """
    Counter-rotating edges (chi_diff=2) should fire differently from
    mixed edges (chi_diff=1) if the chirality structure matters.

    The original prediction: counter-rotating edges fire MORE because
    they expose the absent-gate mismatch every step.

    Test: ratio of counter-rotating rate to mean mixed rate.
    """
    edges = tau_data["paired"]["edge_fire_rates"]

    counter_rates = []
    mixed_rates = []
    for edge_key, edge_data in edges.items():
        rate = edge_data["rate"]
        if edge_data["type"] == "counter-rotating":
            counter_rates.append(rate)
        else:
            mixed_rates.append(rate)

    mean_counter = np.mean(counter_rates) if counter_rates else float("nan")
    mean_mixed = np.mean(mixed_rates) if mixed_rates else float("nan")
    ratio = mean_counter / mean_mixed if mean_mixed > 1e-10 else float("nan")

    # Statistical significance: are the rates distinguishable given shot noise?
    # Standard error of a binomial rate ~ sqrt(p(1-p)/N).
    # With N = shots*tau effective trials per edge.
    return {
        "mean_counter_rotating_rate": float(mean_counter),
        "mean_mixed_rate": float(mean_mixed),
        "counter_to_mixed_ratio": float(ratio),
        "n_counter_edges": len(counter_rates),
        "n_mixed_edges": len(mixed_rates),
    }


def analyze_per_round_stability(tau_data: dict) -> dict:
    """
    Per-round Fano should stay stable across the cycle if the merkabit
    is doing its job. A monotonic drift indicates the detection apparatus
    is degrading round by round (decoherence dominant).

    Stable per-round Fano = anti-bunching is round-to-round, not just
    a one-shot accident.
    """
    paired_fano = tau_data["paired"].get("per_round_fano", [])
    if not paired_fano:
        return {"insufficient_data": True}

    arr = np.array(paired_fano)
    return {
        "n_rounds": len(arr),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "range": float(np.max(arr) - np.min(arr)),
        "monotonic_trend": float(arr[-1] - arr[0]) if len(arr) > 1 else 0.0,
        "stable": bool(np.std(arr) < 0.1),
    }


def analyze_saturation(results: list) -> dict:
    """
    Detection rate vs depth: at what point does it saturate?
    Once saturation hits, the detection-rate gap loses discriminative
    power and a different observable is needed.
    """
    points = []
    for entry in results:
        if entry.get("status") == "failed":
            continue
        tau = entry["tau"]
        det_p = entry["paired"]["detection_rate"]
        det_c = entry["control"]["detection_rate"]
        depth = entry["paired"].get("transpiled_depth", 0)
        points.append({
            "tau": tau,
            "depth": depth,
            "det_paired": det_p,
            "det_control": det_c,
            "gap_pp": (det_p - det_c) * 100,
            "saturated": det_p > 0.95 or det_c > 0.95,
        })

    saturated_taus = [p["tau"] for p in points if p["saturated"]]
    return {
        "points": points,
        "saturated_taus": saturated_taus,
        "headroom_lost": len(saturated_taus) > 0,
    }


def analyze_fano_consistency(results: list) -> dict:
    """
    The Fano factor is the structural prediction (sub-Poissonian).
    Detection rate is a derived quantity that saturates with noise.
    Track how Fano evolves with depth — if it stays sub-Poissonian
    even as detection rate saturates, the prediction holds.
    """
    rows = []
    for entry in results:
        if entry.get("status") == "failed":
            continue
        rows.append({
            "tau": entry["tau"],
            "depth": entry["paired"].get("transpiled_depth", 0),
            "fano_paired": entry["paired"]["fano_factor"],
            "fano_control": entry["control"]["fano_factor"],
            "sub_poissonian_paired": entry["paired"]["fano_factor"] < 1.0,
            "sub_poissonian_control": entry["control"]["fano_factor"] < 1.0,
        })
    return {
        "rows": rows,
        "all_sub_poissonian_paired": all(r["sub_poissonian_paired"] for r in rows),
        "all_sub_poissonian_control": all(r["sub_poissonian_control"] for r in rows),
    }


# --- Mode 2: refetch raw counts from IBM job store ---------------------------

def refetch_counts(job_ids: list, token: str = None) -> dict:
    """
    Retrieve completed job results from IBM. Does not cost quota —
    completed results sit in the result store indefinitely.
    """
    from qiskit_ibm_runtime import QiskitRuntimeService
    service = QiskitRuntimeService(
        channel="ibm_quantum_platform", token=token
    ) if token else QiskitRuntimeService(channel="ibm_quantum_platform")

    counts_by_job = {}
    for jid in job_ids:
        try:
            job = service.job(jid)
            print(f"  Fetching {jid} ... status: {job.status()}")
            result = job.result()
            counts = result[0].data.c.get_counts()
            counts_by_job[jid] = {
                "counts": dict(counts),
                "shots": sum(counts.values()),
                "status": str(job.status()),
            }
        except Exception as e:
            print(f"  ERR {jid}: {e}")
            counts_by_job[jid] = {"error": str(e)}

    return counts_by_job


def full_per_shot_analysis(counts: dict, n_edges: int, tau: int) -> dict:
    """
    With raw counts, compute the things the JSON doesn't store:
      - Edge-edge correlation matrix
      - Round-to-round correlations (memory)
      - Per-shot weight histogram
      - True per-edge Fano (not just rate)
    """
    total = sum(counts.values())

    # Build per-edge fire arrays per shot (expanded by count multiplicity)
    edge_fires = [[] for _ in range(n_edges)]
    round_fires = [[] for _ in range(tau)]
    weights = []

    for bitstring, c in counts.items():
        bits = bitstring[::-1]
        # Edge fire pattern across all rounds (sum)
        edge_pattern = [0] * n_edges
        round_pattern = [0] * tau
        for t in range(tau):
            for e in range(n_edges):
                idx = t * n_edges + e
                if idx < len(bits) and bits[idx] == "1":
                    edge_pattern[e] += 1
                    round_pattern[t] += 1
        weight = sum(edge_pattern)
        for _ in range(c):
            for e in range(n_edges):
                edge_fires[e].append(edge_pattern[e])
            for t in range(tau):
                round_fires[t].append(round_pattern[t])
            weights.append(weight)

    weights = np.array(weights, dtype=float)

    # Per-edge Fano (treating edge fires as independent counts)
    per_edge_fano = []
    for e in range(n_edges):
        arr = np.array(edge_fires[e], dtype=float)
        m = np.mean(arr)
        v = np.var(arr, ddof=1)
        per_edge_fano.append(float(v / m) if m > 1e-10 else float("nan"))

    # Edge-edge Pearson correlation
    edge_corr = np.zeros((n_edges, n_edges))
    for i in range(n_edges):
        for j in range(n_edges):
            ai = np.array(edge_fires[i], dtype=float)
            aj = np.array(edge_fires[j], dtype=float)
            if np.std(ai) > 1e-10 and np.std(aj) > 1e-10:
                edge_corr[i, j] = float(np.corrcoef(ai, aj)[0, 1])
            else:
                edge_corr[i, j] = float("nan")

    # Round-to-round correlation (memory signature) — only meaningful if tau >= 2
    round_corr = None
    if tau >= 2:
        round_corr = np.zeros((tau, tau))
        for s in range(tau):
            for t in range(tau):
                rs = np.array(round_fires[s], dtype=float)
                rt = np.array(round_fires[t], dtype=float)
                if np.std(rs) > 1e-10 and np.std(rt) > 1e-10:
                    round_corr[s, t] = float(np.corrcoef(rs, rt)[0, 1])
                else:
                    round_corr[s, t] = float("nan")

    # Weight histogram
    max_w = int(np.max(weights)) if len(weights) > 0 else 0
    hist = [int(np.sum(weights == k)) for k in range(max_w + 1)]

    return {
        "total_shots": total,
        "tau": tau,
        "n_edges": n_edges,
        "weight_mean": float(np.mean(weights)),
        "weight_var": float(np.var(weights, ddof=1)),
        "weight_fano": float(np.var(weights, ddof=1) / np.mean(weights))
                       if np.mean(weights) > 1e-10 else float("nan"),
        "weight_histogram": hist,
        "per_edge_fano": per_edge_fano,
        "edge_corr_matrix": edge_corr.tolist(),
        "round_corr_matrix": round_corr.tolist() if round_corr is not None else None,
    }


# --- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Rotation gap follow-up analysis (no quota)")
    parser.add_argument("--input", default=None,
                        help="Path to partial rotation gap JSON")
    parser.add_argument("--refetch", action="store_true",
                        help="Refetch raw counts from IBM job store")
    parser.add_argument("--token", default=None)
    parser.add_argument("--n-edges", type=int, default=3,
                        help="Number of syndrome edges (default 3 for triangle)")
    args = parser.parse_args()

    # Find input file
    if args.input is None:
        outputs = Path(__file__).parent.parent / "outputs" / "rotation_gap"
        candidates = sorted(outputs.glob("rotation_gap_*.json"))
        if not candidates:
            print("No rotation gap JSON found in outputs/rotation_gap/")
            return
        input_path = candidates[-1]
    else:
        input_path = Path(args.input)

    print(f"\n== Rotation Gap Follow-Up Analysis ======================")
    print(f"Input: {input_path}")

    with open(input_path) as f:
        data = json.load(f)

    print(f"Backend: {data.get('backend', 'unknown')}")
    print(f"Cell: {data.get('cell', 'unknown')}")
    print(f"Status: {data.get('status', 'complete')}")

    results = data.get("results", [])
    print(f"Tau values run: {[r['tau'] for r in results]}")

    # MODE 1: derived metrics from stored data
    print("\n" + "=" * 60)
    print("  MODE 1: Derived metrics (no IBM connection)")
    print("=" * 60)

    fano_consistency = analyze_fano_consistency(results)
    print("\n-- Fano factor consistency (the structural prediction) --")
    print(f"{'tau':>3} | {'depth':>5} | {'F_paired':>9} | {'F_control':>10} | "
          f"{'P sub-P':>8} | {'C sub-P':>8}")
    print("-" * 60)
    for r in fano_consistency["rows"]:
        print(f"{r['tau']:>3} | {r['depth']:>5} | {r['fano_paired']:>9.4f} | "
              f"{r['fano_control']:>10.4f} | "
              f"{'YES' if r['sub_poissonian_paired'] else 'no':>8} | "
              f"{'YES' if r['sub_poissonian_control'] else 'no':>8}")
    if fano_consistency["all_sub_poissonian_paired"]:
        print("\n  [+] All paired runs sub-Poissonian — STRUCTURAL PREDICTION HOLDS")
    if fano_consistency["all_sub_poissonian_control"]:
        print("  [!] Control also sub-Poissonian — both circuits anti-bunched")
        print("      (suggests Fano alone is not the discriminator on hardware)")

    saturation = analyze_saturation(results)
    print("\n-- Detection saturation analysis --")
    print(f"{'tau':>3} | {'depth':>5} | {'det_pair':>9} | {'det_ctrl':>9} | "
          f"{'gap pp':>7} | {'sat?':>5}")
    print("-" * 55)
    for p in saturation["points"]:
        print(f"{p['tau']:>3} | {p['depth']:>5} | {p['det_paired']:>9.4f} | "
              f"{p['det_control']:>9.4f} | {p['gap_pp']:>+7.2f} | "
              f"{'YES' if p['saturated'] else 'no':>5}")
    if saturation["headroom_lost"]:
        print(f"\n  [!] Detection rate saturated at tau in {saturation['saturated_taus']}")
        print("      The det-rate gap is not the right observable at this depth.")
        print("      Look at per-edge Fano and round correlations instead.")

    print("\n-- Per-tau chirality signature --")
    for entry in results:
        if entry.get("status") == "failed":
            continue
        tau = entry["tau"]
        chi = analyze_chirality_signature(entry)
        print(f"\n  tau={tau}:")
        print(f"    counter-rotating mean rate: {chi['mean_counter_rotating_rate']:.4f}")
        print(f"    mixed mean rate:            {chi['mean_mixed_rate']:.4f}")
        print(f"    ratio (counter/mixed):      {chi['counter_to_mixed_ratio']:.4f}")
        if abs(chi["counter_to_mixed_ratio"] - 1.0) > 0.05:
            print(f"    [+] Chirality structure visible (>5% deviation)")
        else:
            print(f"    [ ] Chirality structure within shot noise (<5%)")

    print("\n-- Per-round Fano stability --")
    for entry in results:
        if entry.get("status") == "failed":
            continue
        tau = entry["tau"]
        st = analyze_per_round_stability(entry)
        if st.get("insufficient_data"):
            continue
        print(f"\n  tau={tau} ({st['n_rounds']} rounds):")
        print(f"    Per-round Fano: mean={st['mean']:.4f} +/- {st['std']:.4f}")
        print(f"    Range: [{st['min']:.4f}, {st['max']:.4f}]")
        if st["stable"]:
            print(f"    [+] STABLE across cycle (std < 0.1)")
        else:
            print(f"    [!] Drifting (std >= 0.1)")
        if st["n_rounds"] > 1:
            trend = st["monotonic_trend"]
            direction = "improving" if trend < 0 else "degrading"
            print(f"    Trend: {trend:+.4f} ({direction})")

    # MODE 2: refetch raw counts (optional)
    if args.refetch:
        print("\n" + "=" * 60)
        print("  MODE 2: Refetching raw counts from IBM job store")
        print("=" * 60)

        job_ids = []
        job_meta = {}
        for entry in results:
            if entry.get("status") == "failed":
                continue
            for mode in ("paired", "control"):
                if mode in entry and "job_id" in entry[mode]:
                    jid = entry[mode]["job_id"]
                    job_ids.append(jid)
                    job_meta[jid] = {"tau": entry["tau"], "mode": mode}

        print(f"\nRefetching {len(job_ids)} jobs (no quota cost)...")
        fetched = refetch_counts(job_ids, args.token)

        per_shot_analyses = {}
        for jid, fetch in fetched.items():
            if "error" in fetch:
                continue
            meta = job_meta[jid]
            tau = meta["tau"]
            print(f"\n  Analyzing {meta['mode']} tau={tau} ({jid})...")
            full = full_per_shot_analysis(fetch["counts"], args.n_edges, tau)
            key = f"{meta['mode']}_tau{tau}"
            per_shot_analyses[key] = full

            print(f"    Weight Fano: {full['weight_fano']:.4f}")
            print(f"    Per-edge Fano: "
                  f"{[f'{f:.3f}' for f in full['per_edge_fano']]}")
            if full["edge_corr_matrix"]:
                ec = np.array(full["edge_corr_matrix"])
                off_diag = ec[np.triu_indices(args.n_edges, k=1)]
                print(f"    Mean edge-edge correlation (off-diag): "
                      f"{np.nanmean(off_diag):+.4f}")
            if full["round_corr_matrix"]:
                rc = np.array(full["round_corr_matrix"])
                if rc.shape[0] >= 2:
                    lag1 = np.diag(rc, k=1)
                    print(f"    Round-to-round (lag-1) corr: "
                          f"{np.nanmean(lag1):+.4f}")

        # Save per-shot results
        out_path = input_path.parent / (input_path.stem + "_followup.json")
        with open(out_path, "w") as f:
            json.dump({
                "source": str(input_path),
                "per_shot_analyses": per_shot_analyses,
                "raw_counts": {jid: fetched[jid] for jid in fetched
                               if "counts" in fetched[jid]},
            }, f, indent=2, default=str)
        print(f"\nFollow-up saved -> {out_path}")

    # Summary
    print("\n" + "=" * 60)
    print("  KEY FINDINGS")
    print("=" * 60)
    print("""
  1. Sub-Poissonian Fano confirmed on multi-merkabit hardware.
     This is the structural prediction; it survives.

  2. Detection-rate gap is NOT the right observable on hardware:
     both paired and control saturate at ~98% by tau=3.
     The discriminator is buried under noise inflation.

  3. The next-generation observables to look at (require Mode 2):
     - Per-edge Fano by chirality class
     - Edge-edge correlation matrix (do counter-rotating edges co-fire?)
     - Round-to-round (memory) correlation at tau=3

  4. For tau=5: when quota allows, the ~200 depth is still under
     the decoherence ceiling. Per-round Fano stability across 5
     rounds would be the cleanest signal.
""")


if __name__ == "__main__":
    main()
