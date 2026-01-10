# PoC MVP Plan

---

## **Goal**

Build the simplest PoC that conveys Interlock’s core idea end-to-end:

A **deterministic orchestration layer** that *captures an agent* inside a fixed flow with **clear gateways** (validation pass/fail), **context compaction** (pinned high-signal context only), and the ability to **resume** from the last checkpoint after an invalidation is fixed. The flow includes an explicit **Execution phase** where the agent uses the plan + pinned context to actually “do the work”.

---

## **What the PoC must demonstrate**

1. **Interlock is an MCP server** exposing tools to run the flow and fetch artifacts
2. A run produces artifacts: events.jsonl, snapshot.json, summary.md
3. The process is **deterministic** (same mock inputs → same outputs)
4. Gateways can **fail closed** with a clear invalidation report (and alert the user)
5. **Resume** continues from the last checkpoint instead of restarting
6. **Context management**: Interlock pins only important context (ACs, todos, evidence) and drops irrelevant metadata
7. Interlock triggers **Execution**: the agent uses pinned context + plan to solve the ticket, and Interlock validates the result

Everything else is optional.

---

## **MVP Scope**

### **Execution modes**

- CLI: python -m interlock run --ticket PROJ-123 --mock [--resume]
- MCP tools:
    - interlock.run(ticket_id, mock=true, resume=false)
    - interlock.get_snapshot(run_id)
    - interlock.get_events(run_id, limit=100)
    - interlock.get_summary(run_id)
    - interlock.list_runs()

### **Key architecture rule**

- **Interlock orchestrates + validates + persists**
- **Agent performs actions** (tool calls + extraction + planning + execution)
- The agent never decides routing; routing is deterministic.

---

## **Minimal state machine (7 states)**

Hardcoded order + deterministic gateways:

1. PARSE_INTENT
2. FETCH_CONTEXT *(Agent action: “call tools”)*
3. PIN_CONTEXT *(Agent action: distill; Interlock gateway validates and freezes pinned context)*
4. BUILD_EVIDENCE *(Agent action: extract evidence objects; Interlock enforces budgets)*
5. GENERATE_PLAN *(Agent action: produce structured plan; Interlock gateway validates grounding + coverage readiness)*
6. REQUEST_EXECUTION *(Interlock instructs agent to execute plan using pinned context + evidence)*
7. VERIFY_EXECUTION *(Interlock gateway: execution result schema + test success)* → DELIVER or FAIL_CLOSED

No branching complexity beyond fail-closed + resume.

---

## **Minimal Data Model (Pydantic schemas)**

Keep schemas small but real.

### **Pinned Context (immutable after validation)**

**PinnedContext**

- problem_statement: str
- acceptance_criteria: list[str]
- todos: list[str]
- constraints: list[str]

### **Inputs and context units**

**Source**

- source_id, type, title, locator
- (raw content may exist in mock tool output, but snapshot only keeps metadata)

**Evidence**

- evidence_id, source_id, locator, snippet, tags, tokens_estimate

### **Planning + execution**

**Plan**

- steps: list[PlanStep] where PlanStep has:
    - action, files_touched, evidence_ids, assumptions
- unknowns: list[str]
- risks: list[str]

**ExecutionRequest**

- instructions: str
- plan_ref: str (id or hash)
- must_run_tests: bool

**ExecutionResult**

- success: bool
- actions_taken: list[str]
- tests_ran: list[str]
- test_output_summary: str
- evidence_ids_used: list[str]

### **Verification + governance**

**CoverageReport**

- mapping: each acceptance criterion → step_ids + evidence_ids
- status: PASS | FAIL

**InvalidationReport**

- reason_code: str
- message: str
- missing_fields: list[str]
- suggested_fix: str
- resume_state: str

**Governance**

- budgets + retries + last_error_signature

**Event**

- event_id, ts, state, tool_calls, validations, delta_summary, error_signature

---

## **State Bus MVP (file-based, event-sourced)**

Per run folder: runs/<run_id>/

- events.jsonl append-only (one event per transition)
- snapshot.json rewritten each checkpoint
- summary.md rewritten each checkpoint (short)

### **Determinism rules**

- Use stable IDs: src_001, ev_001, step_001 (no UUIDs in mock)
- Stable ordering everywhere (sources/evidence/steps)
- timestamps may exist, but must not affect IDs or ordering

---

## **Gateways (clear validation points)**

### **Gateway A — PIN_CONTEXT validation (fail closed)**

Fail if:

- no acceptance criteria found
- pinned context schema invalid

On fail:

- write InvalidationReport
- set snapshot.run.status = FAIL_CLOSED
- set snapshot.run.next_state = PIN_CONTEXT (or FETCH_CONTEXT if missing data)
- alert user via summary.md

### **Gateway B — PLAN grounding + coverage readiness (fail closed)**

Fail if:

- any plan step has neither evidence_ids nor explicit assumptions
- any acceptance criteria cannot map to a plan step (or becomes an unknown)

On fail:

- write InvalidationReport
- set next_state = GENERATE_PLAN or BUILD_EVIDENCE

### **Gateway C — Execution verification (fail closed)**

Fail if:

- ExecutionResult schema invalid
- success == false
- required tests weren’t run (in PoC: enforce at least one test command)

On fail:

- write InvalidationReport
- set next_state = REQUEST_EXECUTION

---

## **Resume MVP (after invalidation is fixed)**

Implement resume from latest checkpoint with minimal logic:

CLI:

- -resume finds the latest run for the same ticket where status is FAIL_CLOSED or RUNNING
- load snapshot.json
- continue from snapshot.run.next_state

MCP:

- interlock.run(..., resume=true) uses the same selection logic

Record resume:

- append an event: state="RESUME" with resumed_from_run_id

No migrations in PoC; schema version mismatch → fail closed with explanation.

---

## **Mock Inputs (the PoC “world”)**

PoC needs repeatable mock tool outputs:

- mock “ticket” (long description + ACs + todos)
- mock “doc page” (long)
- mock “PR discussion” or “log” (long)
- optional: mock “repo tree” list

FETCH_CONTEXT uses these to populate sources[] (metadata only) and returns raw text to the agent, but only the pinned/evidence artifacts are stored long-term.

---

## **How each state works (simplest version)**

### **1) PARSE_INTENT**

- initialize run folder
- create snapshot skeleton
- append event

### **2) FETCH_CONTEXT (agent action, mocked)**

- agent “calls tools” (mock functions)
- outputs raw long texts + source metadata
- snapshot stores sources[] (metadata), not raw dumps
- append event with tool call hashes

### **3) PIN_CONTEXT (agent action + gateway)**

- agent extracts pinned context (ACs/todos/constraints)
- validate schema
- freeze into snapshot.pinned
- append event

### **4) BUILD_EVIDENCE (agent action + budgets)**

- agent extracts 5–15 evidence objects using heuristics
- enforce budgets (truncate deterministically)
- append event

### **5) GENERATE_PLAN (agent action + gateway)**

- agent produces structured plan:
    - each step cites evidence ids OR explicit assumptions
    - unknowns listed if lacking evidence
- validate schema
- append event

### **6) REQUEST_EXECUTION (Interlock instructs agent)**

- Interlock creates a deterministic ExecutionRequest:
    - “execute steps 1..N”
    - “run tests”
    - “report results”
- append event

### **7) VERIFY_EXECUTION (gateway)**

- validate ExecutionResult schema
- verify tests ran + success
- pass → DELIVER, fail → FAIL_CLOSED with invalidation report
- append event

---

## **MCP Server MVP (must exist)**

Expose tools (all operate on runs/ artifacts):

- interlock.run(ticket_id, mock=true, resume=false)
- interlock.get_snapshot(run_id)
- interlock.get_events(run_id, limit=100)
- interlock.get_summary(run_id)
- interlock.list_runs()

---

## **Tests (minimal, high-signal)**

1. **Determinism**
- run twice in mock mode, snapshots identical (ignore timestamps if present)
1. **Resume**
- force a gateway failure once (e.g., missing ACs), then fix mock input and resume; verify it continues from next_state
1. **Execution verification**
- first run returns success=false execution result → fail closed
- resume run returns success=true → deliver

---

## **Deliverables Checklist (PoC “done”)**

- MCP server exists and tools work
- CLI run works in mock mode
- artifacts written (events/snapshot/summary)
- deterministic outputs
- gateway invalidation + fail closed + user-facing summary
- resume continues from last checkpoint
- pinned context demonstrates context compaction
- execution phase exists and is validated
- minimal tests pass
