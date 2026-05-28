# =============================================================
# config.py — Cấu hình trung tâm cho Trans-Atlantic DB Project
# =============================================================

# --- Địa chỉ các nodes ---
COORDINATOR_URL   = "http://127.0.0.1:5000"
PARTICIPANT_A_URL = "http://127.0.0.1:5001"
PARTICIPANT_B_URL = "http://127.0.0.1:5002"

PARTICIPANTS = {
    "participant_a": PARTICIPANT_A_URL,
    "participant_b": PARTICIPANT_B_URL,
}

# --- Latency profiles (đơn vị: giây) ---
LATENCY_PROFILES = {
    "local":    0.001,   # 1ms   — cùng datacenter
    "regional": 0.050,   # 50ms  — liên vùng (US East <-> US West)
    "global":   0.250,   # 250ms — Trans-Atlantic (US <-> EU)
}

# --- Cấu hình benchmark ---
BENCHMARK_RUNS  = 100   # Số lần chạy mỗi latency profile
TIMEOUT_SECONDS = 10    # Timeout cho mỗi HTTP request

# --- Đường dẫn file ---
DATA_DIR         = "data"
LOG_DIR          = "logs"
ANALYSIS_DIR     = "analysis"

DB_SITE_A        = "data/site_a.db"
DB_SITE_B        = "data/site_b.db"
TRANSACTIONS_CSV = "data/financial_transactions.csv"
BENCHMARK_CSV    = "analysis/benchmark_results.csv"

# --- Database schema ---
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id  TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL,
    amount          REAL NOT NULL,
    currency        TEXT NOT NULL,
    region          TEXT NOT NULL,
    status          TEXT DEFAULT 'pending',
    timestamp       TEXT NOT NULL
);
"""

# --- 2PC message types ---
MSG_PREPARE       = "PREPARE"
MSG_VOTE_COMMIT   = "VOTE_COMMIT"
MSG_VOTE_ABORT    = "VOTE_ABORT"
MSG_GLOBAL_COMMIT = "GLOBAL_COMMIT"
MSG_GLOBAL_ABORT  = "GLOBAL_ABORT"
MSG_ACK           = "ACK"

# --- 2PC states ---
STATE_INITIAL = "INITIAL"
STATE_WAIT    = "WAIT"
STATE_READY   = "READY"
STATE_COMMIT  = "COMMIT"
STATE_ABORT   = "ABORT"