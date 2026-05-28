# -*- coding: utf-8 -*-
# =============================================================
# analysis/stats.py
# Xuat bang thong ke chi tiet ra stats_summary.txt
# =============================================================

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime

import config

PROFILE_ORDER  = ["local", "regional", "global"]
OUTPUT_FILE    = os.path.join(config.ANALYSIS_DIR, "stats_summary.txt")


# ------------------------------------------------------------------
# Helper: tinh day du thong ke cho 1 series
# ------------------------------------------------------------------
def describe(series):
    return {
        "count":  len(series),
        "mean":   series.mean(),
        "median": series.median(),
        "std":    series.std(),
        "min":    series.min(),
        "p25":    series.quantile(0.25),
        "p75":    series.quantile(0.75),
        "p95":    series.quantile(0.95),
        "p99":    series.quantile(0.99),
        "max":    series.max(),
    }


# ------------------------------------------------------------------
# Format bang
# ------------------------------------------------------------------
def fmt(val, unit="ms"):
    if val is None:
        return "N/A"
    if unit == "ms":
        return f"{val:.2f}ms"
    if unit == "%":
        return f"{val:.2f}%"
    return f"{val:.2f}"


def write_separator(f, char="=", width=65):
    f.write(char * width + "\n")


def write_section(f, title):
    write_separator(f)
    f.write(f"  {title}\n")
    write_separator(f)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def generate_stats():
    # Load data
    df = pd.read_csv(config.BENCHMARK_CSV)
    df = df[df["total_time_ms"].notna()]

    lines = []
    output = []

    def w(line=""):
        output.append(line)

    # ----------------------------------------------------------
    # Header
    # ----------------------------------------------------------
    w("=" * 65)
    w("  Trans-Atlantic DB — Statistical Summary Report")
    w(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    w(f"  Dataset  : {config.BENCHMARK_CSV}")
    w(f"  Total    : {len(df)} transactions "
      f"({config.BENCHMARK_RUNS} runs x 3 profiles)")
    w("=" * 65)

    # ----------------------------------------------------------
    # Section 1: Tong ket nhanh
    # ----------------------------------------------------------
    w()
    w("=" * 65)
    w("  SECTION 1: QUICK SUMMARY")
    w("=" * 65)
    w()
    w(f"  {'Profile':<12} {'Mean':>9} {'Median':>9} "
      f"{'P99':>9} {'CoordCost':>12}")
    w(f"  {'-'*55}")
    for profile in PROFILE_ORDER:
        d      = df[df["latency_profile"] == profile]
        mean   = d["total_time_ms"].mean()
        median = d["total_time_ms"].median()
        p99    = d["total_time_ms"].quantile(0.99)
        cost   = d["coord_cost_pct"].mean()
        w(f"  {profile:<12} {mean:>8.1f}ms {median:>8.1f}ms "
          f"{p99:>8.1f}ms {cost:>10.1f}%")

    # ----------------------------------------------------------
    # Section 2: Chi tiet tung profile
    # ----------------------------------------------------------
    w()
    w("=" * 65)
    w("  SECTION 2: DETAILED STATISTICS PER PROFILE")
    w("=" * 65)

    for profile in PROFILE_ORDER:
        d          = df[df["latency_profile"] == profile]
        latency_ms = config.LATENCY_PROFILES[profile] * 1000

        w()
        w(f"  --- {profile.upper()} ({latency_ms:.0f}ms one-way latency) ---")
        w()

        # Total time
        s = describe(d["total_time_ms"])
        w(f"  Total Transaction Time:")
        w(f"    Count   : {s['count']}")
        w(f"    Mean    : {fmt(s['mean'])}")
        w(f"    Median  : {fmt(s['median'])}")
        w(f"    Std Dev : {fmt(s['std'])}")
        w(f"    Min     : {fmt(s['min'])}")
        w(f"    P25     : {fmt(s['p25'])}")
        w(f"    P75     : {fmt(s['p75'])}")
        w(f"    P95     : {fmt(s['p95'])}")
        w(f"    P99     : {fmt(s['p99'])}")
        w(f"    Max     : {fmt(s['max'])}")

        # Network wait
        s_net = describe(d["network_wait_ms"])
        w()
        w(f"  Network Wait Time (sleep):")
        w(f"    Mean    : {fmt(s_net['mean'])}")
        w(f"    Std Dev : {fmt(s_net['std'])}")
        w(f"    Min/Max : {fmt(s_net['min'])} / {fmt(s_net['max'])}")

        # Work time
        s_work = describe(d["work_ms"])
        w()
        w(f"  Work Time (CPU + I/O):")
        w(f"    Mean    : {fmt(s_work['mean'])}")
        w(f"    Std Dev : {fmt(s_work['std'])}")
        w(f"    Min/Max : {fmt(s_work['min'])} / {fmt(s_work['max'])}")

        # Cost of Coordination
        s_cost = describe(d["coord_cost_pct"])
        w()
        w(f"  Cost of Coordination:")
        w(f"    Mean    : {fmt(s_cost['mean'], '%')}")
        w(f"    Median  : {fmt(s_cost['median'], '%')}")
        w(f"    Min/Max : {fmt(s_cost['min'], '%')} / "
          f"{fmt(s_cost['max'], '%')}")

        # Phase breakdown
        if "phase1_time_ms" in d.columns:
            w()
            w(f"  Phase Breakdown (mean):")
            w(f"    Phase 1 (Voting)  : "
              f"{fmt(d['phase1_time_ms'].mean())}")
            w(f"    Phase 2 (Decision): "
              f"{fmt(d['phase2_time_ms'].mean())}")

        # Success rate
        if "success" in d.columns:
            success_rate = d["success"].mean() * 100
            w()
            w(f"  Success Rate: {success_rate:.1f}%")

    # ----------------------------------------------------------
    # Section 3: Ozsu Cost Model Analysis
    # ----------------------------------------------------------
    w()
    w("=" * 65)
    w("  SECTION 3: OZSU COST MODEL ANALYSIS")
    w("=" * 65)
    w()
    w("  Formula: Total_Cost = TCPU x #insts + TIO x #IOs")
    w("                      + TMSG x #messages + TTR x #bytes")
    w()
    w("  In this experiment:")
    w("    TMSG = simulated one-way latency")
    w("    #messages per 2PC = 4N = 4 x 2 = 8")
    w()
    w(f"  {'Profile':<12} {'TMSG':>8} {'Comm Cost':>12} "
      f"{'Work Cost':>12} {'Total':>10}")
    w(f"  {'-'*58}")

    for profile in PROFILE_ORDER:
        d         = df[df["latency_profile"] == profile]
        tmsg      = config.LATENCY_PROFILES[profile] * 1000
        comm_cost = d["network_wait_ms"].mean()
        work_cost = d["work_ms"].mean()
        total     = d["total_time_ms"].mean()
        w(f"  {profile:<12} {tmsg:>7.0f}ms {comm_cost:>10.1f}ms "
          f"{work_cost:>10.1f}ms {total:>8.1f}ms")

    w()
    w("  Observation:")

    local_work  = df[df["latency_profile"]=="local"]["work_ms"].mean()
    global_work = df[df["latency_profile"]=="global"]["work_ms"].mean()
    local_comm  = df[df["latency_profile"]=="local"]["network_wait_ms"].mean()
    global_comm = df[df["latency_profile"]=="global"]["network_wait_ms"].mean()

    w(f"  - Work cost (CPU+IO): {local_work:.1f}ms (local) vs "
      f"{global_work:.1f}ms (global)")
    w(f"    => Constant, independent of network latency")
    w(f"  - Comm cost        : {local_comm:.1f}ms (local) vs "
      f"{global_comm:.1f}ms (global)")
    w(f"    => Increases {global_comm/local_comm:.0f}x when latency "
      f"goes from 1ms to 250ms")
    w(f"  - At Global latency, Comm dominates: "
      f"{global_comm/global_work:.1f}x more than Work cost")

    # ----------------------------------------------------------
    # Section 4: P99 Tail Latency Analysis
    # ----------------------------------------------------------
    w()
    w("=" * 65)
    w("  SECTION 4: TAIL LATENCY ANALYSIS (P99)")
    w("=" * 65)
    w()
    w(f"  {'Profile':<12} {'Median':>9} {'P95':>9} "
      f"{'P99':>9} {'P99 overhead':>14}")
    w(f"  {'-'*58}")

    for profile in PROFILE_ORDER:
        d      = df[df["latency_profile"] == profile]["total_time_ms"]
        median = d.median()
        p95    = d.quantile(0.95)
        p99    = d.quantile(0.99)
        overhead = (p99 - median) / median * 100
        w(f"  {profile:<12} {median:>8.1f}ms {p95:>8.1f}ms "
          f"{p99:>8.1f}ms {overhead:>12.1f}%")

    w()
    w("  Interpretation:")
    w("  - Local: High P99 overhead (+32%) due to HTTP/OS jitter")
    w("    being significant relative to small total time")
    w("  - Global: Low P99 overhead (+1%) because deterministic")
    w("    sleep() dominates — distribution becomes very tight")
    w("  => Always report P99, not just Mean, in distributed systems")

    # ----------------------------------------------------------
    # Footer
    # ----------------------------------------------------------
    w()
    w("=" * 65)
    w(f"  End of Report — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    w("=" * 65)

    # Ghi ra file
    os.makedirs(config.ANALYSIS_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(output))

    print(f"[STATS] Saved: {OUTPUT_FILE}")
    print(f"[STATS] Lines: {len(output)}")

    # In ra terminal luon
    print()
    print("\n".join(output))


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
if __name__ == "__main__":
    generate_stats()