# =============================================================
# participants/participant_b.py — Site B (EU Region)
# Flask server lắng nghe lệnh từ Coordinator
# Port: 5002
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
    format="%(asctime)s [PARTICIPANT_B] %(message)s",
    handlers=[
        logging.FileHandler(f"{config.LOG_DIR}/participant_b.log", encoding='utf-8'),
        logging.StreamHandler(io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)),
    ]
)
log = logging.getLogger(__name__)

app = Flask(__name__)

current_state   = config.STATE_INITIAL
current_latency = 0.0
simulate_failure = False


def inject_latency():
    if current_latency > 0:
        log.info(f"  [NET] Simulating {current_latency*1000:.0f}ms network delay...")
        time.sleep(current_latency)


def get_db():
    conn = sqlite3.connect(config.DB_SITE_B)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/config", methods=["POST"])
def set_config():
    global current_latency
    data = request.get_json()
    profile = data.get("latency_profile", "local")
    current_latency = config.LATENCY_PROFILES.get(profile, 0.0)
    log.info(f"[CONFIG] Latency profile set: {profile} "
             f"({current_latency*1000:.0f}ms)")
    return jsonify({"status": "ok", "latency_ms": current_latency * 1000})


@app.route("/set_failure", methods=["POST"])
def set_failure():
    global simulate_failure
    data = request.get_json()
    simulate_failure = data.get("enabled", False)
    log.info(f"[CONFIG] Failure simulation: {'ON' if simulate_failure else 'OFF'}")
    return jsonify({"status": "ok", "failure_mode": simulate_failure})


@app.route("/prepare", methods=["POST"])
def prepare():
    global current_state
    data = request.get_json()

    transaction_id = data.get("transaction_id")
    operations     = data.get("operations", [])

    log.info(f"[PHASE 1] Nhận PREPARE — transaction_id={transaction_id}")
    current_state = config.STATE_READY

    inject_latency()

    if simulate_failure:
        log.warning(f"[FAILURE] Simulating crash! Không trả lời PREPARE.")
        time.sleep(config.TIMEOUT_SECONDS + 1)

    try:
        conn = get_db()
        existing = conn.execute(
            "SELECT transaction_id FROM transactions WHERE transaction_id = ?",
            (transaction_id,)
        ).fetchone()

        if existing:
            log.warning(f"[PHASE 1] VOTE_ABORT — duplicate: {transaction_id}")
            conn.close()
            return jsonify({
                "vote":           config.MSG_VOTE_ABORT,
                "participant":    "participant_b",
                "transaction_id": transaction_id,
                "reason":         "duplicate_transaction"
            })

        conn.close()
        log.info(f"[PHASE 1] VOTE_COMMIT ✓ — {transaction_id}")
        return jsonify({
            "vote":           config.MSG_VOTE_COMMIT,
            "participant":    "participant_b",
            "transaction_id": transaction_id,
        })

    except Exception as e:
        log.error(f"[PHASE 1] VOTE_ABORT — lỗi DB: {e}")
        return jsonify({
            "vote":           config.MSG_VOTE_ABORT,
            "participant":    "participant_b",
            "transaction_id": transaction_id,
            "reason":         str(e)
        })


@app.route("/commit", methods=["POST"])
def commit():
    global current_state
    data = request.get_json()

    transaction_id = data.get("transaction_id")
    operations     = data.get("operations", [])

    log.info(f"[PHASE 2] Nhận GLOBAL_COMMIT — transaction_id={transaction_id}")
    inject_latency()

    try:
        conn = get_db()

        for op in operations:
            if op.get("site") == "participant_b":
                conn.execute(
                    """INSERT OR REPLACE INTO transactions
                       (transaction_id, account_id, amount, currency,
                        region, status, timestamp)
                       VALUES (?, ?, ?, ?, ?, 'committed', ?)""",
                    (
                        transaction_id,
                        op.get("account_id"),
                        op.get("amount"),
                        op.get("currency", "EUR"),
                        "EU",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                )

        conn.commit()
        conn.close()

        current_state = config.STATE_COMMIT
        log.info(f"[PHASE 2] COMMITTED ✓ — {transaction_id}")

        return jsonify({
            "ack":            config.MSG_ACK,
            "participant":    "participant_b",
            "transaction_id": transaction_id,
            "status":         "committed"
        })

    except Exception as e:
        log.error(f"[PHASE 2] Commit thất bại: {e}")
        current_state = config.STATE_ABORT
        return jsonify({
            "ack":            config.MSG_ACK,
            "participant":    "participant_b",
            "transaction_id": transaction_id,
            "status":         "error",
            "reason":         str(e)
        }), 500


@app.route("/abort", methods=["POST"])
def abort():
    global current_state
    data = request.get_json()
    transaction_id = data.get("transaction_id")

    log.info(f"[PHASE 2] Nhận GLOBAL_ABORT — transaction_id={transaction_id}")
    inject_latency()

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
        "participant":    "participant_b",
        "transaction_id": transaction_id,
        "status":         "aborted"
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status":      "online",
        "participant": "participant_b",
        "site":        "EU",
        "db":          config.DB_SITE_B,
        "state":       current_state,
        "latency_ms":  current_latency * 1000,
    })


if __name__ == "__main__":
    log.info("=" * 50)
    log.info("  Participant B — Site EU — Port 5002")
    log.info("=" * 50)
    app.run(host="127.0.0.1", port=5002, debug=False)