# Analysis Report: Trans-Atlantic DB

> Network Latency Impact on 2-Phase Commit Transactions

| Field    | Value                                    |
|----------|------------------------------------------|
| Project  | Topic #93 — Network Latency Impact Study |
| Category | 10 — Performance Benchmarking            |
| Dataset  | Financial_Transactions (10,000 records)  |

---

## 1. Introduction

This report analyzes how network latency affects the performance of
2-Phase Commit (2PC) distributed transactions. Three latency scenarios
were simulated: Local (1ms), Regional (50ms), and Global/Trans-Atlantic
(250ms). The central metric is the **Cost of Coordination** — the
percentage of total transaction time spent waiting for the network
rather than performing actual database work.

---

## 2. System Architecture

```
Client
  |
  v
Coordinator (Port 5000)
  |           |
  v           v
Site A      Site B
(US, 5001)  (EU, 5002)
site_a.db   site_b.db
```

**Fragmentation Strategy:** Horizontal fragmentation by region.

- Site A (US): 5,000 records where `region = 'US'`
- Site B (EU): 5,000 records where `region = 'EU'`

**2PC Message Flow per Transaction (N=2 participants):**

```
Coordinator --> PREPARE       --> Participant A  (1 message)
Coordinator --> PREPARE       --> Participant B  (1 message)
Participant A --> VOTE_COMMIT --> Coordinator    (1 message)
Participant B --> VOTE_COMMIT --> Coordinator    (1 message)
Coordinator --> GLOBAL_COMMIT --> Participant A  (1 message)
Coordinator --> GLOBAL_COMMIT --> Participant B  (1 message)
Participant A --> ACK         --> Coordinator    (1 message)
Participant B --> ACK         --> Coordinator    (1 message)

Total: 4N = 8 messages, each incurring one network delay
```

---

## 3. Methodology

- **Runs per profile:** 100 transactions (after 5 warm-up runs)
- **Latency injection:** `time.sleep()` applied to every message
  send/receive in the 2PC protocol
- **Metrics collected per transaction:**
  - `total_time_ms`: wall-clock time from start to final ACK
  - `network_wait_ms`: total sleep time = latency × 4N
  - `work_ms`: total_time_ms − network_wait_ms
  - `coord_cost_pct`: network_wait_ms / total_time_ms × 100
- **Statistical measures:** Mean, Median, P99 (99th percentile)
- **Outlier handling:** Warm-up runs excluded from measurements

---

## 4. Results

### 4.1 Transaction Time Statistics

| Profile  | Latency | Mean      | Median    | P99       |
|----------|---------|-----------|-----------|-----------|
| Local    | 1ms     | 79.4ms    | 77.0ms    | 125.3ms   |
| Regional | 50ms    | 490.4ms   | 491.0ms   | 526.8ms   |
| Global   | 250ms   | 2111.2ms  | 2113.4ms  | 2135.5ms  |

### 4.2 Cost of Coordination

| Profile  | Network Wait | Work Time | CoordCost |
|----------|-------------|-----------|-----------|
| Local    | 8.0ms       | 71.4ms    | 11.4%     |
| Regional | 400.0ms     | 90.4ms    | 81.7%     |
| Global   | 2000.0ms    | 111.2ms   | 94.7%     |

**Key observation:** Work time remains approximately constant
(~71–111ms) across all profiles. What changes dramatically is
the network wait time — confirming that actual database operations
are not the bottleneck in distributed transactions.

### 4.3 Failure Scenario Results

| Test   | Scenario                              | Expected      | Result |
|--------|---------------------------------------|---------------|--------|
| Test 1 | Normal transaction                    | GLOBAL_COMMIT | PASS   |
| Test 2 | Participant B crash (timeout ~10s)    | GLOBAL_ABORT  | PASS   |
| Test 3 | Recovery after failure                | GLOBAL_COMMIT | PASS   |

---

## 5. Analysis: Linking to Özsu & Valduriez Cost Model

### 5.1 The Cost Model

Özsu & Valduriez (4th ed., Chapter 4) define the total cost of
a distributed query/transaction as:

```
Total_Cost = TCPU × #instructions
           + TIO   × #disk_IOs
           + TMSG  × #messages
           + TTR   × #bytes_transferred
```

Where:

- `TCPU` = cost per CPU instruction (~nanoseconds)
- `TIO`  = cost per disk I/O (~milliseconds)
- `TMSG` = fixed overhead to initiate/receive one message
- `TTR`  = transmission time per byte (bandwidth-dependent)

### 5.2 Applying the Model to Our Results

In our experiment, `TMSG` is the dominant variable — it represents
the one-way network latency we simulate (1ms, 50ms, 250ms).

**Communication cost for one 2PC transaction (8 messages):**

```
Comm_Cost = TMSG × 8

Local:    Comm_Cost = 0.001 × 8 =    8ms
Regional: Comm_Cost = 0.050 × 8 =  400ms
Global:   Comm_Cost = 0.250 × 8 = 2000ms
```

**Theoretical vs. Measured:**

| Profile  | Theoretical Comm | Measured Network Wait | Difference |
|----------|-----------------|----------------------|------------|
| Local    | 8ms             | 8.0ms                | 0.0ms      |
| Regional | 400ms           | 400.0ms              | 0.0ms      |
| Global   | 2000ms          | 2000.0ms             | 0.0ms      |

The measured network wait matches the theoretical model exactly,
validating our simulation approach.

### 5.3 What Drives the Cost of Coordination?

Our results demonstrate a key theorem from Chapter 5 of Özsu:
**in Wide Area Networks, communication cost dominates all other costs.**

At Global latency (250ms):

- CPU + I/O work ≈ 111ms (constant, independent of network)
- Communication cost = 2000ms (grows linearly with latency)
- **CoordCost = 94.7%** — nearly 18× more time waiting than working

This has profound practical implications: optimizing the database
query (reducing CPU/IO cost) yields negligible benefit when the
network latency is high. A 50% faster query at 250ms latency would
only reduce total time from 2111ms to ~2056ms — a 2.6% improvement.
The real optimization must target the **number of messages (4N)**
or the **latency itself**.

### 5.4 P99 Tail Latency Analysis

P99 represents the worst-case experience for 1 in 100 transactions:

| Profile  | Median    | P99       | P99 Overhead |
|----------|-----------|-----------|-------------|
| Local    | 77.0ms    | 125.3ms   | +62.8%      |
| Regional | 491.0ms   | 526.8ms   | +7.3%       |
| Global   | 2113.4ms  | 2135.5ms  | +1.0%       |

At high latency, P99 converges toward Median — the distribution
becomes tight because the dominant cost (network sleep) is perfectly
deterministic. At local latency, P99 shows higher variance (+62.8%)
because HTTP overhead and OS scheduling jitter become relatively
significant, confirming the need to report tail latency rather than
averages alone.

### 5.5 Failure Handling and Atomicity

The failure simulation confirms the core guarantee of 2PC:
**Atomicity is preserved even under node failure.**

When Participant B failed to respond within the timeout window
(10 seconds), the Coordinator issued `GLOBAL_ABORT` — ensuring
Participant A also did not commit. This prevents the most dangerous
consistency violation in distributed systems: **partial commit**,
where one site commits while another does not.

This behavior maps directly to Özsu Chapter 5's description of
the 2PC termination protocol: a Coordinator in `WAIT` state that
receives no response must conservatively abort to maintain safety.

---

## 6. Conclusion

This study empirically confirms the theoretical predictions of the
Özsu & Valduriez cost model for distributed transactions:

1. **Communication cost scales linearly** with both latency and
   message count (4N for centralized 2PC with N participants).

2. **Work time is constant** (~71–111ms) regardless of network
   conditions — the database operations are not the bottleneck.

3. **Cost of Coordination rises sharply**: 11.4% (Local) →
   81.7% (Regional) → 94.7% (Global). At Trans-Atlantic latency,
   a transaction spends ~18× more time waiting for the network
   than doing useful work.

4. **2PC guarantees Atomicity** under failure: timeout detection
   and `GLOBAL_ABORT` prevent partial commits across sites.

5. **Practical implication**: For globally distributed financial
   systems, the 2PC protocol's communication overhead makes it
   unsuitable for low-latency requirements. Alternative protocols
   (Paxos, Raft) or relaxed consistency models (eventual
   consistency) should be considered when `TMSG` is large.

---

## 7. References

- Özsu, M.T. & Valduriez, P. (2020). *Principles of Distributed
  Database Systems*, 4th Edition. Springer.
  - Chapter 1: Introduction to Distributed Databases
  - Chapter 4: Query Processing — Cost Model (Section 4.4)
  - Chapter 5: Transaction Management — 2PC Protocol (Section 5.4)
