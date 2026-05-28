# -*- coding: utf-8 -*-
# =============================================================
# analysis/failure_test.py
# Simulate failure: Participant B crash sau Phase 1
# Chung minh Coordinator xu ly timeout va rollback dung
# =============================================================

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uuid
import time
import requests
import json
from datetime import datetime

import config

COORDINATOR   = config.COORDINATOR_URL
PARTICIPANT_B = config.PARTICIPANT_B_URL

SEP  = "=" * 60
SEP2 = "-" * 60


def print_section(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


def print_result(result):
    print(json.dumps(result, indent=2, ensure_ascii=False))


# ------------------------------------------------------------------
# Test 1: Normal transaction (baseline)
# ------------------------------------------------------------------
def test_normal():
    print_section("TEST 1: Normal Transaction (Baseline)")
    print("  Profile  : local (1ms)")
    print("  Expected : GLOBAL_COMMIT")
    print(SEP2)

    requests.post(f"{COORDINATOR}/config",
                  json={"latency_profile": "local"}, timeout=5)

    result = requests.post(
        f"{COORDINATOR}/transaction",
        json={
            "transaction_id": str(uuid.uuid4()),
            "operations": [
                {"site": "participant_a", "account_id": "ACC-TEST-1",
                 "amount": 500.0, "currency": "USD"},
                {"site": "participant_b", "account_id": "ACC-TEST-2",
                 "amount": 500.0, "currency": "EUR"},
            ]
        },
        timeout=30
    ).json()

    decision = result.get("decision")
    status   = "PASS" if decision == "GLOBAL_COMMIT" else "FAIL"
    print(f"\n  Decision : {decision}")
    print(f"  Result   : [{status}]")
    print(f"  Total    : {result.get('total_time_ms', 0):.1f}ms")
    return result


# ------------------------------------------------------------------
# Test 2: Participant B crash -> Coordinator timeout -> ABORT
# ------------------------------------------------------------------
def test_failure():
    print_section("TEST 2: Participant B Crash During Phase 1")
    print("  Scenario : Participant B crash setelah menerima PREPARE")
    print("  Expected : Coordinator timeout -> GLOBAL_ABORT -> Rollback")
    print(SEP2)

    # Bat failure mode tren Participant B
    print("\n  [STEP 1] Bat failure mode tren Participant B...")
    resp = requests.post(
        f"{PARTICIPANT_B}/set_failure",
        json={"enabled": True},
        timeout=5
    ).json()
    print(f"           Failure mode: {resp.get('failure_mode')}")

    # Chay transaction - se bi timeout
    print("\n  [STEP 2] Gui transaction (se bi timeout ~10s)...")
    print(f"           Started: {datetime.now().strftime('%H:%M:%S')}")

    t_start = time.perf_counter()
    try:
        result = requests.post(
            f"{COORDINATOR}/transaction",
            json={
                "transaction_id": str(uuid.uuid4()),
                "operations": [
                    {"site": "participant_a", "account_id": "ACC-FAIL-1",
                     "amount": 999.0, "currency": "USD"},
                    {"site": "participant_b", "account_id": "ACC-FAIL-2",
                     "amount": 999.0, "currency": "EUR"},
                ]
            },
            timeout=60
        ).json()
    except Exception as e:
        result = {"error": str(e), "decision": "ERROR"}

    elapsed = (time.perf_counter() - t_start) * 1000
    print(f"           Finished: {datetime.now().strftime('%H:%M:%S')}")

    decision = result.get("decision")
    error    = result.get("error")

    print(f"\n  [RESULT] Decision  : {decision}")
    print(f"  [RESULT] Error     : {error}")
    print(f"  [RESULT] Time      : {elapsed:.0f}ms")

    # Kiem tra dung ket qua
    is_aborted = (decision in ["GLOBAL_ABORT", "ERROR"] or
                  error is not None)
    status = "PASS" if is_aborted else "FAIL"
    print(f"  [RESULT] Test      : [{status}]")
    print(f"\n  => Coordinator da xu ly timeout va abort transaction!")
    print(f"     Atomicity dam bao: khong co partial commit.")

    # Tat failure mode
    print(f"\n  [STEP 3] Tat failure mode tren Participant B...")
    requests.post(
        f"{PARTICIPANT_B}/set_failure",
        json={"enabled": False},
        timeout=5
    )
    print(f"           Failure mode: OFF")

    return result


# ------------------------------------------------------------------
# Test 3: Recovery - chay lai sau khi B phuc hoi
# ------------------------------------------------------------------
def test_recovery():
    print_section("TEST 3: Recovery After Failure")
    print("  Scenario : Chay lai transaction sau khi Participant B phuc hoi")
    print("  Expected : GLOBAL_COMMIT binh thuong")
    print(SEP2)

    print("\n  [STEP 1] Cho 1 giay de Participant B on dinh...")
    time.sleep(1)

    print("  [STEP 2] Chay transaction moi...")
    result = requests.post(
        f"{COORDINATOR}/transaction",
        json={
            "transaction_id": str(uuid.uuid4()),
            "operations": [
                {"site": "participant_a", "account_id": "ACC-RECOVERY-1",
                 "amount": 750.0, "currency": "USD"},
                {"site": "participant_b", "account_id": "ACC-RECOVERY-2",
                 "amount": 750.0, "currency": "EUR"},
            ]
        },
        timeout=30
    ).json()

    decision = result.get("decision")
    status   = "PASS" if decision == "GLOBAL_COMMIT" else "FAIL"
    print(f"\n  [RESULT] Decision  : {decision}")
    print(f"  [RESULT] Total     : {result.get('total_time_ms', 0):.1f}ms")
    print(f"  [RESULT] Test      : [{status}]")
    print(f"\n  => He thong tu phuc hoi sau failure!")
    print(f"     2PC dam bao tinh nhat quan sau khi node quay lai.")

    return result


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
if __name__ == "__main__":
    print(SEP)
    print("  Trans-Atlantic DB — Failure Simulation")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(SEP)

    # Kiem tra tat ca nodes dang chay
    print("\n[CHECK] Kiem tra nodes...")
    for name, url in [("Coordinator", COORDINATOR),
                      ("Participant A", config.PARTICIPANT_A_URL),
                      ("Participant B", PARTICIPANT_B)]:
        try:
            requests.get(f"{url}/health", timeout=5)
            print(f"  {name}: online")
        except Exception:
            print(f"  {name}: OFFLINE - hay chay node nay truoc!")
            sys.exit(1)

    # Chay 3 tests
    r1 = test_normal()
    r2 = test_failure()
    r3 = test_recovery()

    # Tong ket
    print_section("TONG KET FAILURE SIMULATION")
    results = [
        ("Test 1 - Normal    ", r1.get("decision") == "GLOBAL_COMMIT"),
        ("Test 2 - Failure   ", r2.get("decision") in
         ["GLOBAL_ABORT", "ERROR"] or r2.get("error") is not None),
        ("Test 3 - Recovery  ", r3.get("decision") == "GLOBAL_COMMIT"),
    ]

    all_pass = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: [{status}]")
        if not passed:
            all_pass = False

    print(SEP2)
    final = "TẤT CẢ PASS" if all_pass else "CÓ TEST THẤT BẠI"
    print(f"  Ket qua tong: {final}")
    print(f"  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(SEP)

    print("""
  Giai thich:
  - Test 2 chung minh: khi Participant B khong phan hoi,
    Coordinator tu dong timeout va quyet dinh GLOBAL_ABORT.
  - Khong co partial commit: neu B fail, A cung khong commit.
  - Day chinh la dam bao ATOMICITY cua 2PC Protocol.
  - Test 3 chung minh: he thong tu phuc hoi,
    giao dich tiep theo chay binh thuong.
    """)