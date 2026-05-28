# -*- coding: utf-8 -*-
# =============================================================
# analysis/charts.py — Vẽ 4 biểu đồ từ benchmark results
# =============================================================

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

import config

# ------------------------------------------------------------------
# Setup style
# ------------------------------------------------------------------
plt.rcParams.update({
    "figure.facecolor":  "white",
    "axes.facecolor":    "white",
    "axes.grid":         True,
    "grid.alpha":        0.3,
    "grid.linestyle":    "--",
    "font.size":         11,
    "axes.titlesize":    13,
    "axes.titleweight":  "bold",
    "axes.labelsize":    11,
    "xtick.labelsize":   10,
    "ytick.labelsize":   10,
    "legend.fontsize":   10,
})

PROFILE_ORDER  = ["local", "regional", "global"]
PROFILE_LABELS = ["Local\n(1ms)", "Regional\n(50ms)", "Global\n(250ms)"]
COLORS = {
    "local":    "#2ecc71",
    "regional": "#f39c12",
    "global":   "#e74c3c",
}
WORK_COLOR    = "#3498db"
NETWORK_COLOR = "#e74c3c"


# ------------------------------------------------------------------
# Load data
# ------------------------------------------------------------------
def load_data():
    df = pd.read_csv(config.BENCHMARK_CSV)
    df = df[df["total_time_ms"].notna()]
    print(f"[CHARTS] Loaded {len(df)} rows from {config.BENCHMARK_CSV}")
    return df


# ------------------------------------------------------------------
# Chart 1: Mean / Median / P99 grouped bar chart
# ------------------------------------------------------------------
def chart_latency_statistics(df):
    fig, ax = plt.subplots(figsize=(10, 6))

    x      = np.arange(len(PROFILE_ORDER))
    width  = 0.25
    means, medians, p99s = [], [], []

    for profile in PROFILE_ORDER:
        d = df[df["latency_profile"] == profile]["total_time_ms"]
        means.append(d.mean())
        medians.append(d.median())
        p99s.append(d.quantile(0.99))

    bars1 = ax.bar(x - width, means,   width, label="Mean",   color="#3498db", alpha=0.85)
    bars2 = ax.bar(x,         medians, width, label="Median", color="#2ecc71", alpha=0.85)
    bars3 = ax.bar(x + width, p99s,    width, label="P99",    color="#e74c3c", alpha=0.85)

    # Gán nhãn giá trị lên đỉnh mỗi bar
    for bars in [bars1, bars2, bars3]:
        for bar in bars:
            h = bar.get_height()
            label = f"{h:.0f}ms" if h < 1000 else f"{h/1000:.2f}s"
            ax.annotate(
                label,
                xy=(bar.get_x() + bar.get_width() / 2, h),
                xytext=(0, 4), textcoords="offset points",
                ha="center", va="bottom", fontsize=9
            )

    ax.set_xticks(x)
    ax.set_xticklabels(PROFILE_LABELS)
    ax.set_xlabel("Network Latency Profile")
    ax.set_ylabel("Transaction Time (ms)")
    ax.set_title("Chart 1: Transaction Time Statistics by Latency Profile\n"
                 "(Mean, Median, P99 Tail Latency)")
    ax.legend()
    ax.set_ylim(0, max(p99s) * 1.2)

    plt.tight_layout()
    path = os.path.join(config.ANALYSIS_DIR, "chart1_latency_statistics.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[CHARTS] Saved: {path}")


# ------------------------------------------------------------------
# Chart 2: Work vs Network Wait stacked bar
# ------------------------------------------------------------------
def chart_work_vs_network(df):
    fig, ax = plt.subplots(figsize=(9, 6))

    x     = np.arange(len(PROFILE_ORDER))
    width = 0.5
    works, networks = [], []

    for profile in PROFILE_ORDER:
        d = df[df["latency_profile"] == profile]
        works.append(d["work_ms"].mean())
        networks.append(d["network_wait_ms"].mean())

    bars_work = ax.bar(x, works,    width, label="Doing Work (CPU + I/O)",
                       color=WORK_COLOR, alpha=0.85)
    bars_net  = ax.bar(x, networks, width, bottom=works,
                       label="Waiting for Network",
                       color=NETWORK_COLOR, alpha=0.85)

    # Gán nhãn % lên phần network
    for i, (w, n) in enumerate(zip(works, networks)):
        total    = w + n
        pct_net  = n / total * 100
        pct_work = w / total * 100
        # % network ở giữa vùng network
        ax.text(i, w + n / 2, f"{pct_net:.1f}%\nNetwork",
                ha="center", va="center", fontsize=9,
                color="white", fontweight="bold")
        # % work ở giữa vùng work
        ax.text(i, w / 2, f"{pct_work:.1f}%\nWork",
                ha="center", va="center", fontsize=9,
                color="white", fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(PROFILE_LABELS)
    ax.set_xlabel("Network Latency Profile")
    ax.set_ylabel("Time (ms)")
    ax.set_title("Chart 2: Cost of Coordination\n"
                 "Work Time vs. Network Wait Time per Transaction")
    ax.legend(loc="upper left")

    plt.tight_layout()
    path = os.path.join(config.ANALYSIS_DIR, "chart2_work_vs_network.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[CHARTS] Saved: {path}")


# ------------------------------------------------------------------
# Chart 3: Cost of Coordination % line chart
# ------------------------------------------------------------------
def chart_coordination_cost(df):
    fig, ax = plt.subplots(figsize=(9, 5))

    coord_costs = []
    for profile in PROFILE_ORDER:
        d = df[df["latency_profile"] == profile]
        coord_costs.append(d["coord_cost_pct"].mean())

    latency_vals = [1, 50, 250]

    ax.plot(latency_vals, coord_costs,
            marker="o", linewidth=2.5, markersize=10,
            color="#8e44ad", label="Cost of Coordination (%)")

    # Annotate each point
    for x_val, y_val, profile in zip(latency_vals, coord_costs, PROFILE_ORDER):
        ax.annotate(
            f"{y_val:.1f}%\n({profile})",
            xy=(x_val, y_val),
            xytext=(15, -20), textcoords="offset points",
            fontsize=10, color="#8e44ad",
            arrowprops=dict(arrowstyle="->", color="#8e44ad", lw=1.2)
        )

    ax.axhline(y=50, color="gray", linestyle="--",
               alpha=0.5, label="50% threshold")

    ax.set_xscale("log")
    ax.set_xticks(latency_vals)
    ax.set_xticklabels(["1ms\n(Local)", "50ms\n(Regional)", "250ms\n(Global)"])
    ax.set_xlabel("One-way Network Latency (ms, log scale)")
    ax.set_ylabel("Cost of Coordination (%)")
    ax.set_title("Chart 3: Cost of Coordination vs. Network Latency\n"
                 "('What % of transaction time is waiting for the network?')")
    ax.set_ylim(0, 105)
    ax.legend()

    plt.tight_layout()
    path = os.path.join(config.ANALYSIS_DIR, "chart3_coordination_cost.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[CHARTS] Saved: {path}")


# ------------------------------------------------------------------
# Chart 4: Distribution boxplot (per profile)
# ------------------------------------------------------------------
def chart_distribution_boxplot(df):
    fig, ax = plt.subplots(figsize=(9, 6))

    data   = []
    colors = []
    for profile in PROFILE_ORDER:
        d = df[df["latency_profile"] == profile]["total_time_ms"].values
        data.append(d)
        colors.append(COLORS[profile])

    bp = ax.boxplot(
        data,
        labels=PROFILE_LABELS,
        patch_artist=True,
        medianprops=dict(color="black", linewidth=2),
        whiskerprops=dict(linewidth=1.5),
        capprops=dict(linewidth=1.5),
        flierprops=dict(marker="o", markersize=4, alpha=0.5),
    )

    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    ax.set_xlabel("Network Latency Profile")
    ax.set_ylabel("Total Transaction Time (ms)")
    ax.set_title("Chart 4: Transaction Time Distribution\n"
                 "(Spread and Outliers per Profile)")

    # Legend
    patches = [
        mpatches.Patch(color=COLORS[p], alpha=0.7, label=f"{p.capitalize()}")
        for p in PROFILE_ORDER
    ]
    ax.legend(handles=patches)

    plt.tight_layout()
    path = os.path.join(config.ANALYSIS_DIR, "chart4_distribution_boxplot.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[CHARTS] Saved: {path}")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 50)
    print("  Trans-Atlantic DB — Chart Generator")
    print("=" * 50)

    df = load_data()

    # In tong ket truoc khi ve
    print("\n  Summary:")
    print(f"  {'Profile':<12} {'Mean':>8} {'Median':>8} "
          f"{'P99':>8} {'CoordCost':>12}")
    print(f"  {'-'*52}")
    for profile in PROFILE_ORDER:
        d      = df[df["latency_profile"] == profile]
        mean   = d["total_time_ms"].mean()
        median = d["total_time_ms"].median()
        p99    = d["total_time_ms"].quantile(0.99)
        cost   = d["coord_cost_pct"].mean()
        print(f"  {profile:<12} {mean:>7.1f}ms {median:>7.1f}ms "
              f"{p99:>7.1f}ms {cost:>10.1f}%")

    print("\n  Generating charts...")
    chart_latency_statistics(df)
    chart_work_vs_network(df)
    chart_coordination_cost(df)
    chart_distribution_boxplot(df)

    print("\n[DONE] 4 charts saved to analysis/")
    print("       chart1_latency_statistics.png")
    print("       chart2_work_vs_network.png")
    print("       chart3_coordination_cost.png")
    print("       chart4_distribution_boxplot.png")