# =============================================================
# analysis/benchmark.py
# Chạy 100 transactions x 3 latency profiles
# Thu thập số liệu và xuất ra CSV
# =============================================================
# -*- coding: utf-8 -*-
import os
os.environ["PYTHONIOENCODING"] = "utf-8"

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import uuid
import requests
import pandas as pd
from datetime import datetime

import config

# ------------------------------------------------------------------
# Cấu hình
# ------------------------------------------------------------------
COORDINATOR = config.COORDINATOR_URL
RUNS        = config.BENCHMARK_RUNS   # 100 lần mỗi profile
PROFILES    = ["local", "regional", "global"]

WARMUP_RUNS = 5   # Chạy warm-up để Flask ổn định trước khi đo


# ------------------------------------------------------------------
# Helper: set latency profile
# ------------------------------------------------------------------
def set_profile(profile):
    resp = requests.post(
        f"{COORDINATOR}/config",
        json={"latency_profile": profile},
        timeout=10
    )
    print(f"  [CONFIG] Profile set: {profile} "
          f"({config.LATENCY_PROFILES[profile]*1000:.0f}ms)")
    return resp.json()


# ------------------------------------------------------------------
# Helper: chạy 1 transaction và trả về kết quả
# ------------------------------------------------------------------
def run_transaction(run_index, profile):
    transaction_id = str(uuid.uuid4())
    operations = [
        {
            "site":       "participant_a",
            "account_id": f"ACC-{1000 + run_index}",
            "amount":     round(100.0 + run_index * 1.5, 2),
            "currency":   "USD",
        },
        {
            "site":       "participant_b",
            "account_id": f"ACC-{5000 + run_index}",
            "amount":     round(200.0 + run_index * 1.5, 2),
            "currency":   "EUR",
        },
    ]

    try:
        resp = requests.post(
            f"{COORDINATOR}/transaction",
            json={
                "transaction_id": transaction_id,
                "operations":     operations,
            },
            timeout=30
        )
        result = resp.json()
        result["run_index"] = run_index
        result["success"]   = (result.get("decision") == "GLOBAL_COMMIT")
        return result

    except Exception as e:
        return {
            "run_index":        run_index,
            "transaction_id":   transaction_id,
            "latency_profile":  profile,
            "latency_ms":       config.LATENCY_PROFILES[profile] * 1000,
            "decision":         "ERROR",
            "total_time_ms":    None,
            "network_wait_ms":  None,
            "work_ms":          None,
            "coord_cost_pct":   None,
            "success":          False,
            "error":            str(e),
        }


# ------------------------------------------------------------------
# Main benchmark loop
# ------------------------------------------------------------------
def run_benchmark():
    all_results = []

    print("=" * 60)
    print("  Trans-Atlantic DB — Benchmark")
    print(f"  {RUNS} runs x {len(PROFILES)} profiles = "
          f"{RUNS * len(PROFILES)} transactions")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    for profile in PROFILES:
        latency_ms = config.LATENCY_PROFILES[profile] * 1000
        print(f"\n{'='*60}")
        print(f"  PROFILE: {profile.upper()} ({latency_ms:.0f}ms)")
        print(f"{'='*60}")

        # --- Warm-up: chạy vài lần để Flask ổn định ---
        print(f"  [WARMUP] Chay {WARMUP_RUNS} warm-up runs...")
        set_profile(profile)
        for i in range(WARMUP_RUNS):
            run_transaction(i, profile)
            print(f"    Warmup {i+1}/{WARMUP_RUNS}", end="\r")
        print(f"  [WARMUP] Xong.          ")

        # --- Benchmark thực sự ---
        set_profile(profile)
        profile_results = []

        for i in range(RUNS):
            result = run_transaction(i, profile)
            profile_results.append(result)
            all_results.append(result)

            # In progress mỗi 10 lần
            if (i + 1) % 10 == 0:
                valid = [r for r in profile_results
                         if r.get("total_time_ms") is not None]
                if valid:
                    avg = sum(r["total_time_ms"] for r in valid) / len(valid)
                    print(f"  Run {i+1:3d}/{RUNS} | "
                          f"Avg total: {avg:.1f}ms")

        # --- Tóm tắt profile ---
        valid = [r for r in profile_results
                 if r.get("total_time_ms") is not None]
        if valid:
            totals      = [r["total_time_ms"]   for r in valid]
            net_waits   = [r["network_wait_ms"]  for r in valid]
            coord_costs = [r["coord_cost_pct"]   for r in valid]

            df_p = pd.DataFrame({"total": totals})
            print(f"\n  --- Ket qua {profile.upper()} ---")
            print(f"  Count  : {len(valid)}")
            print(f"  Mean   : {df_p['total'].mean():.2f}ms")
            print(f"  Median : {df_p['total'].median():.2f}ms")
            print(f"  P99    : {df_p['total'].quantile(0.99):.2f}ms")
            print(f"  Network wait (avg): "
                  f"{sum(net_waits)/len(net_waits):.2f}ms")
            print(f"  CoordCost (avg)   : "
                  f"{sum(coord_costs)/len(coord_costs):.2f}%")

    # ------------------------------------------------------------------
    # Lưu kết quả ra CSV
    # ------------------------------------------------------------------
    os.makedirs(config.ANALYSIS_DIR, exist_ok=True)
    df = pd.DataFrame(all_results)

    # Chỉ giữ các cột cần thiết
    cols = [
        "run_index", "transaction_id", "latency_profile",
        "latency_ms", "decision", "total_time_ms",
        "phase1_time_ms", "phase2_time_ms",
        "network_wait_ms", "work_ms", "coord_cost_pct",
        "success", "timestamp",
    ]
    # Chỉ lấy cột tồn tại
    cols = [c for c in cols if c in df.columns]
    df = df[cols]

    df.to_csv(config.BENCHMARK_CSV, index=False, encoding="utf-8")
    print(f"\n[SAVED] Ket qua da luu: {config.BENCHMARK_CSV}")
    print(f"[SAVED] Tong so rows  : {len(df)}")

    # ------------------------------------------------------------------
    # In tong ket
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("  TONG KET BENCHMARK")
    print(f"{'='*60}")
    print(f"  {'Profile':<12} {'Mean':>8} {'Median':>8} "
          f"{'P99':>8} {'CoordCost':>12}")
    print(f"  {'-'*52}")

    for profile in PROFILES:
        df_p = df[
            (df["latency_profile"] == profile) &
            (df["total_time_ms"].notna())
        ]
        if len(df_p) > 0:
            mean   = df_p["total_time_ms"].mean()
            median = df_p["total_time_ms"].median()
            p99    = df_p["total_time_ms"].quantile(0.99)
            cost   = df_p["coord_cost_pct"].mean()
            print(f"  {profile:<12} {mean:>7.1f}ms {median:>7.1f}ms "
                  f"{p99:>7.1f}ms {cost:>10.1f}%")

    print(f"\n  Benchmark hoan thanh luc: "
          f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    return df


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
if __name__ == "__main__":
    # Kiem tra coordinator dang chay
    try:
        resp = requests.get(f"{COORDINATOR}/health", timeout=5)
        print(f"[CHECK] Coordinator: online")
    except Exception:
        print("[ERROR] Coordinator chua chay!")
        print("        Hay chay: python coordinator/coordinator.py")
        sys.exit(1)

    # Kiem tra participants
    for name, url in config.PARTICIPANTS.items():
        try:
            requests.get(f"{url}/health", timeout=5)
            print(f"[CHECK] {name}: online")
        except Exception:
            print(f"[ERROR] {name} chua chay!")
            print(f"        Hay chay: python participants/{name}.py")
            sys.exit(1)

    print()
    run_benchmark()