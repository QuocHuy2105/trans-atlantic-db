# =============================================================
# coordinator/coordinator.py — Điều phối 2PC Protocol
# Flask server nhận transaction requests từ client
# Port: 5000
# =============================================================
# -*- coding: utf-8 -*-

import sys
import io
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import uuid
import logging
from datetime import datetime

import requests
from flask import Flask, request, jsonify
import config

# ------------------------------------------------------------------
# Setup logging
# ------------------------------------------------------------------
os.makedirs(config.LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [COORDINATOR] %(message)s",
    handlers=[
        logging.FileHandler(f"{config.LOG_DIR}/coordinator.log", encoding='utf-8'),
        logging.StreamHandler(io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)),
    ]
)
log = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Flask app
# ------------------------------------------------------------------
app = Flask(__name__)

# Latency profile hiện tại
current_profile = "local"
current_latency = config.LATENCY_PROFILES["local"]

# Lưu kết quả từng transaction để benchmark
transaction_results = []


# ------------------------------------------------------------------
# Helper: inject latency (phía Coordinator gửi message)
# ------------------------------------------------------------------
def inject_latency():
    if current_latency > 0:
        log.info(f"  [NET] Sending message — {current_latency*1000:.0f}ms delay...")
        time.sleep(current_latency)


# ------------------------------------------------------------------
# Helper: gửi HTTP request với timeout và error handling
# ------------------------------------------------------------------
def send_request(url, payload):
    """Gửi POST request, trả về (response_dict, error_string)."""
    inject_latency()
    try:
        resp = requests.post(
            url,
            json=payload,
            timeout=config.TIMEOUT_SECONDS
        )
        return resp.json(), None
    except requests.exceptions.Timeout:
        return None, "TIMEOUT"
    except requests.exceptions.ConnectionError:
        return None, "CONNECTION_ERROR"
    except Exception as e:
        return None, str(e)


# ------------------------------------------------------------------
# Endpoint: SET CONFIG
# Client gọi để chọn latency profile trước khi benchmark
# ------------------------------------------------------------------
@app.route("/config", methods=["POST"])
def set_config():
    global current_profile, current_latency
    data = request.get_json()
    profile = data.get("latency_profile", "local")

    if profile not in config.LATENCY_PROFILES:
        return jsonify({"error": f"Unknown profile: {profile}"}), 400

    current_profile = profile
    current_latency = config.LATENCY_PROFILES[profile]

    # Đồng bộ latency profile sang cả 2 participants
    for name, url in config.PARTICIPANTS.items():
        try:
            requests.post(
                f"{url}/config",
                json={"latency_profile": profile},
                timeout=5
            )
        except Exception as e:
            log.warning(f"Không thể set config cho {name}: {e}")

    log.info(f"[CONFIG] Profile: {profile} ({current_latency*1000:.0f}ms)")
    return jsonify({
        "status":     "ok",
        "profile":    profile,
        "latency_ms": current_latency * 1000
    })


# ------------------------------------------------------------------
# CORE: 2PC Transaction
# Đây là hàm trung tâm — thực thi toàn bộ 2-Phase Commit
# ------------------------------------------------------------------
def run_2pc(transaction_id, operations):
    """
    Thực thi 2-Phase Commit và trả về kết quả chi tiết.

    Cấu trúc timing:
      t_start          → bắt đầu toàn bộ transaction
      t_phase1_start   → bắt đầu Phase 1 (gửi PREPARE)
      t_phase1_end     → nhận đủ VOTE từ tất cả participants
      t_phase2_start   → bắt đầu Phase 2 (gửi COMMIT/ABORT)
      t_phase2_end     → nhận đủ ACK
      t_end            → kết thúc toàn bộ transaction
    """

    result = {
        "transaction_id":   transaction_id,
        "latency_profile":  current_profile,
        "latency_ms":       current_latency * 1000,
        "decision":         None,
        "total_time_ms":    0,
        "phase1_time_ms":   0,
        "phase2_time_ms":   0,
        "network_wait_ms":  0,
        "work_ms":          0,
        "votes":            {},
        "acks":             {},
        "error":            None,
        "timestamp":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Số messages trong 2PC với 2 participants = 4 × N = 8 messages
    # Mỗi message chịu 1 lần latency (cả chiều đi lẫn chiều về)
    # network_wait = latency × số lần inject
    n_participants = len(config.PARTICIPANTS)
    # Phase 1: gửi PREPARE (N lần) + nhận VOTE (N lần) = 2N injections
    # Phase 2: gửi COMMIT/ABORT (N lần) + nhận ACK (N lần) = 2N injections
    # Tổng: 4N injections
    expected_network_wait = current_latency * 4 * n_participants * 1000

    t_start = time.perf_counter()

    # ==============================================================
    # PHASE 1 — VOTING
    # Coordinator → PREPARE → tất cả Participants
    # ==============================================================
    log.info(f"{'='*50}")
    log.info(f"[2PC] START transaction_id={transaction_id}")
    log.info(f"[2PC] Profile={current_profile} | Latency={current_latency*1000:.0f}ms")
    log.info(f"[STATE] INITIAL → WAIT")

    t_phase1_start = time.perf_counter()

    votes = {}
    for name, url in config.PARTICIPANTS.items():
        log.info(f"[PHASE 1] Gửi PREPARE → {name} ({url})")

        response, error = send_request(
            f"{url}/prepare",
            {
                "transaction_id": transaction_id,
                "operations":     operations,
                "coordinator":    config.COORDINATOR_URL,
            }
        )

        if error:
            log.warning(f"[PHASE 1] {name} KHÔNG PHẢN HỒI: {error}")
            votes[name] = config.MSG_VOTE_ABORT
            result["error"] = f"{name}: {error}"
        else:
            vote = response.get("vote")
            votes[name] = vote
            log.info(f"[PHASE 1] {name} → {vote}")

    t_phase1_end = time.perf_counter()
    result["votes"] = votes

    # ==============================================================
    # QUYẾT ĐỊNH
    # Nếu TẤT CẢ VOTE_COMMIT → GLOBAL_COMMIT
    # Nếu BẤT KỲ VOTE_ABORT  → GLOBAL_ABORT
    # ==============================================================
    all_commit = all(v == config.MSG_VOTE_COMMIT for v in votes.values())

    if all_commit:
        decision = config.MSG_GLOBAL_COMMIT
        log.info(f"[DECISION] Tất cả VOTE_COMMIT → GLOBAL_COMMIT ✓")
        log.info(f"[STATE] WAIT → COMMIT")
    else:
        decision = config.MSG_GLOBAL_ABORT
        aborted_by = [k for k, v in votes.items() if v != config.MSG_VOTE_COMMIT]
        log.warning(f"[DECISION] VOTE_ABORT từ: {aborted_by} → GLOBAL_ABORT ✗")
        log.info(f"[STATE] WAIT → ABORT")

    result["decision"] = decision

    # ==============================================================
    # PHASE 2 — DECISION
    # Coordinator → COMMIT/ABORT → tất cả Participants
    # ==============================================================
    t_phase2_start = time.perf_counter()

    endpoint = "/commit" if decision == config.MSG_GLOBAL_COMMIT else "/abort"
    acks = {}

    for name, url in config.PARTICIPANTS.items():
        log.info(f"[PHASE 2] Gửi {decision} → {name}")

        response, error = send_request(
            f"{url}{endpoint}",
            {
                "transaction_id": transaction_id,
                "operations":     operations,
                "decision":       decision,
            }
        )

        if error:
            log.warning(f"[PHASE 2] {name} KHÔNG ACK: {error}")
            acks[name] = "NO_ACK"
        else:
            ack = response.get("ack", response.get("status"))
            acks[name] = ack
            log.info(f"[PHASE 2] {name} → ACK ✓")

    t_phase2_end = time.perf_counter()
    result["acks"] = acks

    t_end = time.perf_counter()

    # ==============================================================
    # TÍNH TOÁN METRICS
    # ==============================================================
    total_ms   = (t_end - t_start) * 1000
    phase1_ms  = (t_phase1_end - t_phase1_start) * 1000
    phase2_ms  = (t_phase2_end - t_phase2_start) * 1000

    # network_wait = thời gian sleep thực tế trong toàn bộ 2PC
    # = latency × 4N (gửi PREPARE×N + nhận VOTE×N + gửi COMMIT×N + nhận ACK×N)
    network_wait_ms = current_latency * 1000 * 4 * n_participants
    work_ms         = max(0, total_ms - network_wait_ms)

    # Cost of Coordination = % thời gian chờ mạng
    coord_cost_pct = (network_wait_ms / total_ms * 100) if total_ms > 0 else 0

    result["total_time_ms"]   = round(total_ms, 3)
    result["phase1_time_ms"]  = round(phase1_ms, 3)
    result["phase2_time_ms"]  = round(phase2_ms, 3)
    result["network_wait_ms"] = round(network_wait_ms, 3)
    result["work_ms"]         = round(work_ms, 3)
    result["coord_cost_pct"]  = round(coord_cost_pct, 2)

    log.info(f"[METRICS] Total={total_ms:.1f}ms | "
             f"Phase1={phase1_ms:.1f}ms | Phase2={phase2_ms:.1f}ms")
    log.info(f"[METRICS] Network wait={network_wait_ms:.1f}ms | "
             f"Work={work_ms:.1f}ms | "
             f"CoordCost={coord_cost_pct:.1f}%")
    log.info(f"[2PC] END — {decision}")
    log.info(f"{'='*50}")

    return result


# ------------------------------------------------------------------
# Endpoint: EXECUTE TRANSACTION
# Client gọi để thực thi 1 transaction qua 2PC
# ------------------------------------------------------------------
@app.route("/transaction", methods=["POST"])
def execute_transaction():
    data = request.get_json()

    # Tạo transaction_id mới nếu không có
    transaction_id = data.get("transaction_id", str(uuid.uuid4()))

    # Operations: mỗi operation gắn với 1 participant cụ thể
    operations = data.get("operations", [
        {
            "site":       "participant_a",
            "account_id": f"ACC-{1000 + len(transaction_results)}",
            "amount":     round(1000.0 + len(transaction_results) * 10, 2),
            "currency":   "USD",
        },
        {
            "site":       "participant_b",
            "account_id": f"ACC-{5000 + len(transaction_results)}",
            "amount":     round(2000.0 + len(transaction_results) * 10, 2),
            "currency":   "EUR",
        },
    ])

    result = run_2pc(transaction_id, operations)
    transaction_results.append(result)

    return jsonify(result)


# ------------------------------------------------------------------
# Endpoint: HEALTH CHECK
# ------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status":             "online",
        "role":               "coordinator",
        "current_profile":    current_profile,
        "latency_ms":         current_latency * 1000,
        "transactions_run":   len(transaction_results),
    })


# ------------------------------------------------------------------
# Endpoint: GET RESULTS
# Trả về tất cả kết quả transactions đã chạy
# ------------------------------------------------------------------
@app.route("/results", methods=["GET"])
def get_results():
    return jsonify({
        "total":   len(transaction_results),
        "results": transaction_results
    })


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
if __name__ == "__main__":
    log.info("=" * 50)
    log.info("  Coordinator — Port 5000")
    log.info("  2-Phase Commit Protocol")
    log.info("=" * 50)
    app.run(host="127.0.0.1", port=5000, debug=False)