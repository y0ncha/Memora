# **Step-by-step implementation instructions (PoC)**

### **Step 0 — Repo scaffold (10–20 min)**

1. Create folders:
    - interlock/
    - interlock/orchestrator/
    - interlock/statebus/
    - interlock/schemas/
    - interlock/agent/ *(agent interface + mock agent)*
    - interlock/mcp_server/
    - examples/
    - runs/
    - tests/
2. Add pyproject.toml (or requirements.txt) with:
    - pydantic
    - pytest
    - MCP server lib you chose (e.g., fastmcp)
3. Add python -m interlock entrypoint with a tiny CLI parser that supports:
    - interlock run --ticket PROJ-123 --mock [--resume]

**Checkpoint:** python -m interlock --help works.

---

### **Step 1 — Pydantic schemas (foundation)**

Implement in interlock/schemas/:

- PinnedContext
- Source
- Evidence
- PlanStep, Plan
- ExecutionRequest, ExecutionResult
- CoverageReport
- InvalidationReport
- Governance
- RunInfo (run_id, ticket_id, status, next_state)
- Snapshot (wrap run, pinned, working, governance)
- Event

**Rules:**

- Keep all IDs as strings (stable IDs in mock mode).
- Add schema_version string in Snapshot and Event to fail closed on mismatch.

**Checkpoint:** You can python -c "from interlock.schemas import Snapshot; print(Snapshot.model_json_schema())".

---

### **Step 2 — State Bus (events + snapshot persistence)**

Implement in interlock/statebus/:

1. RunStore (file-based):
    - create runs/<run_id>/
    - write snapshot.json
    - append events.jsonl
    - write summary.md
2. Functions:
    - create_run(ticket_id) -> run_id
    - load_snapshot(run_id) -> Snapshot
    - save_snapshot(run_id, snapshot)
    - append_event(run_id, event)
    - write_summary(run_id, markdown)
    - list_runs()
    - find_latest_run_for_ticket(ticket_id) *(for resume)*

**Determinism requirements:**

- In mock mode, generate run_id deterministically (e.g., run_PROJ-123_001) based on existing runs count.
- Event IDs deterministic too (e.g., evt_001, evt_002).

**Checkpoint:** Running a tiny script creates a run folder with empty snapshot + 1 event.

---

### **Step 3 — Agent interface + mock tool world**

Implement in interlock/agent/:

1. Define an Agent interface with methods corresponding to states:
    - fetch_context(ticket_id) -> (sources, raw_text_bundle)
    - pin_context(raw_text_bundle) -> PinnedContext
    - build_evidence(raw_text_bundle, sources) -> list[Evidence]
    - generate_plan(pinned, evidence) -> Plan
    - execute_plan(plan, pinned, evidence) -> ExecutionResult
2. Implement MockAgent:
    - Uses deterministic parsing rules (no LLM needed).
    - Reads mock payloads from examples/:
        - examples/PROJ-123_ticket.md
        - examples/doc_page.md
        - examples/logs.md
    - Returns stable sources and stable evidence ids.

**Checkpoint:** MockAgent.fetch_context() returns 3 sources + raw texts.

---

### **Step 4 — Orchestrator loop (deterministic FSM)**

Implement in interlock/orchestrator/:

1. Define the state order list:
    - PARSE_INTENT → FETCH_CONTEXT → PIN_CONTEXT → BUILD_EVIDENCE → GENERATE_PLAN → REQUEST_EXECUTION → VERIFY_EXECUTION
2. The orchestrator:
    - Loads snapshot if resuming, else creates new run.
    - Executes the current state.
    - After each state:
        - validate output with Pydantic
        - update snapshot
        - append event
        - persist snapshot + summary
    - If a gateway fails:
        - create InvalidationReport
        - set snapshot.run.status = FAIL_CLOSED
        - set snapshot.run.next_state appropriately
        - append failure event
        - stop

**Important:** Routing is **not** LLM-driven.

- The next state is either:
    - the next in the fixed list, or
    - snapshot.run.next_state when resuming.

**Checkpoint:** python -m interlock run --ticket PROJ-123 --mock produces artifacts and ends in DELIVER or FAIL_CLOSED.

---

### **Step 5 — Gateways (validation pass/fail)**

Implement three “gateway checks” as pure deterministic functions (suggest location: interlock/pipeline/gateways.py):

- validate_pinned_context(pinned) -> ok|InvalidationReport
- validate_plan(pinned, evidence, plan) -> ok|InvalidationReport
    - ensure every step has evidence_ids or assumptions
    - ensure no empty plan when ACs exist
- validate_execution(execution_result) -> ok|InvalidationReport
    - schema already validated, now check:
        - success == True
        - tests_ran non-empty

**Checkpoint:** Intentionally break something in examples to trigger FAIL_CLOSED and see summary explain why.

---

### **Step 6 — Coverage report (minimal but real)**

Implement build_coverage_report(pinned, plan) -> CoverageReport:

- For each acceptance criterion:
    - map to plan step(s) by simple deterministic rule:
        - step created per AC → direct mapping (PoC)
- Set PASS only if all ACs are mapped.

**Checkpoint:** If you remove a step or add an AC with no step, VERIFY fails closed with clear invalidation report.

---

### **Step 7 — Resume (after invalidation fixed)**

Implement resume behavior:

CLI:

- -resume:
    - find latest run for ticket
    - load snapshot
    - start from snapshot.run.next_state
    - append RESUME event

In orchestrator:

- when resuming:
    - do not rerun completed states unless next_state requires it
    - keep snapshot.pinned immutable (if pinned exists, don’t overwrite it)

**Checkpoint:** Run once with failing mock execution (see next step), then fix the input and resume; verify it jumps directly to REQUEST_EXECUTION.

---

### **Step 8 — Make execution fail once, then pass (to prove resume)**

In MockAgent.execute_plan():

- First attempt returns success=false and includes test output showing failure
- On subsequent resume attempt (deterministically), return success=true

Simplest deterministic toggle:

- Store a counter in snapshot (e.g., working.execution_attempts)
- If attempts == 0 → fail; else → pass

**Checkpoint:** First run FAIL_CLOSED with next_state=REQUEST_EXECUTION. Resume → DELIVER.

---

### **Step 9 — MCP server (tools)**

Implement MCP server in interlock/mcp_server/ exposing tools that call the orchestrator / RunStore:

Tools:

- interlock.run(ticket_id, mock=true, resume=false)
- interlock.get_snapshot(run_id)
- interlock.get_events(run_id, limit=100)
- interlock.get_summary(run_id)
- interlock.list_runs()

**Checkpoint:** You can start the server and call at least interlock.list_runs() successfully.

---

### **Step 10 — Tests (minimal)**

Add tests/:

1. **Determinism**
    - run twice in mock mode
    - compare snapshots ignoring timestamps
2. **Gateway failure**
    - modify mock ticket to remove acceptance criteria
    - assert FAIL_CLOSED and invalidation report exists
3. **Resume**
    - first run fails at execution
    - resume run delivers and appends RESUME event

**Checkpoint:** pytest -q passes.

---

## **Recommended “definition of done” for PoC**

- CLI works
- MCP tools work
- artifacts produced every run
- at least one gateway failure is demonstrable with a clear invalidation report
- resume works and continues from next_state
- pinned context is compact and stable (not raw dumps)
- plan steps cite evidence ids (or explicit assumptions)

---

## **What Interlock Produces**

A successful run yields:

- Pinned requirements (acceptance criteria + constraints)
- Evidence index with provenance
- Typed extracted entities
- Grounded plan (steps cite evidence or assumptions)
- Coverage report
- Run trace (events + snapshot)
- Execution result (tests run + output summary)
- Invalidation report (when failing closed)