# =============================================================
# data/generate_data.py — Tạo dataset và load vào 2 SQLite sites
# =============================================================

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import random
import uuid
from datetime import datetime, timedelta

import pandas as pd
from faker import Faker

import config

fake = Faker()
random.seed(42)
Faker.seed(42)

# ------------------------------------------------------------------
# 1. Tạo 10,000 records Financial Transactions
# ------------------------------------------------------------------

def generate_transactions(n=10000):
    """Tạo n records financial transactions giả lập."""
    print(f"[DATA] Đang tạo {n} records...")

    records = []
    base_time = datetime(2024, 1, 1)

    for i in range(n):
        region = "US" if i % 2 == 0 else "EU"

        record = {
            "transaction_id": str(uuid.uuid4()),
            "account_id":     f"ACC-{random.randint(1000, 9999)}",
            "amount":         round(random.uniform(10.0, 50000.0), 2),
            "currency":       "USD" if region == "US" else "EUR",
            "region":         region,
            "status":         "pending",
            "timestamp":      (base_time + timedelta(
                                  seconds=random.randint(0, 365*24*3600)
                              )).strftime("%Y-%m-%d %H:%M:%S"),
        }
        records.append(record)

    df = pd.DataFrame(records)
    print(f"[DATA] Tạo xong: {len(df)} records")
    print(f"       US: {len(df[df.region == 'US'])} records")
    print(f"       EU: {len(df[df.region == 'EU'])} records")
    return df


# ------------------------------------------------------------------
# 2. Lưu CSV
# ------------------------------------------------------------------

def save_csv(df):
    os.makedirs(config.DATA_DIR, exist_ok=True)
    df.to_csv(config.TRANSACTIONS_CSV, index=False)
    print(f"[DATA] Đã lưu CSV: {config.TRANSACTIONS_CSV}")


# ------------------------------------------------------------------
# 3. Horizontal Fragmentation → load vào 2 SQLite sites
# ------------------------------------------------------------------

def load_to_sqlite(df):
    """
    Site A (site_a.db) → region = 'US'
    Site B (site_b.db) → region = 'EU'
    """
    df_a = df[df["region"] == "US"].copy()
    conn_a = sqlite3.connect(config.DB_SITE_A)
    conn_a.execute(config.CREATE_TABLE_SQL)
    df_a.to_sql("transactions", conn_a, if_exists="replace", index=False)
    conn_a.commit()
    conn_a.close()
    print(f"[DATA] Site A (US): {len(df_a)} records → {config.DB_SITE_A}")

    df_b = df[df["region"] == "EU"].copy()
    conn_b = sqlite3.connect(config.DB_SITE_B)
    conn_b.execute(config.CREATE_TABLE_SQL)
    df_b.to_sql("transactions", conn_b, if_exists="replace", index=False)
    conn_b.commit()
    conn_b.close()
    print(f"[DATA] Site B (EU): {len(df_b)} records → {config.DB_SITE_B}")


# ------------------------------------------------------------------
# 4. Verify
# ------------------------------------------------------------------

def verify():
    print("\n[VERIFY] Kiểm tra dữ liệu đã load...")

    conn_a = sqlite3.connect(config.DB_SITE_A)
    count_a = conn_a.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    sample_a = conn_a.execute(
        "SELECT transaction_id, account_id, amount, region "
        "FROM transactions LIMIT 3").fetchall()
    conn_a.close()

    conn_b = sqlite3.connect(config.DB_SITE_B)
    count_b = conn_b.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    sample_b = conn_b.execute(
        "SELECT transaction_id, account_id, amount, region "
        "FROM transactions LIMIT 3").fetchall()
    conn_b.close()

    print(f"\n  Site A (site_a.db): {count_a} records")
    for row in sample_a:
        print(f"    {row}")

    print(f"\n  Site B (site_b.db): {count_b} records")
    for row in sample_b:
        print(f"    {row}")

    print(f"\n  Tổng: {count_a + count_b} records")
    print("  Fragmentation: OK ✓" if count_a > 0 and count_b > 0
          else "  Fragmentation: FAILED ✗")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 55)
    print("  Trans-Atlantic DB — Data Generator")
    print("=" * 55)

    df = generate_transactions(10000)
    save_csv(df)
    load_to_sqlite(df)
    verify()

    print("\n[DONE] Dataset sẵn sàng!")