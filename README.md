# Trans-Atlantic DB

> Network Latency Impact Study on 2-Phase Commit Transactions

| Field    | Value                                   |
|----------|-----------------------------------------|
| Course   | Distributed Database Systems            |
| Topic    | #93 — Network Latency Impact Study      |
| Category | 10 — Performance Benchmarking           |

---

## Overview

This project empirically measures how network latency affects
2-Phase Commit (2PC) distributed transactions across three simulated
network environments: Local (1ms), Regional (50ms), and
Trans-Atlantic/Global (250ms).

The central metric is the **Cost of Coordination** — what percentage
of total transaction time is spent *waiting for the network* versus
*doing actual database work*.

---

## Key Results

| Profile  | Latency | Mean      | Median    | P99       | CoordCost |
|----------|---------|-----------|-----------|-----------|-----------|
| Local    | 1ms     | 93.2ms    | 96.6ms    | 127.9ms   | 9.3%      |
| Regional | 50ms    | 501.7ms   | 507.1ms   | 540.0ms   | 79.8%     |
| Global   | 250ms   | 2106.6ms  | 2111.3ms  | 2133.1ms  | 94.9%     |

> At Trans-Atlantic latency (250ms), a transaction spends
> **94.9% of its time waiting for the network** — only 5.1%
> is actual database work.

---

## System Architecture

```
Client
  |
  v
Coordinator (Port 5000)     <- Orchestrates 2PC
  |              |
  v              v
Participant A  Participant B
(Site US:5001) (Site EU:5002)
site_a.db      site_b.db
5,000 records  5,000 records
```

**Dataset:** 10,000 Financial Transactions, horizontally
fragmented by region (US / EU) into two SQLite databases.

**2PC Message Flow (8 messages per transaction):**

```
Coordinator --PREPARE--> A, B          (Phase 1)
A, B --VOTE_COMMIT--> Coordinator      (Phase 1)
Coordinator --GLOBAL_COMMIT--> A, B    (Phase 2)
A, B --ACK--> Coordinator              (Phase 2)
```

---

## Project Structure

```
trans-atlantic-db/
├── coordinator/
│   └── coordinator.py      # 2PC Coordinator (Port 5000)
├── participants/
│   ├── participant_a.py    # Site US (Port 5001)
│   └── participant_b.py    # Site EU (Port 5002)
├── data/
│   ├── generate_data.py    # Dataset generator
│   ├── site_a.db           # SQLite — US transactions
│   └── site_b.db           # SQLite — EU transactions
├── analysis/
│   ├── benchmark.py        # 100 runs x 3 profiles
│   ├── charts.py           # 4 visualization charts
│   ├── stats.py            # Detailed statistical report
│   ├── failure_test.py     # Failure simulation & recovery
│   ├── benchmark_results.csv
│   ├── stats_summary.txt
│   ├── chart1_latency_statistics.png
│   ├── chart2_work_vs_network.png
│   ├── chart3_coordination_cost.png
│   └── chart4_distribution_boxplot.png
├── logs/                   # Runtime logs per node
├── config.py               # Central configuration
├── requirements.txt
└── README.md
```

---

## Installation

**Requirements:** Python 3.8+, Git

```bash
# 1. Clone repository
git clone https://github.com/YOUR_USERNAME/trans-atlantic-db.git
cd trans-atlantic-db

# 2. Create virtual environment
python -m venv venv

# 3. Activate (Windows)
venv\Scripts\activate
# Activate (macOS/Linux)
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Generate dataset
python data/generate_data.py
```

---

## Running the System

### Step 1 — Start all 3 nodes (3 separate terminals)

**Terminal 1:**
```bash
venv\Scripts\activate
python participants/participant_a.py
```

**Terminal 2:**
```bash
venv\Scripts\activate
python participants/participant_b.py
```

**Terminal 3:**
```bash
venv\Scripts\activate
python coordinator/coordinator.py
```

### Step 2 — Verify all nodes are online

```bash
curl http://127.0.0.1:5000/health
curl http://127.0.0.1:5001/health
curl http://127.0.0.1:5002/health
```

### Step 3 — Run a single transaction

```bash
curl -X POST http://127.0.0.1:5000/transaction \
     -H "Content-Type: application/json" \
     -d "{}"
```

### Step 4 — Run full benchmark (300 transactions)

```bash
python analysis/benchmark.py
```

> **Expected duration:** ~25 minutes
> (Local: ~30s, Regional: ~4 min, Global: ~20 min)

### Step 5 — Generate charts

```bash
python analysis/charts.py
```

### Step 6 — Generate statistical report

```bash
python analysis/stats.py
```

### Step 7 — Run failure simulation

```bash
python analysis/failure_test.py
```

---

## Latency Configuration

Edit `config.py` to change parameters:

```python
LATENCY_PROFILES = {
    "local":    0.001,   # 1ms   — same datacenter
    "regional": 0.050,   # 50ms  — cross-region
    "global":   0.250,   # 250ms — Trans-Atlantic
}

BENCHMARK_RUNS = 100     # transactions per profile
TIMEOUT_SECONDS = 10     # coordinator timeout
```

---

## Failure Simulation Results

| Test   | Scenario                          | Result                |
|--------|-----------------------------------|-----------------------|
| Test 1 | Normal transaction                | PASS — GLOBAL_COMMIT  |
| Test 2 | Participant B crash (timeout)     | PASS — GLOBAL_ABORT   |
| Test 3 | Recovery after failure            | PASS — GLOBAL_COMMIT  |

When Participant B fails to respond within 10 seconds,
the Coordinator issues `GLOBAL_ABORT` — ensuring Participant A
also does not commit. **No partial commits. Atomicity preserved.**

---

## Theoretical Foundation

Based on Özsu & Valduriez (2020), Chapter 4 Cost Model:

```
Total_Cost = TCPU × #instructions
           + TIO   × #disk_IOs
           + TMSG  × #messages      <- dominant at high latency
           + TTR   × #bytes
```

With 2 participants and 8 messages per 2PC transaction:

| Profile  | TMSG  | Comm Cost (8×TMSG) | Work Cost | Comm Dominance |
|----------|-------|--------------------|-----------|----------------|
| Local    | 1ms   | 8ms                | 85ms      | 9.3%           |
| Regional | 50ms  | 400ms              | 102ms     | 79.8%          |
| Global   | 250ms | 2000ms             | 107ms     | 94.9%          |

**Work cost is constant (~95ms) regardless of network conditions.**
Communication cost increases 250× from Local to Global.

---

## Charts

| Chart                              | Description                              |
|------------------------------------|------------------------------------------|
| `chart1_latency_statistics.png`    | Mean / Median / P99 per profile          |
| `chart2_work_vs_network.png`       | Work vs Network wait (stacked bar)       |
| `chart3_coordination_cost.png`     | Cost of Coordination % (line chart)      |
| `chart4_distribution_boxplot.png`  | Transaction time distribution            |

---

## References

- Özsu, M.T. & Valduriez, P. (2020). *Principles of Distributed
  Database Systems*, 4th Edition. Springer.
  - Ch.1: Distributed DBMS Architecture
  - Ch.4: Query Processing & Cost Model (Section 4.4)
  - Ch.5: Transaction Management & 2PC (Section 5.4)
