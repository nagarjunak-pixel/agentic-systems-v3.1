# Shared Agentic Core — Phase 0 Backbone (v3.1)

Welcome to Phase 0 of the Shared Agentic Core monorepo skeleton. This package lays the foundation for high-availability model routing, serialized local memory execution, secure sandboxing, and unified orchestrator loops.

---

## Directory Structure

```
phase0/
├── README.md                      # Core documentation & walkthrough
├── requirements.txt               # Dependencies (requests, jsonschema, pytest)
├── proto/
│   └── execution_gateway.proto    # gRPC gateway contract with JWT & error codes
├── db/
│   └── schema.sql                 # SQL schema for task tracking & coordinates
├── seccomp/
│   └── seccomp_profile.json       # gVisor seccomp JSON system call profile (macOS safe spec)
├── core/
│   ├── __init__.py                # Package versioning info
│   ├── wammr/                     # Model Router (WAMMR)
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── router.py              # Circuit Breaker, Exponential retry backoff, Self-repair tracker
│   │   └── routing_config.json    # Routing matrix matching Layer 4 spec
│   ├── memory/                    # File-based Memory Engine
│   │   ├── __init__.py
│   │   ├── engine.py              # Mutex write-queue queue, fallback schema validator
│   │   └── handoff_schema.json    # State handoff schema (GAP-05 validation)
│   └── orchestrator/              # Multi-Agent Orchestrator
│       ├── __init__.py
│       ├── loop.py                # Planner-Builder-Judge execution loop skeleton (V033)
│       ├── broker.py              # Temporal Event Broker (timers, watches, hooks) (GAP-13)
│       └── hitl.py                # HITL Review Gateway stub for escalations
└── tests/                         # Unit tests
    ├── __init__.py
    ├── test_wammr.py              # WAMMR circuit breakers & retry backoff tests
    ├── test_memory.py             # Memory Engine mutex locking & schema validation tests
    └── test_orchestrator.py       # Orchestrator loops, repair checks, and broker timer tests
```

---

## Features & Architectural Fixes (Phase 0)

### 1. WAMMR (Model Router) — `core/wammr/`
* **JSON Config-Driven**: Loads routing matrix parameters from `routing_config.json`.
* **Circuit Breakers**: Implements rolling-window failure evaluation. Exceeding a 50% failure rate over consecutive requests trips the circuit into `OPEN`, triggering a bypass cooldown (60 seconds) before attempting `HALF_OPEN`.
* **Retries & 429 Backoff**: Retries transient failures (e.g. rate limit HTTP 429s, timeouts) with an exponential backoff factor of 2.0 up to the configured limit.
* **Fallback Routing**: Bypasses down primary models and automatically redirects task payloads to designated fallback models.
* **Self-Repair Cap (GAP-04)**: Restricts autonomous self-repair operations to **maximum 1 run per 15 minutes** using the `SelfRepairTracker` to prevent infinite failure loops.

### 2. File Memory Engine — `core/memory/`
* **Mutex Serialized Queue (GAP-10)**: Eliminates race conditions on local markdown/Obsidian files. All write updates are pushed to a thread-safe Queue and processed sequentially by a single-threaded daemon writer.
* **Handoff Validation (GAP-05)**: Defines a structured handoff schema in `handoff_schema.json` ensuring compiler lints, diffs, attempted solutions, and REPL variable states are verified by the *Advisor* agent.

### 3. Orchestration & Event Broker — `core/orchestrator/`
* **Planner-Builder-Judge (V033)**: Coordinates task planning, code generation (Builder), and test validation (Judge).
* **HITL Gateway**: Integrates escalation stub interfaces for operator intervention when validation and self-repair options are exhausted.
* **Temporal Event Broker (GAP-13 / J9-078)**: Implements wake-up hooks for timed delays, file changes, and webhook events, allowing worker agents to resume execution paths without continuous CPU polling.

### 4. Security & API Design Fixes (Pre-Build Review Resolutions)
* **Authenticated gRPC Gateway**: The protobuf specification includes `auth_token` fields and OAuth/JWT context header requirements to prevent unauthenticated network invocation inside the mesh.
* **Structured Error Contract**: Adds `ErrorCode` enums (`ERROR_SANDBOX_OOM`, `ERROR_SECCOMP_VIOLATION`, etc.) to the gRPC `TaskResponse` message for automated failover handling.
* **Seccomp Profile Whitelist**: Extends the gVisor JSON profile to include missing system calls (`futex`, `rt_sigreturn`, `statx`, `getcwd`, `pipe`, `pipe2`, `epoll_wait`, `uname`) required to boot Python/Node runtimes without triggering kernel crashes.
* **Conflict 4 Resolution**: Unifies both coordinates and activity briefs under the centralized SQL database definition in `db/schema.sql`.

---

## Running the Unit Tests

Ensure dependencies are installed and execute pytest:

```bash
pip install -r requirements.txt
pytest -v
```
