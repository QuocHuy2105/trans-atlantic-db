# =============================================================
# participants/participant_a.py — Site A (US Region)
# Flask server lắng nghe lệnh từ Coordinator
# Port: 5001
# =============================================================
# -*- coding: utf-8 -*-
import sys
import io
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import time
import uuid
import logging
from datetime import datetime

from flask import Flask, request, jsonify
import config

# ------------------------------------------------------------------
# Setup logging
# ------------------------------------------------------------------
os.makedirs(config.LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [PARTICIPANT_A] %(message)s",
    handlers=[
        logging.FileHandler(f"{config.LOG_DIR}/participant_a.log", encoding='utf-8'),
        logging.StreamHandler(io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)),
    ]
)
log = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Flask app
# ------------------------------------------------------------------
app = Flask(__name__)

# State hiện tại của participant (dùng cho demo/log)
current_state = config.STATE_INITIAL

# Latency profile hiện tại — sẽ được set bởi Coordinator
current_latency = 0.0

# Biến giả lập failure (dùng ở bước sau)
simulate_failure = False


# ------------------------------------------------------------------
# Helper: inject latency
# ------------------------------------------------------------------
def inject_latency():
    """Simulate network delay trước khi trả response."""
    if current_latency > 0:
        log.info(f"  [NET] Simulating {current_latency*1000:.0f}ms network delay...")
        time.sleep(current_latency)


# ------------------------------------------------------------------
# Helper: kết nối SQLite Site A
# ------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(config.DB_SITE_A)
    conn.row_factory = sqlite3.Row
    return conn


# ------------------------------------------------------------------
# Endpoint: SET CONFIG
# Coordinator gọi đầu tiên để set latency profile
# ------------------------------------------------------------------
@app.route("/config", methods=["POST"])
def set_config():
    global current_latency
    data = request.get_json()
    profile = data.get("latency_profile", "local")
    current_latency = config.LATENCY_PROFILES.get(profile, 0.0)
    log.info(f"[CONFIG] Latency profile set: {profile} "
             f"({current_latency*1000:.0f}ms)")
    return jsonify({"status": "ok", "latency_ms": current_latency * 1000})


# ------------------------------------------------------------------
# Endpoint: SET FAILURE MODE
# Dùng để simulate crash ở bước failure testing
# ------------------------------------------------------------------
@app.route("/set_failure", methods=["POST"])
def set_failure():
    global simulate_failure
    data = request.get_json()
    simulate_failure = data.get("enabled", False)
    log.info(f"[CONFIG] Failure simulation: {'ON' if simulate_failure else 'OFF'}")
    return jsonify({"status": "ok", "failure_mode": simulate_failure})


# ------------------------------------------------------------------
# Phase 1: PREPARE
# Coordinator hỏi: "Có thể commit transaction này không?"
# ------------------------------------------------------------------
@app.route("/prepare", methods=["POST"])
def prepare():
    global current_state
    data = request.get_json()

    transaction_id = data.get("transaction_id")
    operations     = data.get("operations", [])

    log.info(f"[PHASE 1] Nhận PREPARE — transaction_id={transaction_id}")
    current_state = config.STATE_READY

    # Inject latency: simulate thời gian message đi qua mạng
    inject_latency()

    # Giả lập failure nếu được bật
    if simulate_failure:
        log.warning(f"[FAILURE] Simulating crash! Không trả lời PREPARE.")
        # Không trả response — coordinator sẽ timeout
        time.sleep(config.TIMEOUT_SECONDS + 1)

    # Kiểm tra xem có thể thực thi operations không
    try:
        conn = get_db()

        # Validate: kiểm tra transaction_id chưa tồn tại (tránh duplicate)
        existing = conn.execute(
            "SELECT transaction_id FROM transactions WHERE transaction_id = ?",
            (transaction_id,)
        ).fetchone()

        if existing:
            log.warning(f"[PHASE 1] VOTE_ABORT — transaction đã tồn tại: {transaction_id}")
            conn.close()
            return jsonify({
                "vote":           config.MSG_VOTE_ABORT,
                "participant":    "participant_a",
                "transaction_id": transaction_id,
                "reason":         "duplicate_transaction"
            })

        conn.close()

        log.info(f"[PHASE 1] VOTE_COMMIT ✓ — sẵn sàng commit {transaction_id}")
        return jsonify({
            "vote":           config.MSG_VOTE_COMMIT,
            "participant":    "participant_a",
            "transaction_id": transaction_id,
        })

    except Exception as e:
        log.error(f"[PHASE 1] VOTE_ABORT — lỗi DB: {e}")
        return jsonify({
            "vote":           config.MSG_VOTE_ABORT,
            "participant":    "participant_a",
            "transaction_id": transaction_id,
            "reason":         str(e)
        })


# ------------------------------------------------------------------
# Phase 2a: COMMIT
# Coordinator ra lệnh: "Tất cả đồng ý — hãy commit!"
# ------------------------------------------------------------------
@app.route("/commit", methods=["POST"])
def commit():
    global current_state
    data = request.get_json()

    transaction_id = data.get("transaction_id")
    operations     = data.get("operations", [])

    log.info(f"[PHASE 2] Nhận GLOBAL_COMMIT — transaction_id={transaction_id}")

    # Inject latency
    inject_latency()

    try:
        conn = get_db()

        # Thực thi: insert transaction vào Site A với status = committed
        for op in operations:
            if op.get("site") == "participant_a":
                conn.execute(
                    """INSERT OR REPLACE INTO transactions
                       (transaction_id, account_id, amount, currency,
                        region, status, timestamp)
                       VALUES (?, ?, ?, ?, ?, 'committed', ?)""",
                    (
                        transaction_id,
                        op.get("account_id"),
                        op.get("amount"),
                        op.get("currency", "USD"),
                        "US",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                )

        conn.commit()
        conn.close()

        current_state = config.STATE_COMMIT
        log.info(f"[PHASE 2] COMMITTED ✓ — {transaction_id}")

        return jsonify({
            "ack":            config.MSG_ACK,
            "participant":    "participant_a",
            "transaction_id": transaction_id,
            "status":         "committed"
        })

    except Exception as e:
        log.error(f"[PHASE 2] Commit thất bại: {e}")
        current_state = config.STATE_ABORT
        return jsonify({
            "ack":            config.MSG_ACK,
            "participant":    "participant_a",
            "transaction_id": transaction_id,
            "status":         "error",
            "reason":         str(e)
        }), 500


# ------------------------------------------------------------------
# Phase 2b: ABORT
# Coordinator ra lệnh: "Có vấn đề — hãy rollback!"
# ------------------------------------------------------------------
@app.route("/abort", methods=["POST"])
def abort():
    global current_state
    data = request.get_json()

    transaction_id = data.get("transaction_id")

    log.info(f"[PHASE 2] Nhận GLOBAL_ABORT — transaction_id={transaction_id}")

    # Inject latency
    inject_latency()

    # Rollback: xoá transaction nếu đã insert (safety net)
    try:
        conn = get_db()
        conn.execute(
            "DELETE FROM transactions WHERE transaction_id = ? "
            "AND status = 'pending'",
            (transaction_id,)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"[ABORT] Rollback lỗi: {e}")

    current_state = config.STATE_ABORT
    log.info(f"[PHASE 2] ABORTED ✓ — {transaction_id}")

    return jsonify({
        "ack":            config.MSG_ACK,
        "participant":    "participant_a",
        "transaction_id": transaction_id,
        "status":         "aborted"
    })


# ------------------------------------------------------------------
# Endpoint: HEALTH CHECK
# ------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status":      "online",
        "participant": "participant_a",
        "site":        "US",
        "db":          config.DB_SITE_A,
        "state":       current_state,
        "latency_ms":  current_latency * 1000,
    })


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
if __name__ == "__main__":
    log.info("=" * 50)
    log.info("  Participant A — Site US — Port 5001")
    log.info("=" * 50)
    app.run(host="127.0.0.1", port=5001, debug=False)